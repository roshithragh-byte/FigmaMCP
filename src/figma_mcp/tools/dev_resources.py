"""Figma MCP tools for attaching and managing Dev Resources (documentation, repo links) on nodes."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import (
    DeleteDevResourceInput,
    GetDevResourcesInput,
    PostDevResourcesInput,
    PutDevResourcesInput,
)
from figma_mcp.tools.common import (
    check_file_authorization,
    check_read_only,
    get_client,
    validation_error_dict,
)


def register_dev_resources_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register CRUD tools for Figma Dev Resources."""

    @mcp.tool()
    async def get_dev_resources(
        file_key: str,
        node_ids: list[str] | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List developer links (GitHub, Jira, Storybook, docs) attached to Figma nodes."""
        try:
            validated = GetDevResourcesInput(file_key=file_key, node_ids=node_ids)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).get_dev_resources(
                validated.file_key,
                node_ids=validated.node_ids,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def post_dev_resources(
        dev_resources: list[dict[str, Any]],
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Attach one or more dev links to specific Figma nodes in batch.

        Each resource object should contain {file_key, node_id, name, url}.
        """
        try:
            ro_err = check_read_only(settings, "creating dev resources")
            if ro_err is not None:
                return ro_err

            validated = PostDevResourcesInput(dev_resources=dev_resources)
            assert ctx is not None
            return await get_client(ctx, client).post_dev_resources(validated.dev_resources)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def put_dev_resources(
        dev_resources: list[dict[str, Any]],
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Update existing dev links in batch.

        Each resource object should contain {id, file_key, name, url}.
        """
        try:
            ro_err = check_read_only(settings, "updating dev resources")
            if ro_err is not None:
                return ro_err

            validated = PutDevResourcesInput(dev_resources=dev_resources)
            assert ctx is not None
            return await get_client(ctx, client).put_dev_resources(validated.dev_resources)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def delete_dev_resource(
        file_key: str,
        dev_resource_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Delete an attached dev link from a Figma node."""
        try:
            ro_err = check_read_only(settings, "deleting dev resources")
            if ro_err is not None:
                return ro_err

            validated = DeleteDevResourceInput(file_key=file_key, dev_resource_id=dev_resource_id)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).delete_dev_resource(
                validated.file_key,
                validated.dev_resource_id,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()
