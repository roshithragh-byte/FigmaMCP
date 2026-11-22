"""Pydantic models for Figma MCP tool inputs and structured error responses."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_FILE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_file_key(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or not _FILE_KEY_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "file_key must be a non-empty alphanumeric string (hyphens and underscores allowed)."
        )
    return cleaned


def _validate_node_id_list(values: list[str]) -> list[str]:
    cleaned = [item.strip() for item in values if item and item.strip()]
    if not cleaned:
        raise ValueError("node_ids must contain at least one non-empty node ID.")
    return cleaned


class FileKeyInput(BaseModel):
    """Input model for single-file Figma endpoints."""

    file_key: str = Field(..., description="The Figma file key from the file URL.")

    @field_validator("file_key")
    @classmethod
    def check_file_key(cls, value: str) -> str:
        return _validate_file_key(value)


class GetFigmaFileInput(FileKeyInput):
    """Input model for get_figma_file."""

    depth: int | None = Field(
        default=2,
        ge=1,
        le=20,
        description="Tree traversal depth (default 2 to avoid oversized payloads).",
    )
    node_ids: list[str] | None = Field(
        default=None,
        description="Optional list of node IDs to restrict the returned document subtree.",
    )
    compact: bool = Field(
        default=False,
        description="When True, compacts AST by pruning heavy vector curves and transforms.",
    )
    force_refresh: bool = Field(
        default=False,
        description="When True, bypasses the in-memory cache and fetches fresh data from Figma.",
    )

    @field_validator("node_ids")
    @classmethod
    def check_node_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _validate_node_id_list(value)


class GetFigmaNodesInput(FileKeyInput):
    """Input model for get_figma_nodes."""

    node_ids: list[str] = Field(
        ...,
        min_length=1,
        description="List of Figma node IDs to retrieve.",
    )
    depth: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Optional traversal depth within each requested node.",
    )
    compact: bool = Field(
        default=False,
        description="When True, compacts AST by pruning heavy vector curves and transforms.",
    )
    force_refresh: bool = Field(
        default=False,
        description="When True, bypasses the in-memory cache and fetches fresh data from Figma.",
    )

    @field_validator("node_ids")
    @classmethod
    def check_node_ids(cls, value: list[str]) -> list[str]:
        return _validate_node_id_list(value)


class ExportFigmaImagesInput(FileKeyInput):
    """Input model for export_figma_images."""

    node_ids: list[str] = Field(
        ...,
        min_length=1,
        description="List of Figma node IDs to render as images.",
    )
    format: Literal["png", "svg", "jpg", "pdf"] = Field(
        default="png",
        description="Output image format.",
    )
    scale: float = Field(
        default=1.0,
        ge=0.01,
        le=4.0,
        description="Image scaling factor between 0.01 and 4.0.",
    )
    force_refresh: bool = Field(
        default=False,
        description="When True, bypasses the in-memory cache and fetches fresh image URLs.",
    )

    @field_validator("node_ids")
    @classmethod
    def check_node_ids(cls, value: list[str]) -> list[str]:
        return _validate_node_id_list(value)


class GetFileCommentsInput(FileKeyInput):
    """Input model for get_file_comments."""

    as_md: bool = Field(
        default=True,
        description="Return comment bodies formatted as Markdown when True.",
    )


class PostFileCommentInput(FileKeyInput):
    """Input model for post_file_comment."""

    message: str = Field(..., min_length=1, description="Comment text to post.")
    node_id: str | None = Field(
        default=None,
        description="Optional Figma node ID to anchor the comment.",
    )
    comment_id: str | None = Field(
        default=None,
        description="Optional parent comment ID when posting a reply.",
    )

    @field_validator("message")
    @classmethod
    def check_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message must not be empty.")
        return cleaned

    @field_validator("node_id", "comment_id")
    @classmethod
    def check_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ErrorResponse(BaseModel):
    """Structured error payload returned to MCP clients on failure."""

    error: str
    status_code: int | None = None
    retry_after: int | None = None
    action: str
