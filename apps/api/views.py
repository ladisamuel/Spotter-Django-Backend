 

import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError

from django.conf import settings

from apps.api.serializers import (
    RouteOptimizeRequestSerializer,
    RouteOptimizeResponseSerializer,
)
from apps.cache.cache_service import CacheService
from apps.fuel.route_service import RouteService
from apps.fuel.optimization_service import OptimizationService
from utils.exceptions import RouteOptimizerError

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
 
    from rest_framework.views import exception_handler
    
    # First, let DRF handle standard exceptions
    response = exception_handler(exc, context)
    
    if response is not None:
        return response
    
    # Handle our custom exceptions
    if isinstance(exc, RouteOptimizerError):
        return Response(
            {
                'error': exc.__class__.__name__,
                'detail': exc.detail,
            },
            status=exc.status_code
        )
    
    # Fallback for unexpected errors
    logger.exception("Unhandled exception in API")
    return Response(
        {
            'error': 'InternalServerError',
            'detail': 'An unexpected error occurred. Please try again later.',
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


class RouteOptimizeView(APIView):
    """
    POST /routes/
    
    Compute optimal driving route with fuel stops.
    
    Request Body:
        {
            "start": "New York, United States",
            "destination": "Miami, Miami-Dade County, Florida, United States"
        }
    
    Response:
        {
            "start": "New York, United States",
            "destination": "Miami, Miami-Dade County, Florida, United States",
            "distance_miles": 1280.5,
            "duration_seconds": 72000,
            "fuel_stops": [
                {
                    "station_name": "Pilot Travel Center #1243",
                    "city": "Gila Bend",
                    "state": "AZ",
                    "price": 3.899,
                    "distance_from_start": 460.2
                }
            ],
            "estimated_total_fuel_cost": 378.45,
            "route_geometry": "{encoded_polyline_string}"
        }
    """
    
    def post(self, request):
        # Step 1: Validate request
        print('\n\n\ Api view', )
        
        serializer = RouteOptimizeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        start = serializer.validated_data['start']
        destination = serializer.validated_data['destination']
        
        logger.info(f"Optimization request: '{start}' -> '{destination}'")
        
        # Step 2: Check cache
        cached = CacheService.get(start, destination)
        if cached:
            logger.info("Returning cached result")
            return Response(cached, status=status.HTTP_200_OK)
        
        # Step 3: Compute route (single OSRM request)
        try:
            route_result = RouteService.get_route(start, destination)
            print('\n\n\ route_result', route_result)
        except Exception:
            raise  # Let exception handler deal with it
        
        # Step 4: Optimize fuel stops
        try:
            optimization = OptimizationService.optimize_fuel_stops(
                route_geometry=route_result['geometry'],
                route_distance_miles=route_result['distance_miles'],
            )
            print('\n\n\ optimization', optimization)
            
        except Exception:
            raise
        
        # Step 5: Build response
        response_data = {
            'start': start,
            'destination': destination,
            'distance_miles': route_result['distance_miles'],
            'duration_seconds': int(route_result['duration_seconds']),
            'duration_mins': round(int(route_result['duration_seconds'])/60, 2),
            'fuel_stops_count': len(optimization['fuel_stops']),
            'fuel_stops': [
                {
                    'station_name': stop['station_name'],
                    'city': stop['city'],
                    'state': stop['state'],
                    'price': stop['price'],
                    'distance_from_start': stop['distance_from_start'],
                }
                for stop in optimization['fuel_stops']
            ],
            'estimated_total_fuel_cost': optimization['total_fuel_cost'],
            # 'route_geometry': route_result['geometry'],
        }
        
        # Step 6: Cache result
        CacheService.set(start, destination, response_data)
        
        
        print('\n\n\ ', )
        
        # Step 7: Return response
        return Response(response_data, status=status.HTTP_200_OK)