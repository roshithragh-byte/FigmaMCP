"""Figma MCP tools for creating, configuring, and inspecting Webhooks (v2)."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import (
    CreateWebhookInput,
    UpdateWebhookInput,
    WebhookIdInput,
    WebhooksListInput,
)
from figma_mcp.tools.common import (
    check_read_only,
    get_client,
    validation_error_dict,
)


def register_webhooks_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register Figma v2 webhook management tools."""

    @mcp.tool()
    async def list_webhooks(
        context: Literal["team", "project", "folder"] | None = None,
        context_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List active webhooks filtered optionally by context (team, project, folder)."""
        try:
            validated = WebhooksListInput(context=context, context_id=context_id)
            assert ctx is not None
            return await get_client(ctx, client).list_webhooks(
                context=validated.context,
                context_id=validated.context_id,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_webhook(
        webhook_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Get details and configuration of a specific webhook."""
        try:
            validated = WebhookIdInput(webhook_id=webhook_id)
            assert ctx is not None
            return await get_client(ctx, client).get_webhook(validated.webhook_id)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def create_webhook(
        event_type: str,
        team_id: str,
        endpoint: str,
        passcode: str,
        description: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a new webhook subscription for team events.

        event_type can be 'FILE_UPDATE', 'FILE_VERSION_UPDATE', 'FILE_COMMENT', etc.
        """
        try:
            ro_err = check_read_only(settings, "creating webhooks")
            if ro_err is not None:
                return ro_err

            validated = CreateWebhookInput(
                event_type=event_type,
                team_id=team_id,
                endpoint=endpoint,
                passcode=passcode,
                description=description,
            )
            body: dict[str, Any] = {
                "event_type": validated.event_type,
                "team_id": validated.team_id,
                "endpoint": validated.endpoint,
                "passcode": validated.passcode,
            }
            if validated.description:
                body["description"] = validated.description
            assert ctx is not None
            return await get_client(ctx, client).create_webhook(body)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def update_webhook(
        webhook_id: str,
        endpoint: str | None = None,
        passcode: str | None = None,
        description: str | None = None,
        status: Literal["ACTIVE", "PAUSED"] | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing webhook configuration (endpoint, passcode, status)."""
        try:
            ro_err = check_read_only(settings, "updating webhooks")
            if ro_err is not None:
                return ro_err

            validated = UpdateWebhookInput(
                webhook_id=webhook_id,
                endpoint=endpoint,
                passcode=passcode,
                description=description,
                status=status,
            )
            body: dict[str, Any] = {}
            if validated.endpoint is not None:
                body["endpoint"] = validated.endpoint
            if validated.passcode is not None:
                body["passcode"] = validated.passcode
            if validated.description is not None:
                body["description"] = validated.description
            if validated.status is not None:
                body["status"] = validated.status
            assert ctx is not None
            return await get_client(ctx, client).update_webhook(validated.webhook_id, body)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def delete_webhook(
        webhook_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Delete an existing webhook."""
        try:
            ro_err = check_read_only(settings, "deleting webhooks")
            if ro_err is not None:
                return ro_err

            validated = WebhookIdInput(webhook_id=webhook_id)
            assert ctx is not None
            return await get_client(ctx, client).delete_webhook(validated.webhook_id)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_webhook_requests(
        webhook_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve recent delivery attempts and response statuses for a webhook."""
        try:
            validated = WebhookIdInput(webhook_id=webhook_id)
            assert ctx is not None
            return await get_client(ctx, client).get_webhook_requests(validated.webhook_id)
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()
