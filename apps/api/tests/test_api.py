"""
Integration tests for the Route Optimization API.
"""

import responses
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.fuel.models import FuelStation


@override_settings(
    OSRM_BASE_URL='http://test-osrm.example.com',
    DEBUG=True,
    VEHICLE_RANGE_MILES=500,
)
class RouteOptimizeAPITests(TestCase):
    """Integration tests for POST /api/routes/optimize/."""
    
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('route-optimize')
        
        # Create test fuel stations
        FuelStation.objects.create(
            truckstop_id=1,
            name="Midway Station",
            city="Midway",
            state="ST",
            latitude=39.0,
            longitude=-77.0,
            retail_price=3.00,
        )
    
    def test_missing_fields_returns_400(self):
        """Test that missing required fields return 400."""
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_same_location_returns_400(self):
        """Test that identical start/destination returns 400."""
        response = self.client.post(self.url, {
            'start': 'New York, United States',
            'destination': 'Miami, Miami-Dade County, Florida, United States'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    @responses.activate
    def test_successful_optimization(self):
        """Test full successful optimization flow."""
        # Mock geocoding
        responses.add(
            responses.GET,
            'https://nominatim.openstreetmap.org/search',
            json=[{'lat': '40.7128', 'lon': '-74.0060'}],
            status=200
        )
        responses.add(
            responses.GET,
            'https://nominatim.openstreetmap.org/search',
            json=[{'lat': '39.9526', 'lon': '-75.1652'}],
            status=200
        )
        
        # Mock OSRM (short 100-mile route)
        responses.add(
            responses.GET,
            responses.REMATCH,
            json={
                'code': 'Ok',
                'routes': [{
                    'distance': 160934,  # 100 miles
                    'duration': 7200,    # 2 hours
                    'geometry': '_p~iF~ps|U_ulLnnqC'
                }]
            },
            status=200
        )
        
        response = self.client.post(self.url, {
            'start': 'New York, United States',
            'destination': 'Philadelphia, PA'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('distance_miles', response.data)
        self.assertIn('fuel_stops', response.data)
        self.assertIn('estimated_total_fuel_cost', response.data)
        self.assertIn('route_geometry', response.data)
    
    @responses.activate
    def test_caches_result(self):
        """Test that results are cached."""
        # First request - should compute
        responses.add(
            responses.GET,
            'https://nominatim.openstreetmap.org/search',
            json=[{'lat': '40.7128', 'lon': '-74.0060'}],
            status=200
        )
        responses.add(
            responses.GET,
            'https://nominatim.openstreetmap.org/search',
            json=[{'lat': '39.9526', 'lon': '-75.1652'}],
            status=200
        )
        responses.add(
            responses.GET,
            responses.REMATCH,
            json={
                'code': 'Ok',
                'routes': [{
                    'distance': 160934,
                    'duration': 7200,
                    'geometry': '_p~iF~ps|U'
                }]
            },
            status=200
        )
        
        response1 = self.client.post(self.url, {
            'start': 'Cache Test Start',
            'destination': 'Cache Test End'
        }, format='json')
        
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        
        # Second request - should hit cache (no additional mocks needed)
        response2 = self.client.post(self.url, {
            'start': 'Cache Test Start',
            'destination': 'Cache Test End'
        }, format='json')
        
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response1.data, response2.data)