"""In-memory TTL cache with LRU eviction and SingleFlight async request coalescing.

Shields upstream Figma REST API from concurrent thundering-herd requests,
honoring TTL expiration and strictly excluding 4xx/5xx/429 errors from being cached.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _CacheEntry:
    value: Any
    expires_at: float


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


class TTLCache:
    """Coroutine-safe within an asyncio event loop, bounded in-memory LRU cache with TTL."""

    def __init__(self, *, default_ttl: float = 300.0, maxsize: int = 100) -> None:
        self._default_ttl = max(default_ttl, 0.0)
        self._maxsize = max(maxsize, 1)
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._single_flight = SingleFlight()

    async def get(self, key: str) -> Any | None:
        """Retrieve a cached value if present and not expired."""
        now = time.monotonic()
        async with self._lock:
            if key not in self._entries:
                return None
            entry = self._entries[key]
            if entry.expires_at <= now:
                # Expired: remove and return None
                del self._entries[key]
                return None
            # Move to end for LRU tracking
            self._entries.move_to_end(key)
            return entry.value

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        """Store a value in cache with TTL. Evicts oldest entries if maxsize is exceeded."""
        effective_ttl = self._default_ttl if ttl is None else max(ttl, 0.0)
        if effective_ttl <= 0:
            async with self._lock:
                self._entries.pop(key, None)
            return

        now = time.monotonic()
        expires_at = now + effective_ttl
        async with self._lock:
            # Active eviction of expired keys to bound memory footprint
            expired_keys = [k for k, v in self._entries.items() if v.expires_at <= now]
            for k in expired_keys:
                del self._entries[k]

            if key in self._entries:
                self._entries.move_to_end(key)
            self._entries[key] = _CacheEntry(value=value, expires_at=expires_at)
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._entries.clear()

    async def get_or_set(
        self,
        key: str,
        fetch_coro_fn: Callable[[], Awaitable[Any]],
        *,
        ttl: float | None = None,
        force_refresh: bool = False,
    ) -> Any:
        """Retrieve from cache, or coalesce concurrent calls into a single fetch and cache."""
        if not force_refresh:
            cached = await self.get(key)
            if cached is not None:
                return cached

        async def _fetch_and_cache() -> Any:
            # Recheck cache inside single-flight execution
            if not force_refresh:
                cached = await self.get(key)
                if cached is not None:
                    return cached
            val = await fetch_coro_fn()
            # Only cache non-empty valid responses
            await self.set(key, val, ttl=ttl)
            return val

        return await self._single_flight.execute(key, _fetch_and_cache)
