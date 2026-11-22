"""Common helpers and error response formatters for MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from pydantic import ValidationError

from figma_mcp.client import FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import ErrorResponse


def validation_error_dict(exc: ValidationError) -> dict[str, Any]:
    """Format Pydantic validation errors into a structured error dict."""
    messages = "; ".join(
        f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()
    )
    return ErrorResponse(
        error=f"Invalid tool input: {messages}",
        status_code=400,
        action="Fix the input parameters and retry.",
    ).model_dump(exclude_none=True)


def check_read_only(settings: Settings, action_desc: str) -> dict[str, Any] | None:
    """Return an error dict if server is running in read-only mode."""
    if settings.read_only:
        return ErrorResponse(
            error="Figma MCP server is running in read-only mode.",
            status_code=403,
            action=f"Disable FIGMA_READ_ONLY in server configuration to allow {action_desc}.",
        ).model_dump(exclude_none=True)
    return None


def check_file_authorization(settings: Settings, file_key: str) -> dict[str, Any] | None:
    """Return an error dict if file_key is restricted by allowed_file_keys."""
    if settings.allowed_file_keys is not None and file_key not in settings.allowed_file_keys:
        return ErrorResponse(
            error=f"Access to file '{file_key}' is not allowed by this gateway.",
            status_code=403,
            action="Verify the file_key or configure FIGMA_ALLOWED_FILE_KEYS.",
        ).model_dump(exclude_none=True)
    return None


def get_client(
    ctx: Context[Any, Any, Any], fallback_client: FigmaClient | None = None
) -> FigmaClient:
    """Extract FigmaClient from MCP lifespan context or fallback."""
    if fallback_client is not None:
        return fallback_client
    lifespan_ctx = ctx.request_context.lifespan_context
    return lifespan_ctx["figma_client"]  # type: ignore[no-any-return]
