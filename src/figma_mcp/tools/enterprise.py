"""Figma MCP tools for Enterprise Activity Logs, AI Usage, and Library Analytics."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import (
    ActivityLogsInput,
    AIUsageInput,
    LibraryAnalyticsInput,
)
from figma_mcp.tools.common import (
    get_client,
    validation_error_dict,
)


def register_enterprise_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register tools for Enterprise Activity Logs, AI metering, and Library Analytics."""

    @mcp.tool()
    async def get_activity_logs(
        events: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = 50,
        cursor: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve enterprise activity and security audit logs (requires org admin token)."""
        try:
            validated = ActivityLogsInput(
                events=events,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                cursor=cursor,
            )
            assert ctx is not None
            return await get_client(ctx, client).get_activity_logs(
                events=validated.events,
                start_time=validated.start_time,
                end_time=validated.end_time,
                limit=validated.limit,
                cursor=validated.cursor,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_ai_usage(
        start_date: str,
        end_date: str,
        user_email: str | None = None,
        cursor: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve organization daily AI credit usage per user (requires org admin token)."""
        try:
            validated = AIUsageInput(
                start_date=start_date,
                end_date=end_date,
                user_email=user_email,
                cursor=cursor,
            )
            assert ctx is not None
            return await get_client(ctx, client).get_ai_usage(
                validated.start_date,
                validated.end_date,
                user_email=validated.user_email,
                cursor=validated.cursor,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_library_analytics(
        library_file_key: str,
        asset_type: Literal["component", "style", "variable"] = "component",
        metric_type: Literal["usages", "actions"] = "usages",
        group_by: Literal["component", "style", "variable", "team", "file"] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve component, style, or variable adoption analytics and insert/detach actions."""
        try:
            validated = LibraryAnalyticsInput(
                library_file_key=library_file_key,
                asset_type=asset_type,
                metric_type=metric_type,
                group_by=group_by,
                start_date=start_date,
                end_date=end_date,
            )
            assert ctx is not None
            return await get_client(ctx, client).get_library_analytics(
                validated.library_file_key,
                asset_type=validated.asset_type,
                metric_type=validated.metric_type,
                group_by=validated.group_by,
                start_date=validated.start_date,
                end_date=validated.end_date,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()
