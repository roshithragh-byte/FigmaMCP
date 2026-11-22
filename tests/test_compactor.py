"""Tests for AST compactor engine and node pruning."""

from __future__ import annotations

from typing import Any

from figma_mcp.compactor import compact_figma_node


def test_compact_figma_node_prunes_vector_and_transforms() -> None:
    raw_node: dict[str, Any] = {
        "id": "1:2",
        "name": "Primary Button",
        "type": "FRAME",
        "visible": True,
        "vectorData": "M 0 0 L 100 0 ...",
        "vectorNetwork": {"vertices": [1, 2, 3]},
        "strokeGeometry": [{"path": "..."}],
        "fillGeometry": [{"path": "..."}],
        "relativeTransform": [[1, 0, 0], [0, 1, 0]],
        "absoluteTransform": [[1, 0, 50], [0, 1, 100]],
        "absoluteBoundingBox": {"x": 50, "y": 100, "width": 120, "height": 40},
        "exportSettings": [{"format": "PNG", "suffix": "@2x"}],
        "layoutMode": "HORIZONTAL",
        "primaryAxisAlignItems": "CENTER",
        "paddingLeft": 16,
        "paddingRight": 16,
        "children": [
            {
                "id": "1:3",
                "name": "Button Label",
                "type": "TEXT",
                "characters": "Submit Order",
                "vectorData": "M 5 5 ...",
                "relativeTransform": [[1, 0, 10], [0, 1, 10]],
            }
        ],
    }

    compacted = compact_figma_node(raw_node)

    assert compacted["id"] == "1:2"
    assert compacted["name"] == "Primary Button"
    assert compacted["type"] == "FRAME"
    assert compacted["width"] == 120.0
    assert compacted["height"] == 40.0
    assert compacted["layoutMode"] == "HORIZONTAL"
    assert compacted["paddingLeft"] == 16

    # Verify stripped heavy attributes
    assert "vectorData" not in compacted
    assert "vectorNetwork" not in compacted
    assert "strokeGeometry" not in compacted
    assert "fillGeometry" not in compacted
    assert "relativeTransform" not in compacted
    assert "absoluteTransform" not in compacted
    assert "exportSettings" not in compacted

    # Verify children pruning
    assert len(compacted["children"]) == 1
    child = compacted["children"][0]
    assert child["id"] == "1:3"
    assert child["name"] == "Button Label"
    assert child["type"] == "TEXT"
    assert child["characters"] == "Submit Order"
    assert "vectorData" not in child
    assert "relativeTransform" not in child


def test_compact_figma_node_deep_recursion_safety() -> None:
    # Build a 25-level deep nested tree
    deep_tree: dict[str, Any] = {"id": "root", "name": "Root", "type": "FRAME", "children": []}
    current = deep_tree
    for i in range(25):
        child = {"id": f"node_{i}", "name": f"Child {i}", "type": "FRAME", "children": []}
        current["children"] = [child]
        current = child

    compacted = compact_figma_node(deep_tree, max_depth=20)
    # Recursion must not crash and deepest node must be truncated gracefully
    assert compacted["id"] == "root"


def test_compact_figma_node_schema_resilience() -> None:
    # Malformed dictionary or unusual types
    assert compact_figma_node("not-a-dict") == "not-a-dict"
    assert compact_figma_node(None) is None
    assert compact_figma_node({}) == {}
