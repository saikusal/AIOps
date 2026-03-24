# genai/semantic_cache.py
import os
import json
import logging
import redis

logger = logging.getLogger("genai")

# --- Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
CACHE_TTL = 604800  # Time to live for cache entries, in seconds (7 days)

class SimpleCache:
    """
    A simple key-value cache using Redis.
    It stores results using the exact question as the key.
    """
    def __init__(self):
        self.client = None
        self.is_initialized = False

    def initialize(self):
        """
        Connects to the Redis server.
        """
        if self.is_initialized:
            return

        logger.info("Initializing Simple Redis Cache...")
        try:
            # Use the standard redis.Redis client, ensuring decode_responses=True
            self.client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            self.client.ping()
            logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            self.is_initialized = True
            logger.info("Simple Redis Cache initialization complete.")

        except Exception as e:
            logger.error(f"CRITICAL: Simple Redis Cache failed to initialize: {e}", exc_info=True)
            self.is_initialized = False

    def add(self, question: str, answer_data: dict):
        """
        Adds a new question and its answer to the cache.
        """
        if not self.is_initialized or not question:
            return

        try:
            cache_key = f"cache:{question.lower().strip()}"
            self.client.set(cache_key, json.dumps(answer_data), ex=CACHE_TTL)
            logger.info(f"SUCCESS: Stored result in cache for key: '{cache_key}'")
        except Exception as e:
            logger.error(f"Failed to add to simple cache: {e}", exc_info=True)

    def search(self, question: str) -> dict | None:
        """
        Searches the cache for an exact match for the question.
        Logs a hit if found.
        """
        if not self.is_initialized or not question:
            return None

        try:
            cache_key = f"cache:{question.lower().strip()}"
            result = self.client.get(cache_key)

            if result:
                logger.info(f"CACHE HIT: Found result in cache for key: '{cache_key}'")
                return json.loads(result)
            else:
                logger.info(f"CACHE MISS: No result in cache for key: '{cache_key}'")
                return None

        except Exception as e:
            logger.error(f"Failed to search simple cache: {e}", exc_info=True)
            return None

    def delete(self, question: str):
        """
        Deletes a key from the cache.
        """
        if not self.is_initialized or not question:
            return

        try:
            cache_key = f"cache:{question.lower().strip()}"
            deleted_count = self.client.delete(cache_key)
            if deleted_count > 0:
                logger.info(f"SUCCESS: Deleted key from cache: '{cache_key}'")
            else:
                logger.info(f"Key not found in cache for deletion: '{cache_key}'")
        except Exception as e:
            logger.error(f"Failed to delete from simple cache: {e}", exc_info=True)


# A single, global instance of the cache, named to be clear about its purpose.
simple_cache = SimpleCache()
