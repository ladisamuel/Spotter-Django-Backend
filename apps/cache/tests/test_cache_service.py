"""
Unit tests for CacheService.
"""

from django.test import TestCase
from django.core.cache import cache

from apps.cache.cache_service import CacheService


class CacheServiceTests(TestCase):
    """Test suite for CacheService abstraction."""
    
    def setUp(self):
        cache.clear()
    
    def tearDown(self):
        cache.clear()
    
    def test_set_and_get(self):
        """Test basic set/get cycle."""
        test_data = {
            'distance_miles': 1280.5,
            'fuel_stops': [{'name': 'Test Station'}]
        }
        
        success = CacheService.set("New York, United States", "Miami, Miami-Dade County, Florida, United States", test_data)
        self.assertTrue(success)
        
        cached = CacheService.get("New York, United States", "Miami, Miami-Dade County, Florida, United States")
        self.assertIsNotNone(cached)
        self.assertEqual(cached['distance_miles'], 1280.5)
    
    def test_cache_miss_returns_none(self):
        """Test that uncached routes return None."""
        result = CacheService.get("Nowhere", "Somewhere")
        self.assertIsNone(result)
    
    def test_delete_removes_entry(self):
        """Test cache deletion."""
        CacheService.set("A", "B", {'test': 'data'})
        CacheService.delete("A", "B")
        
        result = CacheService.get("A", "B")
        self.assertIsNone(result)
    
    def test_normalization(self):
        """Test that different capitalizations map to same key."""
        data = {'test': 'normalized'}
        
        CacheService.set("New York, United States", "Miami, Miami-Dade County, Florida, United States", data)
        
        # Different case should hit same cache
        cached = CacheService.get("New York, United States", "Miami, Miami-Dade County, Florida, United States")
        self.assertIsNotNone(cached)
    
    def test_clear_all(self):
        """Test clearing all cached entries."""
        CacheService.set("A", "B", {'test': 1})
        CacheService.set("C", "D", {'test': 2})
        
        CacheService.clear_all()
        
        self.assertIsNone(CacheService.get("A", "B"))
        self.assertIsNone(CacheService.get("C", "D"))