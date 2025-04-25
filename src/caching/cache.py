import redis
import json
from typing import Optional, Any
from src.config import settings
from src.logging.logger import get_logger

logger = get_logger(__name__)

class RedisCache:
    """Simple Redis Cache client."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        # Singleton pattern for the cache connection
        if cls._instance is None:
            logger.info("Initializing Redis connection pool...")
            try:
                pool = redis.ConnectionPool(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    password=settings.REDIS_PASSWORD,
                    decode_responses=True # Decode responses to strings automatically
                )
                cls._instance = super(RedisCache, cls).__new__(cls)
                cls._instance.client = redis.Redis(connection_pool=pool)
                # Test connection
                cls._instance.client.ping()
                logger.info("Redis connection successful.")
            except redis.exceptions.ConnectionError as e:
                logger.error(f"Failed to connect to Redis: {e}")
                # Depending on requirements, you might want to raise the error
                # or allow the app to start with caching disabled (more complex).
                raise e # Fail fast if cache is essential
        return cls._instance

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache."""
        try:
            value = self.client.get(key)
            if value:
                logger.debug(f"Cache HIT for key: {key}")
                try:
                    # Attempt to deserialize if it looks like JSON
                    return json.loads(value)
                except json.JSONDecodeError:
                    # Return as plain string if not JSON
                    return value
            logger.debug(f"Cache MISS for key: {key}")
            return None
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None # Treat cache errors as misses

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set a value in the cache with an optional TTL (in seconds)."""
        try:
            # Serialize if it's not a simple string/bytes
            if not isinstance(value, (str, bytes, int, float)):
                value = json.dumps(value)

            effective_ttl = ttl if ttl is not None else settings.SCHEMA_CACHE_TTL
            self.client.set(key, value, ex=effective_ttl)
            logger.debug(f"Cache SET for key: {key} with TTL: {effective_ttl}s")
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis SET error for key {key}: {e}")
        except TypeError as e:
             logger.error(f"Serialization error for key {key}: {e}")


# Global cache instance
try:
    cache_client = RedisCache()
except Exception:
    logger.error("Failed to initialize Redis cache client on module load.")
    cache_client = None # Allow import but client will be None if connection failed

def get_cache_client() -> Optional[RedisCache]:
    """Dependency function to get the cache client."""
    if cache_client is None:
        logger.warning("Attempting to use cache, but client is not initialized.")
    return cache_client 