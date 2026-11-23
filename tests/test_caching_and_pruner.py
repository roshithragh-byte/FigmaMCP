"""Unit tests for TwoTierFigmaCache (L1, L2, SingleFlight, degradation) and prune_figma_node."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from figma_mcp.cache import TwoTierFigmaCache
from figma_mcp.pruner import prune_figma_node

# --- Cache Tests ---


@pytest.mark.asyncio
async def test_two_tier_cache_l1_in_memory() -> None:
    cache = TwoTierFigmaCache(redis_url=None, l1_ttl_seconds=60.0)
    assert not cache.has_l2

    key = TwoTierFigmaCache.make_key("get_nodes", "file123", "v1", ids="1:2")
    assert "figma:v1:get_nodes:file123:v1:" in key

    await cache.set(key, {"cached": "data"})
    assert await cache.get(key) == {"cached": "data"}


@pytest.mark.asyncio
async def test_two_tier_cache_l2_redis_promotion() -> None:
    mock_redis = AsyncMock()
    mock_redis.get.return_value = '{"from_redis": true}'

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        cache = TwoTierFigmaCache(redis_url="redis://localhost:6379", l1_ttl_seconds=60.0)
        assert cache.has_l2

        key = "test:key"
        # First read hits Redis and populates L1
        val = await cache.get(key)
        assert val == {"from_redis": True}
        assert mock_redis.get.await_count == 1

        # Second read hits L1 without calling Redis
        val_l1 = await cache.get(key)
        assert val_l1 == {"from_redis": True}
        assert mock_redis.get.await_count == 1

        # Write sets in both
        await cache.set(key, {"new": "val"}, ttl_seconds=300)
        assert mock_redis.setex.await_count == 1

        await cache.aclose()
        assert mock_redis.aclose.await_count == 1


@pytest.mark.asyncio
async def test_two_tier_cache_redis_error_degrades_gracefully() -> None:
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = ConnectionError("Redis down")
    mock_redis.setex.side_effect = ConnectionError("Redis down")

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        cache = TwoTierFigmaCache(redis_url="redis://localhost:6379")

        # Read failure does not throw exception
        val = await cache.get("broken_key")
        assert val is None

        # Write failure falls back to L1 without throwing
        await cache.set("broken_key", {"safe": "in_l1"})
        assert await cache.get("broken_key") == {"safe": "in_l1"}


# --- Pruner Tests ---


def test_prune_figma_node_drops_invisible_subtrees() -> None:
    tree = {
        "id": "1:0",
        "name": "Root",
        "type": "FRAME",
        "visible": True,
        "children": [
            {
                "id": "1:1",
                "name": "Hidden Layer",
                "type": "RECTANGLE",
                "visible": False,
                "children": [{"id": "1:2", "name": "Deep Child", "visible": True}],
            },
            {
                "id": "1:3",
                "name": "Visible Layer",
                "type": "TEXT",
                "characters": "Hello",
                "visible": True,
            },
        ],
    }
    pruned = prune_figma_node(tree)
    assert pruned is not None
    assert len(pruned["children"]) == 1
    assert pruned["children"][0]["id"] == "1:3"
    assert pruned["children"][0]["characters"] == "Hello"


def test_prune_figma_node_compacts_geometry_and_colors() -> None:
    node = {
        "id": "2:1",
        "name": "Button",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 10.456, "y": 20.789, "width": 120.12, "height": 40.56},
        "opacity": 0.85,
        "fills": [
            {"type": "SOLID", "color": {"r": 0.0, "g": 0.5, "b": 1.0}, "opacity": 1.0},
            {"type": "SOLID", "color": {"r": 1.0, "g": 1.0, "b": 1.0}, "visible": False},
        ],
        "strokes": [{"type": "SOLID", "color": {"r": 0.0, "g": 0.0, "b": 0.0}}],
        "strokeWeight": 1.5,
        "style": {
            "fontFamily": "Inter",
            "fontSize": 14.25,
            "fontWeight": 600,
            "lineHeightPx": 20.0,
        },
        "relativeTransform": [[1, 0, 0], [0, 1, 0]],
        "transitionNodeID": "9:9",
    }
    pruned = prune_figma_node(node)
    assert pruned is not None
    assert pruned["box"] == {"x": 10.5, "y": 20.8, "width": 120.1, "height": 40.6}
    assert pruned["opacity"] == 0.85
    assert pruned["fills"] == ["#0080ff"]
    assert pruned["strokes"] == ["#000000"]
    assert pruned["strokeWeight"] == 1.5
    assert pruned["textStyle"]["fontFamily"] == "Inter"
    assert pruned["textStyle"]["fontSize"] == 14.2
    assert "relativeTransform" not in pruned
    assert "transitionNodeID" not in pruned


def test_prune_figma_node_handles_gradients_and_images() -> None:
    node = {
        "id": "3:1",
        "name": "Media Card",
        "type": "FRAME",
        "fills": [
            {
                "type": "GRADIENT_LINEAR",
                "gradientStops": [
                    {"position": 0.0, "color": {"r": 1.0, "g": 0.0, "b": 0.0}},
                    {"position": 1.0, "color": {"r": 0.0, "g": 0.0, "b": 1.0}},
                ],
            },
            {"type": "IMAGE", "imageRef": "img_hash_123", "scaleMode": "FILL"},
        ],
    }
    pruned = prune_figma_node(node)
    assert pruned is not None
    assert len(pruned["fills"]) == 2
    assert pruned["fills"][0] == {
        "type": "GRADIENT_LINEAR",
        "stops": ["#ff0000 0%", "#0000ff 100%"],
    }
    assert pruned["fills"][1] == {
        "type": "IMAGE",
        "imageRef": "img_hash_123",
        "scaleMode": "FILL",
    }


def test_prune_figma_node_max_depth_guard() -> None:
    # Construct a deeply nested structure (depth 10)
    current: dict[str, Any] = {"id": "leaf", "name": "Leaf", "type": "RECTANGLE"}
    for i in range(10):
        current = {"id": f"node_{i}", "name": f"Node {i}", "type": "FRAME", "children": [current]}

    pruned = prune_figma_node(current, max_depth=3)
    assert pruned is not None

    # Verify traversal truncated at max_depth=3
    d1 = pruned["children"][0]
    d2 = d1["children"][0]
    d3 = d2["children"][0]
    assert "children" not in d3
