
import logging
from typing import List, Dict, Optional
from django.conf import settings

from utils.geospatial import decode_polyline, calculate_route_distance
from utils.exceptions import NoFuelStationError
from apps.fuel.fuel_service import FuelService

logger = logging.getLogger(__name__)


class OptimizationService: 
    
    VEHICLE_RANGE_MILES = getattr(settings, 'VEHICLE_RANGE_MILES', 500.0)
    FUEL_EFFICIENCY_MPG = getattr(settings, 'FUEL_EFFICIENCY_MPG', 10.0)
    TANK_CAPACITY_GALLONS = getattr(settings, 'TANK_CAPACITY_GALLONS', 50.0)
    
    @classmethod
    def optimize_fuel_stops(
        cls,
        route_geometry: str,
        route_distance_miles: float
    ) -> dict: 
        # Step 1: Decode route geometry
        route_points = decode_polyline(route_geometry)
        
        if not route_points:
            raise NoFuelStationError("Route geometry could not be decoded.")
        
        # Step 2: Find stations in corridor
        stations = FuelService.get_stations_near_route(route_points)
        
        if not stations:
            # If route is shorter than range, no stops needed
            if route_distance_miles <= cls.VEHICLE_RANGE_MILES:
                return {
                    'fuel_stops': [],
                    'total_fuel_gallons': 0.0,
                    'total_fuel_cost': 0.0,
                    'num_stops': 0,
                }
            raise NoFuelStationError(
                f"No fuel stations found within {cls.CORRIDOR_WIDTH_MILES} miles "
                f"of the route, and the route ({route_distance_miles:.0f} mi) "
                f"exceeds vehicle range ({cls.VEHICLE_RANGE_MILES:.0f} mi)."
            )
        
        # Step 3: Run greedy optimization
        return cls._greedy_optimize(stations, route_distance_miles)
    
    # @classmethod
    # def _greedy_optimize(
    #     cls,
    #     stations: List[dict],
    #     route_distance_miles: float
    # ) -> dict: 
        
    #     fuel_stops = []
    #     total_fuel_gallons = 0.0
    #     total_fuel_cost = 0.0
        
    #     # State tracking
    #     current_position = 0.0  # miles from start
    #     current_fuel_miles = cls.VEHICLE_RANGE_MILES  # miles of fuel remaining
        
    #     # Safety margin: don't cut it too close
    #     safety_margin = 10.0  # miles
        
    #     max_iterations = len(stations) + 10
    #     iteration = 0
        
    #     while current_position + current_fuel_miles < route_distance_miles:
    #         iteration += 1
    #         if iteration > max_iterations:
    #             raise NoFuelStationError(
    #                 "Optimization failed to converge. Possible loop in station selection."
    #             )
            
    #         # Find all stations reachable from current position
    #         reachable = [
    #             s for s in stations
    #             if current_position < s['distance_from_start'] <= (
    #                 current_position + current_fuel_miles - safety_margin
    #             )
    #         ]
            
    #         if not reachable:
    #             # Try without safety margin as last resort
    #             reachable = [
    #                 s for s in stations
    #                 if current_position < s['distance_from_start'] <= (
    #                     current_position + current_fuel_miles
    #                 )
    #             ]
                
    #             if not reachable:
    #                 raise NoFuelStationError(
    #                     f"No reachable fuel stations between mile {current_position:.1f} "
    #                     f"and mile {current_position + current_fuel_miles:.1f}. "
    #                     f"The route may have gaps in fuel station coverage."
    #                 )
            
    #         # Select cheapest reachable station
    #         # If multiple stations at same location with different prices,
    #         # the cheapest one wins
    #         cheapest = min(reachable, key=lambda s: s['retail_price'])
            
    #         # Calculate fuel needed to reach this station from current position
    #         miles_to_station = cheapest['distance_from_start'] - current_position
    #         fuel_used = miles_to_station / cls.FUEL_EFFICIENCY_MPG
            
    #         # Fuel remaining when arriving at station
    #         fuel_remaining_gallons = (
    #             cls.TANK_CAPACITY_GALLONS - fuel_used
    #         )
            
    #         fuel_to_buy = cls.TANK_CAPACITY_GALLONS - fuel_remaining_gallons
            
    #         purchase_cost = fuel_to_buy * float(cheapest['retail_price'])
            
    #         # Record the stop
    #         fuel_stops.append({
    #             'station_name': cheapest['name'],
    #             'city': cheapest['city'],
    #             'state': cheapest['state'],
    #             'price': round(cheapest['retail_price'], 3),
    #             'distance_from_start': round(cheapest['distance_from_start'], 1),
    #             'fuel_gallons': round(fuel_to_buy, 2),
    #             'cost': round(purchase_cost, 2),
    #         })
            
    #         # Update totals
    #         total_fuel_gallons += fuel_to_buy
    #         total_fuel_cost += purchase_cost
            
    #         # Update state: we're now at the station with a full tank
    #         current_position = cheapest['distance_from_start']
    #         current_fuel_miles = cls.VEHICLE_RANGE_MILES
            
    #         logger.info(
    #             f"Stop #{len(fuel_stops)}: {cheapest['name']} at "
    #             f"mile {current_position:.1f}, ${cheapest['retail_price']}/gal"
    #         )
        
    #     # Final leg: destination is now reachable
    #     final_leg = route_distance_miles - current_position
    #     logger.info(
    #         f"Final leg: {final_leg:.1f} miles to destination. "
    #         f"Total stops: {len(fuel_stops)}, Total cost: ${total_fuel_cost:.2f}"
    #     )
        
    #     return {
    #         'fuel_stops': fuel_stops,
    #         'total_fuel_gallons': round(total_fuel_gallons, 2),
    #         'total_fuel_cost': round(total_fuel_cost, 2),
    #         'num_stops': len(fuel_stops),
    #     }
        
        
            
    @classmethod
    def _greedy_optimize(
        cls,
        stations: List[dict],
        route_distance_miles: float
        ) -> dict:
        """
        Determine fuel stops based on vehicle range.

        Rules:
        - Vehicle starts with a full tank.
        - Vehicle range is VEHICLE_RANGE_MILES (default 500).
        - One stop is selected for each required refuel interval.
        - The cheapest station in each interval is chosen.
        - Tank is assumed to be filled completely at each stop.
        """

        import math

        if route_distance_miles <= cls.VEHICLE_RANGE_MILES:
            return {
                "fuel_stops": [],
                "total_fuel_gallons": 0.0,
                "total_fuel_cost": 0.0,
                "num_stops": 0,
            }

        stations = sorted(
            stations,
            key=lambda s: s["distance_from_start"]
        )

        fuel_stops = []
        total_fuel_cost = 0.0
        total_fuel_gallons = 0.0

        range_miles = cls.VEHICLE_RANGE_MILES
        tank_gallons = cls.TANK_CAPACITY_GALLONS

        # Example:
        # 1201 miles / 500 range = 2 required refuels
        num_required_stops = (
            math.ceil(route_distance_miles / range_miles) - 1
        )

        for stop_index in range(1, num_required_stops + 1):

            segment_start = (stop_index - 1) * range_miles
            segment_end = stop_index * range_miles

            candidates = [
                station
                for station in stations
                if segment_start <
                station["distance_from_start"] <= segment_end
            ]

            if not candidates:
                raise NoFuelStationError(
                    f"No fuel station found between "
                    f"mile {segment_start:.1f} and "
                    f"mile {segment_end:.1f}"
                )

            selected = min(
                candidates,
                key=lambda s: float(s["retail_price"])
            )

            gallons_purchased = tank_gallons
            stop_cost = (
                gallons_purchased *
                float(selected["retail_price"])
            )

            fuel_stops.append({
                "station_name": selected["name"],
                "city": selected["city"],
                "state": selected["state"],
                "price": round(
                    float(selected["retail_price"]),
                    3
                ),
                "distance_from_start": round(
                    selected["distance_from_start"],
                    1
                ),
                "fuel_gallons": round(
                    gallons_purchased,
                    2
                ),
                "cost": round(
                    stop_cost,
                    2
                ),
            })

            total_fuel_gallons += gallons_purchased
            total_fuel_cost += stop_cost

            logger.info(
                f"Selected stop #{stop_index}: "
                f"{selected['name']} "
                f"at mile {selected['distance_from_start']:.1f} "
                f"(${selected['retail_price']}/gal)"
            )

        return {
            "fuel_stops": fuel_stops,
            "total_fuel_gallons": round(
                total_fuel_gallons,
                2
            ),
            "total_fuel_cost": round(
                total_fuel_cost,
                2
            ),
            "num_stops": len(fuel_stops),
        }
        
    