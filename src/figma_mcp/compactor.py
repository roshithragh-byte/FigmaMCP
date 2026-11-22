"""AST compaction engine for Figma design trees.

Strips heavy vector graphics, absolute transform matrices, and export settings
while preserving semantic layout, typography, components, and hierarchy to fit
LLM context windows efficiently.
"""

from __future__ import annotations

from typing import Any

# Whitelist of attributes to preserve on Figma nodes
_PRESERVED_ATTRIBUTES = frozenset(
    {
        "id",
        "name",
        "type",
        "visible",
        "characters",
        "componentId",
        "componentProperties",
        "styles",
        "layoutMode",
        "layoutWrap",
        "primaryAxisAlignItems",
        "counterAxisAlignItems",
        "primaryAxisSizingMode",
        "counterAxisSizingMode",
        "paddingLeft",
        "paddingRight",
        "paddingTop",
        "paddingBottom",
        "itemSpacing",
        "counterAxisSpacing",
        "layoutGrow",
        "layoutAlign",
        "width",
        "height",
        "opacity",
        "blendMode",
        "isMask",
        "fills",
        "strokes",
        "strokeWeight",
        "strokeAlign",
        "cornerRadius",
        "rectangleCornerRadii",
        "style",  # TypeStyle on text nodes
        "constraints",
    }
)

# Attributes that should be explicitly dropped or pruned
_STRIPPED_ATTRIBUTES = frozenset(
    {
        "vectorData",
        "vectorNetwork",
        "strokeGeometry",
        "fillGeometry",
        "relativeTransform",
        "absoluteTransform",
        "absoluteBoundingBox",
        "absoluteRenderBounds",
        "transitionNodeID",
        "transitionDuration",
        "transitionEasing",
        "interactions",
        "exportSettings",
    }
)


def compact_figma_node(
    node: Any,
    *,
    depth: int = 0,
    max_depth: int = 20,
) -> Any:
    """Recursively prune a Figma node dictionary to reduce JSON token consumption.

    Args:
        node: Node dictionary or child value to compact.
        depth: Current recursion depth.
        max_depth: Maximum recursion depth to prevent stack overflow on circular/deep trees.

    Returns:
        Compacted node dictionary or primitive value.
    """
    if not isinstance(node, dict):
        return node

    if depth >= max_depth:
        # Return a summarized leaf when maximum depth is reached
        return {
            "id": node.get("id", ""),
            "name": node.get("name", ""),
            "type": node.get("type", ""),
            "truncated": True,
        }

    try:
        compacted: dict[str, Any] = {}

        # Preserve bounding box dimensions if present
        if "absoluteBoundingBox" in node and isinstance(node["absoluteBoundingBox"], dict):
            bbox = node["absoluteBoundingBox"]
            if "width" in bbox and "width" not in node:
                compacted["width"] = round(float(bbox["width"]), 2)
            if "height" in bbox and "height" not in node:
                compacted["height"] = round(float(bbox["height"]), 2)

        for key, value in node.items():
            if key in _STRIPPED_ATTRIBUTES:
                continue

            if key == "children" and isinstance(value, list):
                compacted["children"] = [
                    compact_figma_node(child, depth=depth + 1, max_depth=max_depth)
                    for child in value
                    if child is not None
                ]
            elif key in _PRESERVED_ATTRIBUTES or depth == 0:
                # Retain whitelisted attributes or top-level properties
                compacted[key] = value

        return compacted
    except Exception:
        # Schema resilience: degrade gracefully to the uncompacted node
        return node
