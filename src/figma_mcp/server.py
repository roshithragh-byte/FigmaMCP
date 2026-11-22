"""Remote Streamable HTTP MCP server wrapping the Figma REST API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from figma_mcp.client import FigmaClient
from figma_mcp.config import Settings
from figma_mcp.tools import register_all_tools

logger = logging.getLogger(__name__)


def create_server(
    settings: Settings | None = None,
    *,
    client: FigmaClient | None = None,
) -> FastMCP:
    """Create and configure the FastMCP server instance with all tools registered."""
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
            "Complete Enterprise MCP server for reading, writing, and mutating Figma resources: "
            "file ASTs, nodes, image exports, comments, reactions, variables, dev resources, "
            "teams, folders, webhooks, activity logs, AI usage, and design system intelligence."
        ),
        host=resolved_settings.host,
        port=resolved_settings.port,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
        lifespan=lifespan,
    )

    @mcp.custom_route("/healthz", methods=["GET"])  # type: ignore[untyped-decorator]
    async def healthz(_: Request) -> JSONResponse:
        """Cloud Run liveness and readiness probe endpoint."""
        return JSONResponse({"status": "ok"}, status_code=200)

    # Register all domain tool suites
    register_all_tools(mcp, resolved_settings, client=client)

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
