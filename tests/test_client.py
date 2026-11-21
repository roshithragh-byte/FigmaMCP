"""Unit tests for FigmaClient, Settings, and Pydantic input models."""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import ConfigurationError, Settings
from figma_mcp.models import (
    ExportFigmaImagesInput,
    GetFigmaFileInput,
    GetFigmaNodesInput,
    PostFileCommentInput,
)


def _test_settings(token: str = "figd_test_secret_token") -> Settings:
    return Settings(figma_access_token=token)


def test_settings_fail_fast_when_token_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIGMA_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ConfigurationError, match="FIGMA_ACCESS_TOKEN"):
        Settings.from_env(require_token=True)


def test_settings_invalid_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIGMA_ACCESS_TOKEN", "figd_valid")
    monkeypatch.setenv("PORT", "not-a-number")
    with pytest.raises(ConfigurationError, match="Invalid PORT"):
        Settings.from_env(require_token=True)


def test_settings_repr_hides_token() -> None:
    settings = _test_settings("figd_super_secret")
    assert "figd_super_secret" not in repr(settings)


def test_input_validation_rejects_bad_inputs() -> None:
    with pytest.raises(ValidationError):
        GetFigmaFileInput(file_key="../etc/passwd")

    with pytest.raises(ValidationError):
        GetFigmaNodesInput(file_key="abc123", node_ids=[])

    with pytest.raises(ValidationError):
        ExportFigmaImagesInput(file_key="abc123", node_ids=["1:2"], scale=10.0)

    with pytest.raises(ValidationError):
        PostFileCommentInput(file_key="abc123", message="   ")


@pytest.mark.asyncio
async def test_client_sends_token_header_and_calls_all_endpoints() -> None:
    with respx.mock(base_url="https://api.figma.com/v1") as mock:
        file_route = mock.get("/files/abc123").mock(
            return_value=httpx.Response(200, json={"name": "Design System"})
        )
        nodes_route = mock.get("/files/abc123/nodes").mock(
            return_value=httpx.Response(200, json={"nodes": {"1:2": {}}})
        )
        images_route = mock.get("/images/abc123").mock(
            return_value=httpx.Response(200, json={"images": {"1:2": "https://cdn.example/1.png"}})
        )
        comp_route = mock.get("/files/abc123/components").mock(
            return_value=httpx.Response(200, json={"meta": {"components": []}})
        )
        styles_route = mock.get("/files/abc123/styles").mock(
            return_value=httpx.Response(200, json={"meta": {"styles": []}})
        )
        comments_get_route = mock.get("/files/abc123/comments").mock(
            return_value=httpx.Response(200, json={"comments": []})
        )
        comments_post_route = mock.post("/files/abc123/comments").mock(
            return_value=httpx.Response(200, json={"id": "c1", "message": "Looks good"})
        )

        async with FigmaClient(_test_settings("figd_secret_123")) as client:
            assert (await client.get_file("abc123", depth=2, node_ids=["1:2"]))["name"] == "Design System"
            assert "1:2" in (await client.get_nodes("abc123", ["1:2"], depth=1))["nodes"]
            assert "1:2" in (await client.export_images("abc123", ["1:2"], image_format="png", scale=2.0))["images"]
            assert "meta" in await client.get_file_components("abc123")
            assert "meta" in await client.get_file_styles("abc123")
            assert "comments" in await client.get_file_comments("abc123", as_md=True)
            posted = await client.post_file_comment("abc123", "Looks good", node_id="1:2")
            assert posted["id"] == "c1"

        for route in (
            file_route,
            nodes_route,
            images_route,
            comp_route,
            styles_route,
            comments_get_route,
            comments_post_route,
        ):
            assert route.called
            assert route.calls[0].request.headers["X-Figma-Token"] == "figd_secret_123"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "headers", "expected_fragment"),
    [
        (401, {}, "authentication failed"),
        (403, {}, "Access forbidden"),
        (404, {}, "not found"),
        (429, {"Retry-After": "42"}, "42 seconds"),
    ],
)
async def test_client_handles_http_errors_cleanly(
    status_code: int,
    headers: dict[str, str],
    expected_fragment: str,
) -> None:
    secret = "figd_do_not_leak_me"
    with respx.mock(base_url="https://api.figma.com/v1") as mock:
        mock.get("/files/abc123").mock(
            return_value=httpx.Response(
                status_code,
                headers=headers,
                json={"err": f"error with {secret}"},
            )
        )
        async with FigmaClient(_test_settings(secret)) as client:
            with pytest.raises(FigmaAPIError) as exc_info:
                await client.get_file("abc123")

    err = exc_info.value
    assert err.status_code == status_code
    assert expected_fragment.lower() in err.message.lower()
    assert secret not in err.message
    assert secret not in str(err.to_dict())
    if status_code == 429:
        assert err.retry_after == 42
