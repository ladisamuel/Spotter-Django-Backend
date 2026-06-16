 
import hashlib
import json
import logging
from typing import Any, Optional

from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class CacheService: 

    DEFAULT_TTL = getattr(settings, 'CACHE_TTL_SECONDS', 86400)
    KEY_PREFIX = 'route'

    @classmethod
    def _normalize_key(cls, start: str, destination: str) -> str:
 
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
         
        try:
            cache.clear()
            logger.info("Cache cleared")
            return True
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return False
