"""Tests for TTLCache, SingleFlight request coalescing, and cache policies."""

from __future__ import annotations

import asyncio

import pytest

from figma_mcp.cache import SingleFlight, TTLCache


@pytest.mark.asyncio
async def test_ttl_cache_basic_get_set() -> None:
    cache = TTLCache(default_ttl=10.0, maxsize=5)
    await cache.set("k1", {"data": 123})
    res = await cache.get("k1")
    assert res == {"data": 123}

    assert await cache.get("nonexistent") is None


@pytest.mark.asyncio
async def test_ttl_cache_expiration() -> None:
    cache = TTLCache(default_ttl=0.05, maxsize=5)
    await cache.set("short_key", "hello")
    assert await cache.get("short_key") == "hello"

    await asyncio.sleep(0.08)
    assert await cache.get("short_key") is None


@pytest.mark.asyncio
async def test_ttl_cache_lru_eviction() -> None:
    cache = TTLCache(default_ttl=60.0, maxsize=2)
    await cache.set("k1", 1)
    await cache.set("k2", 2)
    # Access k1 to make k2 the oldest
    assert await cache.get("k1") == 1
    # Adding k3 must evict k2
    await cache.set("k3", 3)
    assert await cache.get("k1") == 1
    assert await cache.get("k3") == 3
    assert await cache.get("k2") is None


@pytest.mark.asyncio
async def test_single_flight_coalescing() -> None:
    sf = SingleFlight()
    call_count = 0

    async def fetch_data() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return "result_value"

    tasks = [sf.execute("identical_key", fetch_data) for _ in range(5)]
    results = await asyncio.gather(*tasks)

    # All 5 calls must receive identical result but fetch_data ran exactly once
    assert results == ["result_value"] * 5
    assert call_count == 1


@pytest.mark.asyncio
async def test_ttl_cache_force_refresh() -> None:
    cache = TTLCache(default_ttl=60.0, maxsize=5)
    counter = 0

    async def fetch() -> int:
        nonlocal counter
        counter += 1
        return counter

    v1 = await cache.get_or_set("key", fetch, force_refresh=False)
    assert v1 == 1

    # Second call hits cache
    v2 = await cache.get_or_set("key", fetch, force_refresh=False)
    assert v2 == 1
    assert counter == 1

    # Call with force_refresh=True updates cache
    v3 = await cache.get_or_set("key", fetch, force_refresh=True)
    assert v3 == 2
    assert counter == 2
