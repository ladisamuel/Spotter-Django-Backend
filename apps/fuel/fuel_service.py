"""
FuelService - Station discovery and filtering.

Provides two implementations based on DEBUG mode:
- Development: Bounding‑box reduction + Python Haversine filtering (no PostGIS)
- Production: PostGIS ST_DWithin spatial queries (database-level, indexed)

This abstraction allows the OptimizationService to work identically
in both environments without mode-specific logic.
"""

import logging
import math
from typing import List, Optional

from django.conf import settings
from django.db.models import QuerySet

from apps.fuel.models import FuelStation
from utils.geospatial import is_point_near_route
from utils.exceptions import EmptyDatasetError

logger = logging.getLogger(__name__)


class FuelService:
    """
    Service for finding fuel stations near a route.
    
    Mode-Aware Implementation:
    - DEBUG=True:  Bounding‑box + Haversine filtering in Python
    - DEBUG=False: Uses PostGIS ST_DWithin for efficient spatial queries
    
    The corridor width determines how far from the route we search.
    Default: 25 miles (configurable via ROUTE_CORRIDOR_WIDTH_MILES)
    """

    CORRIDOR_WIDTH_MILES = getattr(settings, 'ROUTE_CORRIDOR_WIDTH_MILES', 25.0)

    @classmethod
    def get_stations_near_route(
        cls,
        route_points: List[tuple],
        corridor_width: float = None
    ) -> List[dict]:
        """
        Find all fuel stations within a corridor of the route.
        
        Args:
            route_points: List of (lat, lon) tuples decoded from polyline
            corridor_width: Search distance in miles (default from settings)
        
        Returns:
            List of station dicts with keys:
                - id, truckstop_id, name, city, state
                - latitude, longitude, retail_price
                - distance_from_start (miles along route)
        
        Raises:
            EmptyDatasetError: If no fuel stations exist in the database
        """
        if not route_points:
            return []
        
        width = corridor_width or cls.CORRIDOR_WIDTH_MILES
        
        # Check if dataset is empty
        total_stations = FuelStation.objects.count()
        if total_stations == 0:
            raise EmptyDatasetError(
                "No fuel stations available in the database. "
                "Please run: python manage.py import_fuel_stations <csv_file>"
            )
        
        logger.info(
            f"Searching for stations near route ({len(route_points)} points, "
            f"{width}mi corridor). Total stations in DB: {total_stations}"
        )
        
        if settings.DEBUG:
            return cls._filter_dev(route_points, width)
        else:
            return cls._filter_prod(route_points, width)

    @classmethod
    def _compute_route_bbox(cls, route_points: List[tuple], width_miles: float) -> tuple:
        """
        Compute a bounding box around the route expanded by corridor width.
        
        Args:
            route_points: List of (lat, lon) tuples
            width_miles: Search radius in miles
        
        Returns:
            (min_lat, max_lat, min_lon, max_lon)
        
        Notes:
            - 1 degree latitude ≈ 69.0 miles (constant)
            - 1 degree longitude ≈ 69.0 * cos(latitude) miles (varies)
        """
        if not route_points:
            return (0.0, 0.0, 0.0, 0.0)
        
        delta_lat = width_miles / 69.0
        
        min_lat = max_lat = route_points[0][0]
        min_lon = max_lon = route_points[0][1]
        
        for lat, lon in route_points:
            lat_rad = math.radians(lat)
            delta_lon = width_miles / (69.0 * max(math.cos(lat_rad), 0.01))
            
            point_min_lat = lat - delta_lat
            point_max_lat = lat + delta_lat
            point_min_lon = lon - delta_lon
            point_max_lon = lon + delta_lon
            
            min_lat = min(min_lat, point_min_lat)
            max_lat = max(max_lat, point_max_lat)
            min_lon = min(min_lon, point_min_lon)
            max_lon = max(max_lon, point_max_lon)
        
        return (min_lat, max_lat, min_lon, max_lon)

    @classmethod
    def _filter_dev(cls, route_points: List[tuple], width: float) -> List[dict]:
        """
        Development mode: Bounding‑box + Haversine filtering.
        
        Optimisation:
        1. Compute bounding box around the route (expanded by width).
        2. Query only stations with latitude/longitude inside that box.
        3. For each candidate, perform exact corridor check.
        """
        from utils.geospatial import (
            find_closest_point_on_route,
            calculate_route_distance,
        )
        
        # Step 1: bounding box
        min_lat, max_lat, min_lon, max_lon = cls._compute_route_bbox(route_points, width)
        
        # Step 2: database filtering using actual column names
        candidate_stations = FuelStation.objects.filter(
            latitude__gte=min_lat, latitude__lte=max_lat,
            longitude__gte=min_lon, longitude__lte=max_lon
        )
        
        total_before = FuelStation.objects.count()
        candidate_count = candidate_stations.count()
        logger.debug(
            f"Bounding box reduced stations from {total_before} to {candidate_count} candidates"
        )
        
        # Step 3: precise check
        results = []
        for station in candidate_stations.iterator():
            # is_point_near_route expects (lat, lon)
            if is_point_near_route(float(station.latitude), float(station.longitude), route_points, width):
                closest_idx, _ = find_closest_point_on_route(
                    float(station.latitude), float(station.longitude), route_points
                )
                distance_from_start = calculate_route_distance(
                    route_points[:closest_idx + 1]
                )
                
                results.append({
                    'id': station.id,
                    'truckstop_id': station.truckstop_id,
                    'name': station.name,
                    'city': station.city,
                    'state': station.state,
                    'latitude': station.latitude,
                    'longitude': station.longitude,
                    'retail_price': station.retail_price,
                    'distance_from_start': round(distance_from_start, 2),
                })
        
        results.sort(key=lambda x: x['distance_from_start'])
        logger.info(f"Development mode: found {len(results)} stations near route")
        return results

    @classmethod
    def _filter_prod(cls, route_points: List[tuple], width: float) -> List[dict]:
        """
        Production mode: PostGIS ST_DWithin spatial query.
        
        Assumes FuelStation has a `location` PointField (created from latitude/longitude).
        """
        from django.contrib.gis.geos import LineString
        from django.contrib.gis.measure import D
        
        route_line = LineString(
            [(lon, lat) for lat, lon in route_points],
            srid=4326
        )
        
        stations = FuelStation.objects.filter(
            location__dwithin=(route_line, D(mi=width))
        )
        
        results = []
        for station in stations:
            from utils.geospatial import find_closest_point_on_route, calculate_route_distance
            
            closest_idx, _ = find_closest_point_on_route(
                float(station.latitude), float(station.longitude), route_points
            )
            distance_from_start = calculate_route_distance(
                route_points[:closest_idx + 1]
            )
            
            results.append({
                'id': station.id,
                'truckstop_id': station.truckstop_id,
                'name': station.name,
                'city': station.city,
                'state': station.state,
                'latitude': station.latitude,
                'longitude': station.longitude,
                'retail_price': station.retail_price,
                'distance_from_start': round(distance_from_start, 2),
            })
        
        logger.info(f"Production mode: found {len(results)} stations near route")
        return results

    @classmethod
    def get_station_by_id(cls, station_id: int) -> Optional[dict]:
        """
        Retrieve a single station by ID.
        """
        try:
            station = FuelStation.objects.get(id=station_id)
            return {
                'id': station.id,
                'truckstop_id': station.truckstop_id,
                'name': station.name,
                'city': station.city,
                'state': station.state,
                'latitude': station.latitude,
                'longitude': station.longitude,
                'retail_price': station.retail_price,
            }
        except FuelStation.DoesNotExist:
            return None