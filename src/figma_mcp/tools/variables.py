"""Figma MCP tools for reading and mutating Figma variables and collections."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import FileKeyInput, VariablesBulkUpdateInput
from figma_mcp.tools.common import (
    check_file_authorization,
    check_read_only,
    get_client,
    validation_error_dict,
)


def register_variables_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register variable inspection and atomic bulk update tools."""

    @mcp.tool()
    async def get_local_variables(
        file_key: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve local variable collections, modes, and variable values from a Figma file."""
        try:
            validated = FileKeyInput(file_key=file_key)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).get_local_variables(validated.file_key)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_published_variables(
        file_key: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve published variable collections and variables from a Figma file."""
        try:
            validated = FileKeyInput(file_key=file_key)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).get_published_variables(validated.file_key)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def post_variables_bulk_update(
        file_key: str,
        variable_collections: list[dict[str, Any]] | None = None,
        variable_modes: list[dict[str, Any]] | None = None,
        variables: list[dict[str, Any]] | None = None,
        variable_mode_values: list[dict[str, Any]] | None = None,
        dry_run: bool = False,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Atomically create, update, or delete variable collections, modes, and variables.

        Supports dry_run=True to preview the mutations and validate without committing changes.
        """
        try:
            ro_err = check_read_only(settings, "updating variables")
            if ro_err is not None and not dry_run:
                return ro_err

            validated = VariablesBulkUpdateInput(
                file_key=file_key,
                variable_collections=variable_collections,
                variable_modes=variable_modes,
                variables=variables,
                variable_mode_values=variable_mode_values,
                dry_run=dry_run,
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err

            body: dict[str, Any] = {}
            if validated.variable_collections:
                body["variableCollections"] = validated.variable_collections
            if validated.variable_modes:
                body["variableModes"] = validated.variable_modes
            if validated.variables:
                body["variables"] = validated.variables
            if validated.variable_mode_values:
                body["variableModeValues"] = validated.variable_mode_values

            if validated.dry_run:
                return {
                    "dry_run": True,
                    "status": "validated",
                    "action_count": {
                        "collections": len(validated.variable_collections or []),
                        "modes": len(validated.variable_modes or []),
                        "variables": len(validated.variables or []),
                        "mode_values": len(validated.variable_mode_values or []),
                    },
                    "preview_payload": body,
                }

            assert ctx is not None
            return await get_client(ctx, client).post_variables_bulk_update(
                validated.file_key,
                body,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()
