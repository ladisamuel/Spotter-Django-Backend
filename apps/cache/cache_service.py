"""
CacheService abstraction layer.

Provides a backend-agnostic caching interface. The rest of the application
uses this service without knowing whether LocMemCache (dev) or Redis (prod)
is active underneath.

Cache key format: route:{normalized_start}:{normalized_destination}
Default TTL: 24 hours (86400 seconds)
"""

import hashlib
import json
import logging
from typing import Any, Optional

from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class CacheService:
    """
    Abstraction over Django's cache framework.
    
    Automatically uses the configured cache backend (LocMemCache in dev,
    Redis in prod) without the calling code needing to know the difference.
    
    Cache Strategy:
    - Key format: route:{start}:{destination} (normalized, lowercase, trimmed)
    - TTL: 24 hours to balance freshness with API cost reduction
    - Serialization: JSON for complex objects
    - Fallback: On cache failure, log warning and proceed without cache
    """

    DEFAULT_TTL = getattr(settings, 'CACHE_TTL_SECONDS', 86400)
    KEY_PREFIX = 'route'

    @classmethod
    def _normalize_key(cls, start: str, destination: str) -> str:
        """
        Create a deterministic cache key from start/destination.
        
        Normalization ensures that "New York, United States" and "new york, united states"
        map to the same cache key.
        """
        normalized_start = start.strip().lower().replace(' ', '_')
        normalized_dest = destination.strip().lower().replace(' ', '_')
        
        # Use hash for very long strings to keep key length reasonable
        raw = f"{normalized_start}:{normalized_dest}"
        if len(raw) > 200:
            hash_part = hashlib.md5(raw.encode()).hexdigest()[:16]
            raw = f"hash:{hash_part}"
        
        return f"{cls.KEY_PREFIX}:{raw}"

    @classmethod
    def get(cls, start: str, destination: str) -> Optional[dict]:
        """
        Retrieve cached route result.
        
        Args:
            start: Start location string
            destination: Destination location string
        
        Returns:
            Cached result dict or None if not found/expired
        """
        key = cls._normalize_key(start, destination)
        
        try:
            cached = cache.get(key)
            if cached is not None:
                logger.info(f"Cache HIT for key: {key}")
                # Handle both JSON-serialized strings and raw dicts
                if isinstance(cached, str):
                    return json.loads(cached)
                return cached
            logger.info(f"Cache MISS for key: {key}")
            return None
        except Exception as e:
            logger.warning(f"Cache read error for key {key}: {e}")
            return None

    @classmethod
    def set(cls, start: str, destination: str, value: dict, ttl: int = None) -> bool:
        """
        Store route result in cache.
        
        Args:
            start: Start location string
            destination: Destination location string
            value: Result dictionary to cache
            ttl: Time-to-live in seconds (defaults to 24 hours)
        
        Returns:
            True if cached successfully, False on failure
        """
        key = cls._normalize_key(start, destination)
        ttl = ttl or cls.DEFAULT_TTL
        
        try:
            # Serialize to JSON string for cross-backend compatibility
            serialized = json.dumps(value, default=str)
            cache.set(key, serialized, timeout=ttl)
            logger.info(f"Cache SET for key: {key} (TTL={ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"Cache write error for key {key}: {e}")
            return False

    @classmethod
    def delete(cls, start: str, destination: str) -> bool:
        """
        Remove a cached entry.
        
        Args:
            start: Start location string
            destination: Destination location string
        
        Returns:
            True if deleted or not found, False on error
        """
        key = cls._normalize_key(start, destination)
        
        try:
            cache.delete(key)
            logger.info(f"Cache DELETE for key: {key}")
            return True
        except Exception as e:
            logger.warning(f"Cache delete error for key {key}: {e}")
            return False

    @classmethod
    def clear_all(cls) -> bool:
        """
        Clear all cached route entries. Use with caution.
        
        Returns:
            True if cleared successfully
        """
        try:
            cache.clear()
            logger.info("Cache cleared")
            return True
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return False
