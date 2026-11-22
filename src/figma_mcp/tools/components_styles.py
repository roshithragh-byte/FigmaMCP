"""Figma MCP tools for published components, component sets, and styles."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import FileKeyInput, TeamIdInput
from figma_mcp.tools.common import (
    check_file_authorization,
    get_client,
    validation_error_dict,
)


def register_components_styles_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register component and style inspection tools for files and teams."""

    @mcp.tool()
    async def get_file_components(
        file_key: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List published components defined in a Figma file."""
        try:
            validated = FileKeyInput(file_key=file_key)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).get_file_components(validated.file_key)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_file_component_sets(
        file_key: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List published component sets (variants) defined in a Figma file."""
        try:
            validated = FileKeyInput(file_key=file_key)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).get_file_component_sets(validated.file_key)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_file_styles(
        file_key: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List published styles (color, text, effect, grid) in a Figma file."""
        try:
            validated = FileKeyInput(file_key=file_key)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).get_file_styles(validated.file_key)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_team_components(
        team_id: str,
        page_size: int = 30,
        cursor: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List all published components in a team library."""
        try:
            validated = TeamIdInput(team_id=team_id)
            assert ctx is not None
            return await get_client(ctx, client).get_team_components(
                validated.team_id,
                page_size=page_size,
                cursor=cursor,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_team_styles(
        team_id: str,
        page_size: int = 30,
        cursor: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List all published styles in a team library."""
        try:
            validated = TeamIdInput(team_id=team_id)
            assert ctx is not None
            return await get_client(ctx, client).get_team_styles(
                validated.team_id,
                page_size=page_size,
                cursor=cursor,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()
