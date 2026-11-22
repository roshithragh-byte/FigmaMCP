"""Figma MCP tools for teams and v2 folders/projects."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import CreateFolderInput, FolderIdInput, TeamIdInput
from figma_mcp.tools.common import (
    check_read_only,
    get_client,
    validation_error_dict,
)


def register_projects_folders_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register team and folder management tools."""

    @mcp.tool()
    async def get_team(
        team_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve team information and metadata by team ID."""
        try:
            validated = TeamIdInput(team_id=team_id)
            assert ctx is not None
            return await get_client(ctx, client).get_team(validated.team_id)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_team_folders(
        team_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List all top-level folders in a Figma team."""
        try:
            validated = TeamIdInput(team_id=team_id)
            assert ctx is not None
            return await get_client(ctx, client).get_team_folders(validated.team_id)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_folder_files(
        folder_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List all Figma files inside a specific folder."""
        try:
            validated = FolderIdInput(folder_id=folder_id)
            assert ctx is not None
            return await get_client(ctx, client).get_folder_files(validated.folder_id)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_folder_subfolders(
        folder_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List nested subfolders inside a specific folder."""
        try:
            validated = FolderIdInput(folder_id=folder_id)
            assert ctx is not None
            return await get_client(ctx, client).get_folder_subfolders(validated.folder_id)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def create_folder(
        team_id: str,
        name: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new folder in a Figma team."""
        try:
            ro_err = check_read_only(settings, "creating folders")
            if ro_err is not None:
                return ro_err

            validated = CreateFolderInput(team_id=team_id, name=name)
            assert ctx is not None
            return await get_client(ctx, client).create_folder(validated.team_id, validated.name)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()
