"""Tests for Variables, Dev Resources, Webhooks, Folders, Enterprise, and Compound tools."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from figma_mcp.client import FigmaClient
from figma_mcp.config import Settings
from figma_mcp.server import create_server


def _extract_payload(res: Any) -> dict[str, Any]:
    if isinstance(res, tuple):
        if len(res) > 1 and isinstance(res[1], dict):
            return res[1]
        return json.loads(res[0][0].text)  # type: ignore[no-any-return]
    if isinstance(res, list):
        return json.loads(res[0].text)  # type: ignore[no-any-return]
    return json.loads(str(res))  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_variables_tools() -> None:
    settings = Settings(figma_access_token="figd_test", read_only=False)
    with respx.mock(base_url="https://api.figma.com/v1", assert_all_called=False) as mock:
        mock.get("/files/file123/variables/local").mock(
            return_value=httpx.Response(
                200, json={"meta": {"variables": {"v1": {"name": "color/primary"}}}}
            )
        )
        mock.get("/files/file123/variables/published").mock(
            return_value=httpx.Response(
                200, json={"meta": {"variables": {"v1": {"name": "color/primary"}}}}
            )
        )
        mock.post("/files/file123/variables").mock(
            return_value=httpx.Response(200, json={"status": 200, "error": False})
        )

        async with FigmaClient(settings) as client:
            mcp = create_server(settings, client=client)

            # Local variables
            res_local = await mcp.call_tool("get_local_variables", {"file_key": "file123"})
            payload_local = _extract_payload(res_local)
            assert "variables" in payload_local["meta"]

            # Published variables
            res_pub = await mcp.call_tool("get_published_variables", {"file_key": "file123"})
            payload_pub = _extract_payload(res_pub)
            assert "variables" in payload_pub["meta"]

            # Dry-run bulk update
            res_dry = await mcp.call_tool(
                "post_variables_bulk_update",
                {"file_key": "file123", "variables": [{"name": "test"}], "dry_run": True},
            )
            payload_dry = _extract_payload(res_dry)
            assert payload_dry["dry_run"] is True
            assert payload_dry["action_count"]["variables"] == 1

            # Commit bulk update
            res_commit = await mcp.call_tool(
                "post_variables_bulk_update",
                {"file_key": "file123", "variables": [{"name": "test"}], "dry_run": False},
            )
            payload_commit = _extract_payload(res_commit)
            assert payload_commit["status"] == 200


@pytest.mark.asyncio
async def test_comments_delete_and_reactions() -> None:
    settings = Settings(figma_access_token="figd_test", read_only=False)
    with respx.mock(base_url="https://api.figma.com/v1", assert_all_called=False) as mock:
        mock.delete("/files/file123/comments/c1").mock(return_value=httpx.Response(200, json={}))
        mock.get("/files/file123/comments/c1/reactions").mock(
            return_value=httpx.Response(200, json={"reactions": [{"emoji": "👍"}]})
        )
        mock.post("/files/file123/comments/c1/reactions").mock(
            return_value=httpx.Response(200, json={})
        )
        mock.delete("/files/file123/comments/c1/reactions?emoji=%F0%9F%93%A6").mock(
            return_value=httpx.Response(200, json={})
        )
        mock.delete("/files/file123/comments/c1/reactions").mock(
            return_value=httpx.Response(200, json={})
        )

        async with FigmaClient(settings) as client:
            mcp = create_server(settings, client=client)

            del_res = await mcp.call_tool(
                "delete_file_comment", {"file_key": "file123", "comment_id": "c1"}
            )
            assert _extract_payload(del_res) == {}

            rx_get = await mcp.call_tool(
                "get_comment_reactions", {"file_key": "file123", "comment_id": "c1"}
            )
            assert len(_extract_payload(rx_get)["reactions"]) == 1

            rx_post = await mcp.call_tool(
                "post_comment_reaction", {"file_key": "file123", "comment_id": "c1", "emoji": "👍"}
            )
            assert _extract_payload(rx_post) == {}

            rx_del = await mcp.call_tool(
                "delete_comment_reaction",
                {"file_key": "file123", "comment_id": "c1", "emoji": "👍"},
            )
            assert _extract_payload(rx_del) == {}


@pytest.mark.asyncio
async def test_dev_resources_tools() -> None:
    settings = Settings(figma_access_token="figd_test", read_only=False)
    with respx.mock(base_url="https://api.figma.com/v1", assert_all_called=False) as mock:
        mock.get("/files/file123/dev_resources").mock(
            return_value=httpx.Response(
                200, json={"dev_resources": [{"id": "d1", "url": "https://github.com"}]}
            )
        )
        mock.post("/dev_resources").mock(
            return_value=httpx.Response(200, json={"links_created": [{"id": "d1"}]})
        )
        mock.delete("/files/file123/dev_resources/d1").mock(
            return_value=httpx.Response(200, json={})
        )

        async with FigmaClient(settings) as client:
            mcp = create_server(settings, client=client)

            get_res = await mcp.call_tool("get_dev_resources", {"file_key": "file123"})
            assert len(_extract_payload(get_res)["dev_resources"]) == 1

            post_res = await mcp.call_tool(
                "post_dev_resources",
                {
                    "dev_resources": [
                        {
                            "file_key": "file123",
                            "node_id": "1:2",
                            "name": "Repo",
                            "url": "https://github.com",
                        }
                    ]
                },
            )
            assert len(_extract_payload(post_res)["links_created"]) == 1

            del_res = await mcp.call_tool(
                "delete_dev_resource", {"file_key": "file123", "dev_resource_id": "d1"}
            )
            assert _extract_payload(del_res) == {}


@pytest.mark.asyncio
async def test_webhooks_and_folders() -> None:
    settings = Settings(figma_access_token="figd_test", read_only=False)
    with respx.mock(base_url="https://api.figma.com", assert_all_called=False) as mock:
        mock.get("/v2/webhooks").mock(return_value=httpx.Response(200, json={"webhooks": []}))
        mock.get("/v2/teams/team_1/folders").mock(
            return_value=httpx.Response(200, json={"folders": []})
        )
        mock.get("/v2/folders/f1/files").mock(return_value=httpx.Response(200, json={"files": []}))

        async with FigmaClient(settings) as client:
            mcp = create_server(settings, client=client)

            wh_res = await mcp.call_tool("list_webhooks", {})
            assert "webhooks" in _extract_payload(wh_res)

            folders_res = await mcp.call_tool("get_team_folders", {"team_id": "team_1"})
            assert "folders" in _extract_payload(folders_res)

            files_res = await mcp.call_tool("get_folder_files", {"folder_id": "f1"})
            assert "files" in _extract_payload(files_res)


@pytest.mark.asyncio
async def test_compound_analysis_tools() -> None:
    settings = Settings(figma_access_token="figd_test", read_only=False)
    with respx.mock(base_url="https://api.figma.com/v1", assert_all_called=False) as mock:
        mock.get("/files/file123/components").mock(
            return_value=httpx.Response(
                200, json={"meta": {"components": [{"key": "c1", "name": "Button"}]}}
            )
        )
        mock.get("/files/file123/component_sets").mock(
            return_value=httpx.Response(200, json={"meta": {"component_sets": []}})
        )
        mock.get("/files/file123/styles").mock(
            return_value=httpx.Response(
                200, json={"meta": {"styles": [{"style_type": "FILL", "key": "s1"}]}}
            )
        )
        mock.get("/files/file123/variables/local").mock(
            return_value=httpx.Response(
                200, json={"meta": {"variableCollections": {}, "variables": {}}}
            )
        )
        mock.get("/files/file123/variables/published").mock(
            return_value=httpx.Response(
                200, json={"meta": {"variableCollections": {}, "variables": {}}}
            )
        )
        mock.get("/files/file123/comments?as_md=true").mock(
            return_value=httpx.Response(
                200,
                json={
                    "comments": [
                        {"id": "c1", "message": "Need review", "user": {"handle": "alice"}}
                    ]
                },
            )
        )
        mock.get("/files/file123?depth=3").mock(
            return_value=httpx.Response(
                200,
                json={
                    "document": {
                        "type": "DOCUMENT",
                        "children": [{"type": "INSTANCE", "componentId": "c1", "id": "1:2"}],
                    }
                },
            )
        )

        async with FigmaClient(settings) as client:
            mcp = create_server(settings, client=client)

            # Design system analysis
            ds_res = await mcp.call_tool("analyze_design_system", {"file_key": "file123"})
            ds_payload = _extract_payload(ds_res)
            assert ds_payload["summary"]["total_components"] == 1
            assert ds_payload["styles_breakdown"]["FILL"] == 1

            # Token drift check
            drift_res = await mcp.call_tool("check_token_drift", {"file_key": "file123"})
            drift_payload = _extract_payload(drift_res)
            assert "drift_summary" in drift_payload

            # Comment triage
            triage_res = await mcp.call_tool("triage_comments", {"file_key": "file123"})
            triage_payload = _extract_payload(triage_res)
            assert triage_payload["total_comments"] == 1
            assert triage_payload["unresolved_count"] == 1

            # Dependency graph
            graph_res = await mcp.call_tool(
                "build_dependency_graph", {"file_key": "file123", "depth": 3}
            )
            graph_payload = _extract_payload(graph_res)
            assert graph_payload["graph_summary"]["total_instances_found"] == 1
            assert graph_payload["component_frequency"]["c1"] == 1
