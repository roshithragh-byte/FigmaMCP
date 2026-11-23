"""Figma MCP tools for file, node inspection, image export, and versions."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.compactor import compact_figma_node
from figma_mcp.config import Settings
from figma_mcp.models import (
    ExportFigmaImagesInput,
    GetFigmaFileInput,
    GetFigmaNodesInput,
    GetFileVersionsInput,
)
from figma_mcp.pruner import prune_figma_node
from figma_mcp.tools.common import (
    check_file_authorization,
    get_client,
    validation_error_dict,
)


def register_files_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register file inspection, node parsing, image exports, and version history tools."""

    @mcp.tool()
    async def get_figma_file(
        file_key: str,
        depth: int | None = 2,
        node_ids: list[str] | None = None,
        compact: bool = False,
        force_refresh: bool = False,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve a Figma file's document tree and metadata.

        Defaults to depth=2 to prevent oversized payloads on large design files.
        Optionally filter to specific node_ids, set compact=True for token-saving AST pruning,
        or set force_refresh=True to bypass the cache.
        """
        try:
            validated = GetFigmaFileInput(
                file_key=file_key,
                depth=depth,
                node_ids=node_ids,
                compact=compact,
                force_refresh=force_refresh,
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            raw_file = await get_client(ctx, client).get_file(
                validated.file_key,
                depth=validated.depth,
                node_ids=validated.node_ids,
                force_refresh=validated.force_refresh,
            )
            if validated.compact and "document" in raw_file:
                # Apply deterministic pruning and vector compaction
                raw_doc = raw_file["document"]
                pruned = prune_figma_node(raw_doc)
                doc_to_return = pruned if pruned is not None else compact_figma_node(raw_doc)
                return {
                    **raw_file,
                    "document": doc_to_return,
                }
            return raw_file
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_figma_nodes(
        file_key: str,
        node_ids: list[str],
        depth: int | None = None,
        compact: bool = False,
        force_refresh: bool = False,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve specific nodes and their subtrees from a Figma file.

        Set compact=True to prune heavy vector geometry and transforms,
        or set force_refresh=True to bypass the cache.
        """
        try:
            validated = GetFigmaNodesInput(
                file_key=file_key,
                node_ids=node_ids,
                depth=depth,
                compact=compact,
                force_refresh=force_refresh,
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            raw_nodes = await get_client(ctx, client).get_nodes(
                validated.file_key,
                validated.node_ids,
                depth=validated.depth,
                force_refresh=validated.force_refresh,
            )
            if validated.compact and "nodes" in raw_nodes and isinstance(raw_nodes["nodes"], dict):
                compacted_nodes: dict[str, Any] = {}
                for nid, nentry in raw_nodes["nodes"].items():
                    if isinstance(nentry, dict) and "document" in nentry:
                        pruned_doc = prune_figma_node(nentry["document"])
                        doc_to_return = (
                            pruned_doc
                            if pruned_doc is not None
                            else compact_figma_node(nentry["document"])
                        )
                        compacted_nodes[nid] = {
                            **nentry,
                            "document": doc_to_return,
                        }
                    else:
                        compacted_nodes[nid] = nentry
                return {**raw_nodes, "nodes": compacted_nodes}
            return raw_nodes
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def export_figma_images(
        file_key: str,
        node_ids: list[str],
        format: Literal["png", "svg", "jpg", "pdf"] = "png",
        scale: float = 1.0,
        force_refresh: bool = False,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Render and return download URLs for specific Figma nodes in png, svg, jpg, or pdf.

        Set force_refresh=True to bypass cached image URLs.
        """
        try:
            validated = ExportFigmaImagesInput(
                file_key=file_key,
                node_ids=node_ids,
                format=format,
                scale=scale,
                force_refresh=force_refresh,
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).export_images(
                validated.file_key,
                validated.node_ids,
                image_format=validated.format,
                scale=validated.scale,
                force_refresh=validated.force_refresh,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_file_versions(
        file_key: str,
        page_size: int | None = 30,
        before: str | None = None,
        after: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve the version history of a Figma file."""
        try:
            validated = GetFileVersionsInput(
                file_key=file_key,
                page_size=page_size,
                before=before,
                after=after,
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).get_file_versions(
                validated.file_key,
                page_size=validated.page_size,
                before=validated.before,
                after=validated.after,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()
