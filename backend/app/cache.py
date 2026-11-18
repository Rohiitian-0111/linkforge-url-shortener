import hashlib
import json
import logging
import time
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

SET_IF_GENERATION_MATCHES = """
local generation = redis.call('GET', KEYS[2]) or '0'
if generation == ARGV[1] then
  redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
  return 1
end
return 0
"""
INVALIDATE = """
redis.call('INCR', KEYS[2])
redis.call('DEL', KEYS[1])
return 1
"""
RATE_LIMIT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then redis.call('EXPIRE', KEYS[1], ARGV[1]); ttl = tonumber(ARGV[1]) end
return {count, ttl}
"""


class URLCache:
    def __init__(self, redis_client, ttl: int, metrics):
        self.redis = redis_client
        self.ttl = ttl
        self.metrics = metrics

    @staticmethod
    def keys(code: str):
        # A hash tag also keeps the two Lua keys in one Redis Cluster slot.
        return f"linkforge:url:{{{code}}}:data", f"linkforge:url:{{{code}}}:generation"

    async def read(self, code: str) -> tuple[dict | None, str | None]:
        if self.redis is None:
            self.metrics.cache.labels("disabled").inc()
            return None, None
        try:
            data, generation = await self.redis.mget(*self.keys(code))
            if isinstance(generation, bytes):
                generation = generation.decode()
            value = json.loads(data) if data else None
            if value and not {"id", "original_url", "is_active", "expires_at"}.issubset(value):
                value = None
            if value:
                UUID(value["id"])
                if not isinstance(value["is_active"], bool) or not isinstance(value["original_url"], str):
                    raise ValueError("Invalid cached mapping")
                if not value["original_url"].startswith(("http://", "https://")):
                    raise ValueError("Invalid cached destination")
                if value["expires_at"] is not None:
                    expiry = datetime.fromisoformat(value["expires_at"])
                    if expiry.tzinfo is None:
                        raise ValueError("Invalid cached expiry")
            self.metrics.cache.labels("hit" if value else "miss").inc()
            return value, generation or "0"
        except (RedisError, ValueError, TypeError, AttributeError):
            self.metrics.redis_errors.labels("cache_read").inc()
            self.metrics.cache.labels("error").inc()
            return None, None

    async def store(self, code: str, payload: dict, generation: str | None):
        if self.redis is None or generation is None:
            return
        try:
            await self.redis.eval(SET_IF_GENERATION_MATCHES, 2, *self.keys(code), generation, json.dumps(payload), self.ttl)
        except RedisError:
            self.metrics.redis_errors.labels("cache_write").inc()

    async def invalidate(self, code: str) -> bool:
        if self.redis is None:
            return False
        try:
            await self.redis.eval(INVALIDATE, 2, *self.keys(code))
            return True
        except RedisError:
            self.metrics.redis_errors.labels("cache_invalidate").inc()
            logger.warning("cache_invalidation_failed; stale entries expire within cache TTL")
            return False


class RateLimiter:
    def __init__(self, redis_client, settings, metrics):
        self.redis = redis_client
        self.settings = settings
        self.metrics = metrics
        self.local: dict[str, tuple[int, float]] = {}

    async def check(self, category: str, identity: str, limit: int, window_seconds: int):
        if not self.settings.rate_limit_enabled:
            return
        digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
        key = f"linkforge:limit:{category}:{digest}"
        try:
            if self.redis is None:
                raise RedisError("Redis disabled")
            count, ttl = await self.redis.eval(RATE_LIMIT, 1, key, window_seconds)
        except RedisError:
            self.metrics.redis_errors.labels("rate_limit").inc()
            if self.settings.environment == "production":
                raise HTTPException(503, "Rate limiting temporarily unavailable. Try again shortly.", headers={"Retry-After": "5"})
            # Development-only fallback. Never pretend this coordinates multiple processes.
            now = time.monotonic()
            if len(self.local) > 10000:
                self.local = {k: v for k, v in self.local.items() if v[1] > now}
            count, until = self.local.get(key, (0, now + window_seconds))
            if until <= now:
                count, until = 0, now + window_seconds
            count += 1
            self.local[key] = (count, until)
            ttl = max(1, int(until - now + 0.999))
        if int(count) > limit:
            raise HTTPException(429, "Too many requests. Please try again later.", headers={"Retry-After": str(max(1, int(ttl)))})
