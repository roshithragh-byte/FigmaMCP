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
async def test_mcp_lists_all_tools() -> None:
    settings = Settings(figma_access_token="figd_test")
    mcp = create_server(settings)
    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert EXPECTED_TOOLS.issubset(tool_names)
    assert len(tool_names) >= 40


@pytest.mark.asyncio
async def test_mcp_tool_execution_and_error_handling() -> None:
    settings = Settings(figma_access_token="figd_test")
    with respx.mock(base_url="https://api.figma.com/v1") as mock:
        mock.get("/files/file123").mock(
            return_value=httpx.Response(200, json={"name": "App UI", "document": {}})
        )
        mock.get("/files/missing").mock(return_value=httpx.Response(404, json={"err": "Not found"}))

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
            # FastMCP call_tool returns (content_list, structured_dict) in modern SDK
            if isinstance(err_result, tuple):
                if len(err_result) > 1 and isinstance(err_result[1], dict):
                    parsed = err_result[1]
                else:
                    parsed = json.loads(err_result[0][0].text)
            elif isinstance(err_result, list):
                parsed = json.loads(err_result[0].text)
            else:
                parsed = json.loads(str(err_result))
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


@pytest.mark.asyncio
async def test_read_only_mode_blocks_post_comment() -> None:
    settings = Settings(figma_access_token="figd_test", read_only=True)
    async with FigmaClient(settings) as client:
        mcp = create_server(settings, client=client)
        res: Any = await mcp.call_tool(
            "post_file_comment",
            {"file_key": "abc123", "message": "Automated review comment"},
        )
        payload = res[1] if isinstance(res, tuple) else json.loads(res[0].text)
        assert payload["status_code"] == 403
        assert "read-only" in payload["error"].lower()


@pytest.mark.asyncio
async def test_allowed_file_keys_rejection() -> None:
    settings = Settings(
        figma_access_token="figd_test",
        allowed_file_keys=("allowed_file_1", "allowed_file_2"),
    )
    async with FigmaClient(settings) as client:
        mcp = create_server(settings, client=client)
        res: Any = await mcp.call_tool(
            "get_figma_file",
            {"file_key": "unauthorized_file"},
        )
        payload = res[1] if isinstance(res, tuple) else json.loads(res[0].text)
        assert payload["status_code"] == 403
        assert "not allowed" in payload["error"].lower()


@pytest.mark.asyncio
async def test_get_figma_nodes_compact_mode() -> None:
    settings = Settings(figma_access_token="figd_test")
    raw_node = {
        "nodes": {
            "1:2": {
                "document": {
                    "id": "1:2",
                    "name": "Frame",
                    "type": "FRAME",
                    "vectorData": "M 0 0 ...",
                    "absoluteBoundingBox": {"width": 100, "height": 50},
                }
            }
        }
    }
    with respx.mock(base_url="https://api.figma.com/v1") as mock:
        mock.get("/files/file123/nodes").mock(return_value=httpx.Response(200, json=raw_node))
        async with FigmaClient(settings) as client:
            mcp = create_server(settings, client=client)
            # 1. Without compact (compact=False by default)
            res_raw: Any = await mcp.call_tool(
                "get_figma_nodes",
                {"file_key": "file123", "node_ids": ["1:2"], "compact": False},
            )
            data_raw = res_raw[1] if isinstance(res_raw, tuple) else json.loads(res_raw[0].text)
            doc_raw = data_raw["nodes"]["1:2"]["document"]
            assert "vectorData" in doc_raw

            # 2. With compact=True
            res_compact: Any = await mcp.call_tool(
                "get_figma_nodes",
                {"file_key": "file123", "node_ids": ["1:2"], "compact": True},
            )
            data_compact = (
                res_compact[1]
                if isinstance(res_compact, tuple)
                else json.loads(res_compact[0].text)
            )
            doc_compact = data_compact["nodes"]["1:2"]["document"]
            assert "vectorData" not in doc_compact
            # Pruner outputs compact box dictionary {x, y, width, height}
            if "box" in doc_compact:
                assert doc_compact["box"]["width"] == 100.0
                assert doc_compact["box"]["height"] == 50.0
            else:
                assert doc_compact["width"] == 100.0
                assert doc_compact["height"] == 50.0

            # 3. Cache isolation: Request with compact=False immediately after compact=True
            # must still return full uncompacted vector data from cache!
            res_after: Any = await mcp.call_tool(
                "get_figma_nodes",
                {"file_key": "file123", "node_ids": ["1:2"], "compact": False},
            )
            data_after = (
                res_after[1] if isinstance(res_after, tuple) else json.loads(res_after[0].text)
            )
            doc_after = data_after["nodes"]["1:2"]["document"]
            assert "vectorData" in doc_after, "Cache was poisoned by previous compact=True call!"


@pytest.mark.asyncio
async def test_allowed_file_keys_success_and_read_only_false() -> None:
    settings = Settings(
        figma_access_token="figd_test",
        allowed_file_keys=("allowed_file_1",),
        read_only=False,
    )
    with respx.mock(base_url="https://api.figma.com/v1") as mock:
        mock.get("/files/allowed_file_1").mock(
            return_value=httpx.Response(200, json={"name": "Allowed Doc", "document": {}})
        )
        mock.post("/files/allowed_file_1/comments").mock(
            return_value=httpx.Response(200, json={"id": "comment_1", "message": "LGTM"})
        )
        async with FigmaClient(settings) as client:
            mcp = create_server(settings, client=client)

            # 1. Allowed file key succeeds
            res_file: Any = await mcp.call_tool(
                "get_figma_file",
                {"file_key": "allowed_file_1"},
            )
            data_file = res_file[1] if isinstance(res_file, tuple) else json.loads(res_file[0].text)
            assert data_file["name"] == "Allowed Doc"

            # 2. post_file_comment succeeds when read_only=False
            res_comment: Any = await mcp.call_tool(
                "post_file_comment",
                {"file_key": "allowed_file_1", "message": "LGTM"},
            )
            data_comment = (
                res_comment[1]
                if isinstance(res_comment, tuple)
                else json.loads(res_comment[0].text)
            )
            assert data_comment["id"] == "comment_1"
