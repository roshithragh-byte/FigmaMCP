"""Async HTTP client wrapping the Figma REST API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from figma_mcp.config import Settings

logger = logging.getLogger(__name__)


class FigmaAPIError(Exception):
    """Structured error raised when the Figma API returns an error or is unreachable."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: int | None = None,
        action: str = "Verify your request parameters and try again.",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after
        self.action = action

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": self.message,
            "action": self.action,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        if self.retry_after is not None:
            payload["retry_after"] = self.retry_after
        return payload


def _parse_retry_after(headers: httpx.Headers) -> int | None:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        seconds = int(raw.strip())
        return max(seconds, 0)
    except ValueError:
        return None


class FigmaClient:
    """Async Figma REST API client backed by a pooled httpx.AsyncClient."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = http_client is None
        if http_client is not None:
            self._client = http_client
        else:
            timeout = httpx.Timeout(settings.timeout_seconds)
            limits = httpx.Limits(
                max_connections=settings.max_connections,
                max_keepalive_connections=settings.max_keepalive_connections,
            )
            headers: dict[str, str] = {"Accept": "application/json"}
            if settings.figma_access_token:
                headers["X-Figma-Token"] = settings.figma_access_token
            self._client = httpx.AsyncClient(
                base_url=settings.figma_api_base_url,
                headers=headers,
                timeout=timeout,
                limits=limits,
            )

    async def __aenter__(self) -> FigmaClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if owned by this instance."""
        if self._owns_client:
            await self._client.aclose()

    def _sanitize_text(self, text: str) -> str:
        token = self._settings.figma_access_token
        if token and token in text:
            return text.replace(token, "[REDACTED]")
        return text

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._settings.figma_access_token:
            raise FigmaAPIError(
                "FIGMA_ACCESS_TOKEN is not configured.",
                status_code=401,
                action="Set the FIGMA_ACCESS_TOKEN environment variable and restart the server.",
            )

        try:
            response = await self._client.request(
                method,
                path,
                params=params,
                json=json_body,
            )
        except httpx.TimeoutException as exc:
            logger.warning("Figma API request timed out: %s %s", method, path)
            raise FigmaAPIError(
                "Request to Figma API timed out.",
                status_code=504,
                action="Retry the request or narrow the query using depth or node_ids.",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("Figma API network error on %s %s: %s", method, path, type(exc).__name__)
            raise FigmaAPIError(
                "Unable to reach the Figma API due to a network error.",
                status_code=502,
                action="Check network connectivity and retry.",
            ) from exc

        if response.status_code == 200 or response.status_code == 201:
            try:
                data: dict[str, Any] = response.json()
                return data
            except ValueError as exc:
                raise FigmaAPIError(
                    "Figma API returned an invalid JSON response.",
                    status_code=502,
                    action="Retry the request; if the issue persists, check Figma API status.",
                ) from exc

        self._raise_for_status(response)
        raise AssertionError("Unreachable")  # pragma: no cover

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        retry_after = _parse_retry_after(response.headers) if status == 429 else None

        api_detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                raw_msg = body.get("err") or body.get("message") or ""
                if isinstance(raw_msg, str):
                    api_detail = self._sanitize_text(raw_msg.strip())
        except ValueError:
            api_detail = ""

        if status == 401:
            raise FigmaAPIError(
                "Figma authentication failed: invalid or expired access token.",
                status_code=401,
                action="Verify FIGMA_ACCESS_TOKEN is valid and not expired.",
            )
        if status == 403:
            raise FigmaAPIError(
                "Access forbidden: token lacks permission for this Figma resource.",
                status_code=403,
                action="Ensure the token owner has access and required scopes for the file.",
            )
        if status == 404:
            raise FigmaAPIError(
                "Figma resource not found.",
                status_code=404,
                action="Check that the file_key (and any node_ids) exist and are spelled correctly.",
            )
        if status == 429:
            wait_hint = (
                f" Wait {retry_after} seconds before retrying."
                if retry_after is not None
                else " Back off and retry shortly."
            )
            raise FigmaAPIError(
                f"Figma API rate limit exceeded.{wait_hint}",
                status_code=429,
                retry_after=retry_after,
                action=(
                    f"Retry after {retry_after} seconds."
                    if retry_after is not None
                    else "Reduce request frequency and retry."
                ),
            )
        if status >= 500:
            raise FigmaAPIError(
                f"Figma API upstream error (HTTP {status}).",
                status_code=status,
                action="Retry the request after a short delay.",
            )

        suffix = f" ({api_detail})" if api_detail else ""
        raise FigmaAPIError(
            f"Figma API request failed with HTTP {status}{suffix}.",
            status_code=status,
            action="Review the request parameters and try again.",
        )

    async def get_file(
        self,
        file_key: str,
        *,
        depth: int | None = 2,
        node_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if depth is not None:
            params["depth"] = depth
        if node_ids:
            params["ids"] = ",".join(node_ids)
        return await self._request("GET", f"/files/{file_key}", params=params)

    async def get_nodes(
        self,
        file_key: str,
        node_ids: list[str],
        *,
        depth: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"ids": ",".join(node_ids)}
        if depth is not None:
            params["depth"] = depth
        return await self._request("GET", f"/files/{file_key}/nodes", params=params)

    async def export_images(
        self,
        file_key: str,
        node_ids: list[str],
        *,
        image_format: str = "png",
        scale: float = 1.0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "ids": ",".join(node_ids),
            "format": image_format,
            "scale": scale,
        }
        return await self._request("GET", f"/images/{file_key}", params=params)

    async def get_file_components(self, file_key: str) -> dict[str, Any]:
        return await self._request("GET", f"/files/{file_key}/components")

    async def get_file_styles(self, file_key: str) -> dict[str, Any]:
        return await self._request("GET", f"/files/{file_key}/styles")

    async def get_file_comments(
        self,
        file_key: str,
        *,
        as_md: bool = True,
    ) -> dict[str, Any]:
        params = {"as_md": "true" if as_md else "false"}
        return await self._request("GET", f"/files/{file_key}/comments", params=params)

    async def post_file_comment(
        self,
        file_key: str,
        message: str,
        *,
        node_id: str | None = None,
        comment_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"message": message}
        if comment_id is not None:
            body["comment_id"] = comment_id
        if node_id is not None:
            body["client_meta"] = {
                "node_id": node_id,
                "node_offset": {"x": 0, "y": 0},
            }
        return await self._request("POST", f"/files/{file_key}/comments", json_body=body)
