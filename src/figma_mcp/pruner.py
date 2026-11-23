"""Deterministic tree pruner for Figma nodes and document trees.

Strips invisible subtrees, heavy vector paths, redundant transform matrices,
and default styles to reduce AST token payload by 75-85% for LLM consumption.
"""

from __future__ import annotations

from typing import Any

KEEP_KEYS: frozenset[str] = frozenset({
    "id",
    "name",
    "type",
    "characters",
    "componentId",
    "componentProperties",
    "componentPropertyReferences",
    "variantProperties",
    "layoutMode",
    "primaryAxisAlignItems",
    "counterAxisAlignItems",
    "itemSpacing",
    "paddingLeft",
    "paddingRight",
    "paddingTop",
    "paddingBottom",
    "cornerRadius",
    "rectangleCornerRadii",
    "constraints",
    "layoutWrap",
    "primaryAxisSizingMode",
    "counterAxisSizingMode",
    "layoutGrow",
    "layoutAlign",
})


def _rgba_to_hex(color: dict[str, float], opacity: float = 1.0) -> str:
    """Convert normalized 0.0-1.0 RGB dict to hex or rgba CSS string."""
    r = round(color.get("r", 0.0) * 255)
    g = round(color.get("g", 0.0) * 255)
    b = round(color.get("b", 0.0) * 255)
    a = round(color.get("a", 1.0) * opacity, 2)
    return f"#{r:02x}{g:02x}{b:02x}" if a >= 0.99 else f"rgba({r},{g},{b},{a})"


def _prune_paints(paints: list[dict[str, Any]]) -> list[dict[str, Any] | str]:
    """Extract visible paint colors, gradients, and images concisely."""
    result: list[dict[str, Any] | str] = []
    for p in paints:
        if not isinstance(p, dict) or p.get("visible", True) is False:
            continue
        ptype = p.get("type")
        opacity = float(p.get("opacity", 1.0))

        if ptype == "SOLID" and "color" in p and isinstance(p["color"], dict):
            result.append(_rgba_to_hex(p["color"], opacity))
        elif ptype in ("GRADIENT_LINEAR", "GRADIENT_RADIAL", "GRADIENT_ANGULAR"):
            # Summarize gradient stops
            stops: list[str] = []
            for stop in p.get("gradientStops", []):
                if isinstance(stop, dict) and "color" in stop and isinstance(stop["color"], dict):
                    pos = round(float(stop.get("position", 0.0)) * 100)
                    stops.append(f"{_rgba_to_hex(stop['color'])} {pos}%")
            result.append({"type": ptype, "stops": stops})
        elif ptype == "IMAGE":
            img_entry: dict[str, Any] = {"type": "IMAGE"}
            if "imageRef" in p:
                img_entry["imageRef"] = p["imageRef"]
            if "scaleMode" in p:
                img_entry["scaleMode"] = p["scaleMode"]
            result.append(img_entry)
        elif ptype:
            result.append(str(ptype))
    return result


def prune_figma_node(
    node: dict[str, Any],
    *,
    max_depth: int = 8,
    _depth: int = 0,
) -> dict[str, Any] | None:
    """Recursively prune a Figma node dictionary.

    - Drops hidden nodes (`visible is False`) and their children completely.
    - Rounds bounding box coordinates to 1 decimal place.
    - Extracts typography into a clean textStyle block.
    - Normalizes fills and strokes to CSS colors or concise gradient/image summaries.
    - Retains auto-layout parameters, corner radii, and component properties.
    """
    if not isinstance(node, dict):
        return None

    # 1. Drop invisible nodes and their entire subtrees
    if node.get("visible") is False:
        return None

    out: dict[str, Any] = {k: node[k] for k in KEEP_KEYS if k in node}

    # 2. Compact bounding box
    bbox = node.get("absoluteBoundingBox")
    if isinstance(bbox, dict):
        out["box"] = {
            k: round(float(bbox[k]), 1)
            for k in ("x", "y", "width", "height")
            if k in bbox and isinstance(bbox[k], (int, float))
        }

    # 3. Only include non-default opacity
    opacity = node.get("opacity")
    if isinstance(opacity, (int, float)) and opacity < 0.99:
        out["opacity"] = round(float(opacity), 2)

    # 4. Compact fills and strokes
    raw_fills = node.get("fills")
    if isinstance(raw_fills, list):
        pruned_fills = _prune_paints(raw_fills)
        if pruned_fills:
            out["fills"] = pruned_fills

    raw_strokes = node.get("strokes")
    if isinstance(raw_strokes, list):
        pruned_strokes = _prune_paints(raw_strokes)
        if pruned_strokes:
            out["strokes"] = pruned_strokes
        if "strokeWeight" in node and isinstance(node["strokeWeight"], (int, float)):
            out["strokeWeight"] = round(float(node["strokeWeight"]), 1)

    # 5. Compact typography style
    style = node.get("style")
    if isinstance(style, dict):
        text_style: dict[str, Any] = {}
        for prop in (
            "fontFamily",
            "fontSize",
            "fontWeight",
            "lineHeightPx",
            "textAlignHorizontal",
            "textAlignVertical",
            "letterSpacing",
        ):
            if prop in style:
                val = style[prop]
                if isinstance(val, (int, float)) and prop in ("fontSize", "lineHeightPx"):
                    text_style[prop] = round(float(val), 1)
                else:
                    text_style[prop] = val
        if text_style:
            out["textStyle"] = text_style

    # 6. Recurse children up to max_depth
    children = node.get("children")
    if isinstance(children, list) and _depth < max_depth:
        pruned_children: list[dict[str, Any]] = []
        for child in children:
            if isinstance(child, dict):
                pruned_c = prune_figma_node(child, max_depth=max_depth, _depth=_depth + 1)
                if pruned_c is not None:
                    pruned_children.append(pruned_c)
        if pruned_children:
            out["children"] = pruned_children

    return out
