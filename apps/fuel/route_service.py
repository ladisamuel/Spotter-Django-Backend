"""
RouteService - OSRM integration with single-request policy.

This service is responsible for:
1. Geocoding location strings to coordinates (via Nominatim/OSRM)
2. Making a single OSRM route API request per route
3. Extracting distance, duration, and encoded geometry
4. Handling retries, timeouts, and error cases

Design Decision: One route API request per route.
- OSRM is called exactly once for each unique start/destination pair
- Route geometry is decoded once and reused for all downstream processing
- This minimizes external API usage and cost
"""

import logging
import time
from typing import Tuple, Optional
from urllib.parse import quote

import requests
from django.conf import settings

from utils.exceptions import (
    InvalidLocationError,
    NoRouteError,
    RoutingAPIError,
)

logger = logging.getLogger(__name__)


class RouteService: 

    OSRM_BASE_URL = getattr(settings, 'OSRM_BASE_URL', 'http://router.project-osrm.org')
    OSRM_ENDPOINT = getattr(settings, 'OSRM_ROUTE_ENDPOINT', '/route/v1/driving/')
    TIMEOUT = getattr(settings, 'OSRM_REQUEST_TIMEOUT', 30)
    MAX_RETRIES = getattr(settings, 'OSRM_MAX_RETRIES', 2)

    @classmethod
    def geocode_location(cls, location: str) -> Tuple[float, float]:
         
        try:
            query = quote(location)
            url = f"https://nominatim.openstreetmap.org/search?q={query}&format=jsonv2&limit=1"
            
            sample_res = [
                {
                    "place_id": 359971500,
                    "licence": "Data © OpenStreetMap contributors, ODbL 1.0. http://osm.org/copyright",
                    "osm_type": "relation",
                    "osm_id": 175905,
                    "lat": "40.7127281",
                    "lon": "-74.0060152",
                    "class": "boundary",
                    "type": "administrative",
                    "place_rank": 10,
                    "importance": 0.8817923363604117,
                    "addresstype": "city",
                    "name": "New York",
                    "display_name": "New York, United States",
                    "boundingbox": [
                        "40.4765780",
                        "40.9176300",
                        "-74.2588430",
                        "-73.7002330"
                        ]
                    }
                ]
            
            
            print('\n\n\ url', url)
            headers = {
                # 'User-Agent': 'RouteOptimizer/1.0 (assessment@example.com)',
                
                "User-Agent": "SpotterRouteOptimizer/1.0 (contact: ladisamuel00@gmail.com)"

            }
            
            response = requests.get(url, headers=headers, timeout=15)
            print('\n\n\ response', response)
            
            response.raise_for_status()
            print('\n\n\ response2', response)
            
            data = response.json()
            


            print('\n\n\ data json', data)
            print('\n\n\ check data', data == sample_res)
            
            
            if not data:    
                print('\n\n\ data not existing', )
                raise InvalidLocationError(
                    f"Location '{location}' could not be found. "
                    "Please check the spelling and try again."
                )
            
            lat = float(data[0]['lat'])
            print('\n\n\ lat', lat)
            lon = float(data[0]['lon'])
            print('\n\n\ lon', lon)

            logger.info(f"Geocoded '{location}' -> ({lat}, {lon})")
            return (lat, lon)
            
        except InvalidLocationError:
            raise
        except Exception as e:
            logger.error(f"Geocoding failed for '{location}': {e}")
            raise InvalidLocationError(
                f"Unable to resolve location '{location}'. "
                f"Error: {str(e)}"
            )

    @classmethod
    def get_route(
        cls,
        start: str,
        destination: str
    ) -> dict: 
        
        logger.info(f"Computing route: '{start}' -> '{destination}'")
        
        print('\n\n\ Geocoding start', )
        start_coords = cls.geocode_location(start)
        end_coords = cls.geocode_location(destination)
        
        print('Geocoding done', )        
        
        
        print('Geocoding done', )        
        if abs(start_coords[0] - end_coords[0]) < 0.001 and abs(start_coords[1] - end_coords[1]) < 0.001:
            print('\n\n validate they are not same point', )          
            raise InvalidLocationError(
                "Start and destination are too close or identical."
            )
        
        coords = f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
        url = (
            f"{cls.OSRM_BASE_URL}{cls.OSRM_ENDPOINT}{coords}"
            f"?overview=full&geometries=polyline"
        )
        
        logger.info(f"OSRM request: {url}")
        
        last_error = None
        for attempt in range(cls.MAX_RETRIES + 1):
            try:
                response = requests.get(url, timeout=cls.TIMEOUT)
                response.raise_for_status()
                
                data = response.json()
                
                print('\n\n get route data', data)
                
                if data.get('code') != 'Ok':
                    if data.get('code') == 'NoRoute':
                        raise NoRouteError(
                            f"No drivable route found between '{start}' and "
                            f"'{destination}'. The locations may be on "
                            f"disconnected road networks."
                        )
                    raise RoutingAPIError(
                        f"OSRM returned error code: {data.get('code')}"
                    )
                
                route = data['routes'][0]
                
                distance_meters = route['distance']
                distance_miles = distance_meters / 1609.344
                
                print('\n\n\ distance_miles', distance_miles)
                
                duration_seconds = route['duration']
                print('\n\n\ duration_seconds for driving', duration_seconds)
                
                geometry = route['geometry']
                
                result = {
                    'distance_miles': round(distance_miles, 2),
                    'duration_seconds': round(duration_seconds, 0),
                    'geometry': geometry,
                    'start_coords': start_coords,
                    'end_coords': end_coords,
                }
                
                logger.info(
                    f"Route computed: {distance_miles:.1f} miles, "
                    f"{duration_seconds/3600:.1f} hours"
                )
                return result
                
            except (NoRouteError, InvalidLocationError):
                raise
            except requests.exceptions.Timeout:
                logger.warning(f"OSRM timeout (attempt {attempt + 1}/{cls.MAX_RETRIES + 1})")
                last_error = "timeout"
                if attempt < cls.MAX_RETRIES:
                    time.sleep(2 ** attempt)  # Exponential backoff
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"OSRM request error (attempt {attempt + 1}/{cls.MAX_RETRIES + 1}): {e}"
                )
                last_error = str(e)
                if attempt < cls.MAX_RETRIES:
                    time.sleep(2 ** attempt)
        
        raise RoutingAPIError(
            f"Routing service failed after {cls.MAX_RETRIES + 1} attempts. "
            f"Last error: {last_error}"
        )
