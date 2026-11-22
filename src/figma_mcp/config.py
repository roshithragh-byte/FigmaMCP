"""Configuration management for the Figma MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigurationError(RuntimeError):
    """Raised when required server configuration is missing or invalid."""


def _is_test_environment() -> bool:
    return (
        os.environ.get("APP_ENV", "").lower() == "test"
        or "PYTEST_CURRENT_TEST" in os.environ
    )


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    figma_access_token: str = field(repr=False)
    figma_api_base_url: str = "https://api.figma.com/v1"
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    timeout_seconds: float = 30.0
    max_connections: int = 20
    max_keepalive_connections: int = 10
    read_only: bool = True
    allowed_file_keys: tuple[str, ...] | None = None
    cache_ttl_seconds: float = 300.0
    cache_max_size: int = 100

    @classmethod
    def from_env(cls, *, require_token: bool | None = None) -> Settings:
        """Load settings from environment variables.

        Args:
            require_token: Override whether a missing FIGMA_ACCESS_TOKEN raises
                ConfigurationError. Defaults to True in non-test environments.
        """
        if require_token is None:
            require_token = not _is_test_environment()

        token = os.environ.get("FIGMA_ACCESS_TOKEN", "").strip()
        if require_token and not token:
            raise ConfigurationError(
                "FIGMA_ACCESS_TOKEN environment variable is required and must not be empty."
            )

        raw_port = os.environ.get("PORT", "8080").strip()
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ConfigurationError(f"Invalid PORT value: {raw_port!r}") from exc

        if not (1 <= port <= 65535):
            raise ConfigurationError(f"PORT must be between 1 and 65535, got {port}.")

        raw_timeout = os.environ.get("FIGMA_TIMEOUT_SECONDS", "30.0").strip()
        try:
            timeout_seconds = float(raw_timeout)
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid FIGMA_TIMEOUT_SECONDS value: {raw_timeout!r}"
            ) from exc

        if timeout_seconds <= 0:
            raise ConfigurationError("FIGMA_TIMEOUT_SECONDS must be positive.")

        max_connections = int(os.environ.get("FIGMA_MAX_CONNECTIONS", "20"))
        max_keepalive = int(os.environ.get("FIGMA_MAX_KEEPALIVE_CONNECTIONS", "10"))

        raw_read_only = os.environ.get("FIGMA_READ_ONLY", "true").strip().lower()
        read_only = raw_read_only not in ("false", "0", "no", "off")

        raw_allowed_keys = os.environ.get("FIGMA_ALLOWED_FILE_KEYS", "").strip()
        allowed_file_keys: tuple[str, ...] | None = None
        if raw_allowed_keys:
            parsed_keys = tuple(k.strip() for k in raw_allowed_keys.split(",") if k.strip())
            allowed_file_keys = parsed_keys or None

        raw_cache_ttl = os.environ.get("FIGMA_CACHE_TTL_SECONDS", "300.0").strip()
        try:
            cache_ttl_seconds = float(raw_cache_ttl)
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid FIGMA_CACHE_TTL_SECONDS value: {raw_cache_ttl!r}"
            ) from exc

        if cache_ttl_seconds < 0:
            raise ConfigurationError("FIGMA_CACHE_TTL_SECONDS cannot be negative.")

        raw_cache_max_size = os.environ.get("FIGMA_CACHE_MAX_SIZE", "500").strip()
        try:
            cache_max_size = int(raw_cache_max_size)
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid FIGMA_CACHE_MAX_SIZE value: {raw_cache_max_size!r}"
            ) from exc

        if cache_max_size <= 0:
            raise ConfigurationError("FIGMA_CACHE_MAX_SIZE must be positive.")

        return cls(
            figma_access_token=token,
            figma_api_base_url=os.environ.get(
                "FIGMA_API_BASE_URL", "https://api.figma.com/v1"
            ).rstrip("/"),
            host=os.environ.get("HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=port,
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            timeout_seconds=timeout_seconds,
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
            read_only=read_only,
            allowed_file_keys=allowed_file_keys,
            cache_ttl_seconds=cache_ttl_seconds,
            cache_max_size=cache_max_size,
        )
