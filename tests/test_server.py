"""Integration tests for the FastMCP Streamable HTTP server and /healthz."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from figma_mcp.client import FigmaClient
from figma_mcp.config import Settings
from figma_mcp.server import create_app, create_server

EXPECTED_TOOLS = {
    "get_figma_file",
    "get_figma_nodes",
    "export_figma_images",
    "get_file_components",
    "get_file_styles",
    "get_file_comments",
    "post_file_comment",
}


def test_healthz_endpoint() -> None:
    settings = Settings(figma_access_token="figd_test")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_mcp_lists_all_seven_tools() -> None:
    settings = Settings(figma_access_token="figd_test")
    mcp = create_server(settings)
    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert tool_names == EXPECTED_TOOLS


@pytest.mark.asyncio
async def test_mcp_tool_execution_and_error_handling() -> None:
    settings = Settings(figma_access_token="figd_test")
    with respx.mock(base_url="https://api.figma.com/v1") as mock:
        mock.get("/files/file123").mock(
            return_value=httpx.Response(200, json={"name": "App UI", "document": {}})
        )
        mock.get("/files/missing").mock(
            return_value=httpx.Response(404, json={"err": "Not found"})
        )

        async with FigmaClient(settings) as figma_client:
            mcp = create_server(settings, client=figma_client)

            ok_result: Any = await mcp.call_tool(
                "get_figma_file",
                {"file_key": "file123", "depth": 2},
            )
            ok_text = ok_result[0].text if isinstance(ok_result, list) else str(ok_result)
            assert "App UI" in ok_text

            err_result: Any = await mcp.call_tool(
                "get_figma_file",
                {"file_key": "missing", "depth": 2},
            )
            err_text = err_result[0].text if isinstance(err_result, list) else str(err_result)
            parsed = json.loads(err_text)
            assert parsed["status_code"] == 404
            assert "not found" in parsed["error"].lower()


def test_streamable_http_list_tools_over_http() -> None:
    settings = Settings(figma_access_token="figd_test")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            },
        )
    assert response.status_code == 200
    body_text = response.text
    for tool_name in EXPECTED_TOOLS:
        assert tool_name in body_text
