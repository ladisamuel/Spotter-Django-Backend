"""
Unit tests for FuelService.
"""

from django.test import TestCase, override_settings

from apps.fuel.models import FuelStation
from apps.fuel.fuel_service import FuelService
from utils.exceptions import EmptyDatasetError


@override_settings(DEBUG=True, ROUTE_CORRIDOR_WIDTH_MILES=50)
class FuelServiceDevTests(TestCase):
    """Test FuelService in development mode (Haversine filtering)."""
    
    def setUp(self):
        # Create test stations along a hypothetical route
        # Route: roughly I-95 from NYC to Miami
        self.route_points = [
            (40.7128, -74.0060),   # NYC
            (39.9526, -75.1652),   # Philadelphia
            (38.9072, -77.0369),   # DC
            (36.8508, -76.2859),   # Norfolk
            (35.7796, -78.6382),   # Raleigh
            (33.7490, -84.3880),   # Atlanta
            (30.3322, -81.6557),   # Jacksonville
            (25.7617, -80.1918),   # Miami
        ]
        
        # Create stations near the route
        FuelStation.objects.create(
            truckstop_id=1,
            name="Test Station Philly",
            city="Philadelphia",
            state="PA",
            latitude=39.95,
            longitude=-75.16,
            retail_price=3.50,
        )
        FuelStation.objects.create(
            truckstop_id=2,
            name="Test Station DC",
            city="Washington",
            state="DC",
            latitude=38.90,
            longitude=-77.03,
            retail_price=3.25,
        )
        # Station far from route
        FuelStation.objects.create(
            truckstop_id=3,
            name="Far Away Station",
            city="Chicago",
            state="IL",
            latitude=41.87,
            longitude=-87.62,
            retail_price=3.00,
        )
    
    def test_get_stations_near_route_finds_nearby(self):
        """Test that nearby stations are found."""
        stations = FuelService.get_stations_near_route(self.route_points)
        
        # Should find Philly and DC, not Chicago
        self.assertEqual(len(stations), 2)
        names = [s['name'] for s in stations]
        self.assertIn("Test Station Philly", names)
        self.assertIn("Test Station DC", names)
        self.assertNotIn("Far Away Station", names)
    
    def test_get_stations_sorted_by_distance(self):
        """Test that results are sorted by distance from start."""
        stations = FuelService.get_stations_near_route(self.route_points)
        
        self.assertEqual(len(stations), 2)
        # Philly should be before DC
        self.assertLess(
            stations[0]['distance_from_start'],
            stations[1]['distance_from_start']
        )
    
    def test_empty_dataset_raises_error(self):
        """Test that empty database raises EmptyDatasetError."""
        FuelStation.objects.all().delete()
        
        with self.assertRaises(EmptyDatasetError):
            FuelService.get_stations_near_route(self.route_points)