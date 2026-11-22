"""Async HTTP client wrapping the Figma REST API (v1 and v2)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from figma_mcp.cache import TTLCache
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
        cache: TTLCache | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = http_client is None
        self._cache = cache or TTLCache(
            default_ttl=settings.cache_ttl_seconds,
            maxsize=settings.cache_max_size,
        )
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
                # Support both personal access token and oauth bearer format if user provided Bearer
                if settings.figma_access_token.startswith("Bearer "):
                    headers["Authorization"] = settings.figma_access_token
                else:
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

    def _normalize_path(self, path: str) -> str:
        """Ensure path begins with /v1 or /v2 or default to /v1."""
        stripped = path.strip()
        if not stripped.startswith("/"):
            stripped = f"/{stripped}"
        if not (
            stripped.startswith("/v1/")
            or stripped.startswith("/v2/")
            or stripped == "/v1"
            or stripped == "/v2"
        ):
            stripped = f"/v1{stripped}"
        return stripped

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        auth_header: str | None = None,
    ) -> dict[str, Any]:
        if not self._settings.figma_access_token and not auth_header:
            raise FigmaAPIError(
                "FIGMA_ACCESS_TOKEN is not configured.",
                status_code=401,
                action="Set the FIGMA_ACCESS_TOKEN environment variable and restart the server.",
            )

        full_path = self._normalize_path(path)
        req_headers: dict[str, str] = {}
        if auth_header:
            req_headers["Authorization"] = auth_header

        try:
            response = await self._client.request(
                method,
                full_path,
                params=params,
                json=json_body,
                headers=req_headers if req_headers else None,
            )
        except httpx.TimeoutException as exc:
            logger.warning("Figma API request timed out: %s %s", method, full_path)
            raise FigmaAPIError(
                "Request to Figma API timed out.",
                status_code=504,
                action="Retry the request or narrow the query using depth or node_ids.",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "Figma API network error on %s %s: %s", method, full_path, type(exc).__name__
            )
            raise FigmaAPIError(
                "Unable to reach the Figma API due to a network error.",
                status_code=502,
                action="Check network connectivity and retry.",
            ) from exc

        if response.status_code in (200, 201):
            try:
                data: dict[str, Any] = response.json()
                return data
            except ValueError as exc:
                raise FigmaAPIError(
                    "Figma API returned an invalid JSON response.",
                    status_code=502,
                    action="Retry the request; if the issue persists, check Figma API status.",
                ) from exc
        elif response.status_code == 204:
            return {"success": True}

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
                action=(
                    "Check that the file_key (and any node_ids) exist and are spelled correctly."
                ),
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

    # --- Core Files & Nodes ---
    async def get_file(
        self,
        file_key: str,
        *,
        depth: int | None = 2,
        node_ids: list[str] | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if depth is not None:
            params["depth"] = depth
        if node_ids:
            params["ids"] = ",".join(sorted(set(node_ids)))
        cache_key = f"file:{file_key}:depth={depth}:ids={params.get('ids', '')}"
        res = await self._cache.get_or_set(
            cache_key,
            lambda: self._request("GET", f"/files/{file_key}", params=params),
            force_refresh=force_refresh,
        )
        return res  # type: ignore[no-any-return]

    async def get_nodes(
        self,
        file_key: str,
        node_ids: list[str],
        *,
        depth: int | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"ids": ",".join(sorted(set(node_ids)))}
        if depth is not None:
            params["depth"] = depth
        cache_key = f"nodes:{file_key}:ids={params['ids']}:depth={depth}"
        res = await self._cache.get_or_set(
            cache_key,
            lambda: self._request("GET", f"/files/{file_key}/nodes", params=params),
            force_refresh=force_refresh,
        )
        return res  # type: ignore[no-any-return]

    async def export_images(
        self,
        file_key: str,
        node_ids: list[str],
        *,
        image_format: str = "png",
        scale: float = 1.0,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "ids": ",".join(sorted(set(node_ids))),
            "format": image_format,
            "scale": scale,
        }
        cache_key = f"images:{file_key}:ids={params['ids']}:fmt={image_format}:scale={scale}"
        res = await self._cache.get_or_set(
            cache_key,
            lambda: self._request("GET", f"/images/{file_key}", params=params),
            force_refresh=force_refresh,
        )
        return res  # type: ignore[no-any-return]

    async def get_file_versions(
        self,
        file_key: str,
        *,
        page_size: int | None = 30,
        before: str | None = None,
        after: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if page_size is not None:
            params["page_size"] = page_size
        if before:
            params["before"] = before
        if after:
            params["after"] = after
        return await self._request("GET", f"/files/{file_key}/versions", params=params)

    # --- Components & Styles ---
    async def get_file_components(self, file_key: str) -> dict[str, Any]:
        return await self._request("GET", f"/files/{file_key}/components")

    async def get_file_styles(self, file_key: str) -> dict[str, Any]:
        return await self._request("GET", f"/files/{file_key}/styles")

    async def get_file_component_sets(self, file_key: str) -> dict[str, Any]:
        return await self._request("GET", f"/files/{file_key}/component_sets")

    async def get_team_components(
        self, team_id: str, *, page_size: int = 30, cursor: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", f"/teams/{team_id}/components", params=params)

    async def get_team_styles(
        self, team_id: str, *, page_size: int = 30, cursor: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", f"/teams/{team_id}/styles", params=params)

    async def get_team_component_sets(
        self, team_id: str, *, page_size: int = 30, cursor: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", f"/teams/{team_id}/component_sets", params=params)

    # --- Comments & Reactions ---
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

    async def delete_file_comment(self, file_key: str, comment_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/files/{file_key}/comments/{comment_id}")

    async def get_comment_reactions(
        self, file_key: str, comment_id: str, *, cursor: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if cursor:
            params["cursor"] = cursor
        return await self._request(
            "GET", f"/files/{file_key}/comments/{comment_id}/reactions", params=params
        )

    async def post_comment_reaction(
        self, file_key: str, comment_id: str, emoji: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST", f"/files/{file_key}/comments/{comment_id}/reactions", json_body={"emoji": emoji}
        )

    async def delete_comment_reaction(
        self, file_key: str, comment_id: str, emoji: str
    ) -> dict[str, Any]:
        params = {"emoji": emoji}
        return await self._request(
            "DELETE", f"/files/{file_key}/comments/{comment_id}/reactions", params=params
        )

    # --- Variables ---
    async def get_local_variables(self, file_key: str) -> dict[str, Any]:
        return await self._request("GET", f"/files/{file_key}/variables/local")

    async def get_published_variables(self, file_key: str) -> dict[str, Any]:
        return await self._request("GET", f"/files/{file_key}/variables/published")

    async def post_variables_bulk_update(
        self,
        file_key: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request("POST", f"/files/{file_key}/variables", json_body=body)

    # --- Dev Resources ---
    async def get_dev_resources(
        self, file_key: str, *, node_ids: list[str] | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if node_ids:
            params["node_ids"] = ",".join(sorted(set(node_ids)))
        return await self._request("GET", f"/files/{file_key}/dev_resources", params=params)

    async def post_dev_resources(self, dev_resources: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._request(
            "POST", "/dev_resources", json_body={"dev_resources": dev_resources}
        )

    async def put_dev_resources(self, dev_resources: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._request(
            "PUT", "/dev_resources", json_body={"dev_resources": dev_resources}
        )

    async def delete_dev_resource(self, file_key: str, dev_resource_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/files/{file_key}/dev_resources/{dev_resource_id}")

    # --- Teams & Folders (v2 Projects) ---
    async def get_team(self, team_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/teams/{team_id}")

    async def get_team_folders(self, team_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/teams/{team_id}/folders")

    async def get_folder_files(self, folder_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/folders/{folder_id}/files")

    async def get_folder_subfolders(self, folder_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/folders/{folder_id}/folders")

    async def create_folder(self, team_id: str, name: str) -> dict[str, Any]:
        return await self._request("POST", f"/teams/{team_id}/folders", json_body={"name": name})

    # --- Webhooks (v2) ---
    async def list_webhooks(
        self, *, context: str | None = None, context_id: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if context:
            params["context"] = context
        if context_id:
            params["context_id"] = context_id
        return await self._request("GET", "/v2/webhooks", params=params)

    async def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/webhooks/{webhook_id}")

    async def create_webhook(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/v2/webhooks", json_body=body)

    async def update_webhook(self, webhook_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"/v2/webhooks/{webhook_id}", json_body=body)

    async def delete_webhook(self, webhook_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/v2/webhooks/{webhook_id}")

    async def get_webhook_requests(self, webhook_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/webhooks/{webhook_id}/requests")

    # --- Enterprise & Analytics ---
    async def get_activity_logs(
        self,
        *,
        events: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if events:
            params["events"] = events
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if limit is not None:
            params["limit"] = limit
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/activity_logs", params=params)

    async def get_ai_usage(
        self,
        start_date: str,
        end_date: str,
        *,
        user_email: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
        if user_email:
            params["user_email"] = user_email
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/ai_usage/daily", params=params)

    async def get_library_analytics(
        self,
        library_file_key: str,
        asset_type: str,
        metric_type: str,
        *,
        group_by: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if group_by:
            params["group_by"] = group_by
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        path = f"/analytics/libraries/{library_file_key}/{asset_type}/{metric_type}"
        return await self._request("GET", path, params=params)
