"""Two-tier caching architecture with L1 in-process and optional L2 distributed Redis.

Features:
- L1 in-memory TTLCache (microsecond lookups for burst concurrency).
- Optional L2 Redis cache (shared across horizontal Cloud Run instances).
- SingleFlight async lock coalescing to prevent thundering-herd 429 rate limits.
- Version-aware deterministic key hashing for automatic cache invalidation.
- Graceful degradation if Redis is unavailable or unconfigured.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from cachetools import TTLCache as CachetoolsTTLCache

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class SingleFlight:
    """Async request coalescing lock map to deduplicate identical concurrent operations."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._in_flight: dict[str, asyncio.Future[Any]] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    async def execute(
        self,
        key: str,
        coro_fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Execute coro_fn once for key, sharing the resulting future among concurrent callers."""
        async with self._lock:
            if key in self._in_flight:
                future = self._in_flight[key]
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._in_flight[key] = future
                task = asyncio.create_task(self._run(key, future, coro_fn))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

        return await asyncio.shield(future)

    async def _run(
        self,
        key: str,
        future: asyncio.Future[Any],
        coro_fn: Callable[[], Awaitable[Any]],
    ) -> None:
        try:
            result = await coro_fn()
        except asyncio.CancelledError:
            async with self._lock:
                if self._in_flight.get(key) is future:
                    del self._in_flight[key]
                if not future.done():
                    future.cancel()
            raise
        except Exception as exc:
            async with self._lock:
                if self._in_flight.get(key) is future:
                    del self._in_flight[key]
                if not future.done():
                    future.set_exception(exc)
        else:
            async with self._lock:
                if self._in_flight.get(key) is future:
                    del self._in_flight[key]
                if not future.done():
                    future.set_result(result)


class TwoTierFigmaCache:
    """Two-tier cache: in-memory L1 TTLCache + optional distributed L2 Redis."""

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        l1_ttl_seconds: float = 60.0,
        l1_max_size: int = 512,
        default_ttl: float | None = None,
        maxsize: int | None = None,
    ) -> None:
        effective_ttl = default_ttl if default_ttl is not None else l1_ttl_seconds
        effective_maxsize = maxsize if maxsize is not None else l1_max_size
        self._default_ttl = effective_ttl
        self._l1: CachetoolsTTLCache[str, Any] = CachetoolsTTLCache(
            maxsize=effective_maxsize,
            ttl=effective_ttl,
        )
        self._l1_lock = asyncio.Lock()
        self._single_flight = SingleFlight()
        self._redis_client: Any | None = None
        self._redis_url = redis_url

        if redis_url and redis is not None:
            try:
                self._redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0,
                )
                logger.info("Configured L2 Redis cache at %s", redis_url.split("@")[-1])
            except Exception as exc:
                logger.warning("Failed to initialize Redis client, falling back to L1: %s", exc)
                self._redis_client = None

    @property
    def has_l2(self) -> bool:
        return self._redis_client is not None

    @staticmethod
    def make_key(tool: str, file_key: str, version: str, **params: Any) -> str:
        """Construct a deterministic version-aware cache key."""
        canonical = json.dumps(params, sort_keys=True, default=str)
        param_hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]
        return f"figma:v1:{tool}:{file_key}:{version}:{param_hash}"

    async def get(self, key: str) -> Any | None:
        """Lookup in L1, then L2. Promotes L2 hits to L1."""
        # 1. Check L1 in-process
        async with self._l1_lock:
            if key in self._l1:
                return self._l1[key]

        # 2. Check L2 distributed Redis if available
        if self._redis_client is not None:
            try:
                raw = await self._redis_client.get(key)
                if raw:
                    data = json.loads(raw)
                    async with self._l1_lock:
                        self._l1[key] = data
                    return data
            except Exception as exc:
                logger.warning("L2 Redis read error for %s: %s", key, exc)

        return None

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int = 86400,
    ) -> None:
        """Store value in L1 and L2 asynchronously."""
        async with self._l1_lock:
            self._l1[key] = value

        if self._redis_client is not None:
            try:
                raw = json.dumps(value)
                await self._redis_client.setex(key, ttl_seconds, raw)
            except Exception as exc:
                logger.warning("L2 Redis write error for %s: %s", key, exc)

    async def get_or_set(
        self,
        key: str,
        coro_fn: Callable[[], Awaitable[Any]],
        *,
        ttl_seconds: int = 86400,
        force_refresh: bool = False,
    ) -> Any:
        """Get cached value or execute coro_fn through SingleFlight lock coalescing."""
        if not force_refresh:
            cached = await self.get(key)
            if cached is not None:
                return cached

        async def _fetch_and_store() -> Any:
            val = await coro_fn()
            await self.set(key, val, ttl_seconds=ttl_seconds)
            return val

        return await self._single_flight.execute(key, _fetch_and_store)

    async def aclose(self) -> None:
        """Close L2 Redis connection pool."""
        if self._redis_client is not None:
            try:
                await self._redis_client.aclose()
            except Exception as exc:
                logger.debug("Error closing Redis client: %s", exc)


# Legacy alias for backward compatibility with existing tests
TTLCache = TwoTierFigmaCache
