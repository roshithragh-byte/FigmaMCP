"""Remote Streamable HTTP MCP server wrapping the Figma REST API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import (
    ErrorResponse,
    ExportFigmaImagesInput,
    FileKeyInput,
    GetFigmaFileInput,
    GetFigmaNodesInput,
    GetFileCommentsInput,
    PostFileCommentInput,
)

logger = logging.getLogger(__name__)


def _validation_error_dict(exc: ValidationError) -> dict[str, Any]:
    messages = "; ".join(
        f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    )
    return ErrorResponse(
        error=f"Invalid tool input: {messages}",
        status_code=400,
        action="Fix the input parameters and retry.",
    ).model_dump(exclude_none=True)


def create_server(
    settings: Settings | None = None,
    *,
    client: FigmaClient | None = None,
) -> FastMCP:
    """Create and configure the FastMCP server instance."""
    resolved_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(_: FastMCP) -> AsyncIterator[dict[str, Any]]:
        if client is not None:
            yield {"figma_client": client}
            return

        async with FigmaClient(resolved_settings) as managed_client:
            yield {"figma_client": managed_client}

    mcp = FastMCP(
        name="figma-mcp-server",
        instructions=(
            "Remote MCP server for inspecting Figma files, nodes, components, styles, "
            "comments, and exporting rendered node images."
        ),
        host=resolved_settings.host,
        port=resolved_settings.port,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
        lifespan=lifespan,
    )

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(_: Request) -> JSONResponse:
        """Cloud Run liveness and readiness probe endpoint."""
        return JSONResponse({"status": "ok"}, status_code=200)

    def _get_client(ctx: Context[Any, Any, Any]) -> FigmaClient:
        if client is not None:
            return client
        lifespan_ctx = ctx.request_context.lifespan_context
        return lifespan_ctx["figma_client"]  # type: ignore[no-any-return]

    @mcp.tool()
    async def get_figma_file(
        file_key: str,
        depth: int | None = 2,
        node_ids: list[str] | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve a Figma file's document tree and metadata.

        Defaults to depth=2 to prevent oversized payloads on large design files.
        Optionally filter to specific node_ids.
        """
        try:
            validated = GetFigmaFileInput(
                file_key=file_key,
                depth=depth,
                node_ids=node_ids,
            )
            assert ctx is not None
            return await _get_client(ctx).get_file(
                validated.file_key,
                depth=validated.depth,
                node_ids=validated.node_ids,
            )
        except ValidationError as exc:
            return _validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_figma_nodes(
        file_key: str,
        node_ids: list[str],
        depth: int | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve specific nodes and their subtrees from a Figma file."""
        try:
            validated = GetFigmaNodesInput(
                file_key=file_key,
                node_ids=node_ids,
                depth=depth,
            )
            assert ctx is not None
            return await _get_client(ctx).get_nodes(
                validated.file_key,
                validated.node_ids,
                depth=validated.depth,
            )
        except ValidationError as exc:
            return _validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def export_figma_images(
        file_key: str,
        node_ids: list[str],
        format: Literal["png", "svg", "jpg", "pdf"] = "png",
        scale: float = 1.0,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Render and return download URLs for specific Figma nodes in png, svg, jpg, or pdf."""
        try:
            validated = ExportFigmaImagesInput(
                file_key=file_key,
                node_ids=node_ids,
                format=format,
                scale=scale,
            )
            assert ctx is not None
            return await _get_client(ctx).export_images(
                validated.file_key,
                validated.node_ids,
                image_format=validated.format,
                scale=validated.scale,
            )
        except ValidationError as exc:
            return _validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_file_components(
        file_key: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """List published components defined in a Figma file."""
        try:
            validated = FileKeyInput(file_key=file_key)
            assert ctx is not None
            return await _get_client(ctx).get_file_components(validated.file_key)
        except ValidationError as exc:
            return _validation_error_dict(exc)
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
            assert ctx is not None
            return await _get_client(ctx).get_file_styles(validated.file_key)
        except ValidationError as exc:
            return _validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_file_comments(
        file_key: str,
        as_md: bool = True,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve comments on a Figma file, optionally formatted as Markdown."""
        try:
            validated = GetFileCommentsInput(file_key=file_key, as_md=as_md)
            assert ctx is not None
            return await _get_client(ctx).get_file_comments(
                validated.file_key,
                as_md=validated.as_md,
            )
        except ValidationError as exc:
            return _validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def post_file_comment(
        file_key: str,
        message: str,
        node_id: str | None = None,
        comment_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Post a new comment on a Figma file or reply to an existing comment."""
        try:
            validated = PostFileCommentInput(
                file_key=file_key,
                message=message,
                node_id=node_id,
                comment_id=comment_id,
            )
            assert ctx is not None
            return await _get_client(ctx).post_file_comment(
                validated.file_key,
                validated.message,
                node_id=validated.node_id,
                comment_id=validated.comment_id,
            )
        except ValidationError as exc:
            return _validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    return mcp


def create_app(
    settings: Settings | None = None,
    *,
    client: FigmaClient | None = None,
) -> Starlette:
    """Build the Starlette ASGI app for Streamable HTTP transport."""
    server = create_server(settings, client=client)
    return server.streamable_http_app()


def main() -> None:
    """Entrypoint for running the Streamable HTTP MCP server."""
    settings = Settings.from_env(require_token=True)
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Never log httpx/httpcore request details that could include auth headers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logger.info(
        "Starting figma-mcp-server on %s:%s (Streamable HTTP)",
        settings.host,
        settings.port,
    )
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
