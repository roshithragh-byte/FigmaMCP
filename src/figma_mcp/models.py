"""Pydantic models for Figma MCP tool inputs, outputs, and errors."""

from __future__ import annotations

import re
from typing import Any, Literal

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


class GetFileVersionsInput(FileKeyInput):
    """Input model for get_file_versions."""

    page_size: int | None = Field(
        default=30,
        ge=1,
        le=100,
        description="Number of versions to return per page.",
    )
    before: str | None = Field(
        default=None,
        description="Cursor/version ID before which to retrieve versions.",
    )
    after: str | None = Field(
        default=None,
        description="Cursor/version ID after which to retrieve versions.",
    )


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


class DeleteFileCommentInput(FileKeyInput):
    """Input model for delete_file_comment."""

    comment_id: str = Field(..., min_length=1, description="ID of the comment to delete.")


class GetCommentReactionsInput(FileKeyInput):
    """Input model for get_comment_reactions."""

    comment_id: str = Field(..., min_length=1, description="ID of the comment.")
    cursor: str | None = Field(default=None, description="Pagination cursor.")


class PostCommentReactionInput(FileKeyInput):
    """Input model for post_comment_reaction."""

    comment_id: str = Field(..., min_length=1, description="ID of the comment.")
    emoji: str = Field(
        ..., min_length=1, description="Emoji reaction string, e.g. ':eyes:' or '👍'."
    )


class DeleteCommentReactionInput(FileKeyInput):
    """Input model for delete_comment_reaction."""

    comment_id: str = Field(..., min_length=1, description="ID of the comment.")
    emoji: str = Field(..., min_length=1, description="Emoji to remove.")


# Variables
class VariablesBulkUpdateInput(FileKeyInput):
    """Input model for post_variables_bulk_update."""

    variable_collections: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of variable collections to create, update, or delete.",
    )
    variable_modes: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of variable modes to create, update, or delete.",
    )
    variables: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of variables to create, update, or delete.",
    )
    variable_mode_values: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of variable mode values to set.",
    )
    dry_run: bool = Field(
        default=False,
        description="When True, validates changes and simulates diff without committing to Figma.",
    )


# Dev Resources
class GetDevResourcesInput(FileKeyInput):
    """Input model for get_dev_resources."""

    node_ids: list[str] | None = Field(
        default=None,
        description="Optional list of node IDs to filter dev resources for.",
    )


class PostDevResourcesInput(BaseModel):
    """Input model for post_dev_resources."""

    dev_resources: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="List of dev resources to attach ({file_key, node_id, name, url}).",
    )


class PutDevResourcesInput(BaseModel):
    """Input model for put_dev_resources."""

    dev_resources: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="List of dev resources to update ({id, file_key, name, url}).",
    )


class DeleteDevResourceInput(FileKeyInput):
    """Input model for delete_dev_resource."""

    dev_resource_id: str = Field(..., min_length=1, description="ID of the dev resource to delete.")


# Projects & Folders
class TeamIdInput(BaseModel):
    """Input model for team endpoints."""

    team_id: str = Field(..., min_length=1, description="Team ID.")


class FolderIdInput(BaseModel):
    """Input model for folder endpoints."""

    folder_id: str = Field(..., min_length=1, description="Folder / project ID.")


class CreateFolderInput(TeamIdInput):
    """Input model for create_folder."""

    name: str = Field(..., min_length=1, description="Name of the new folder/project.")


# Webhooks
class WebhooksListInput(BaseModel):
    """Input model for list_webhooks."""

    context: Literal["team", "project", "folder"] | None = Field(
        default=None,
        description="Context level of webhooks.",
    )
    context_id: str | None = Field(
        default=None,
        description="ID of the context (team ID or project/folder ID).",
    )


class WebhookIdInput(BaseModel):
    """Input model for single webhook operations."""

    webhook_id: str = Field(..., min_length=1, description="Webhook ID.")


class CreateWebhookInput(BaseModel):
    """Input model for create_webhook."""

    event_type: str = Field(
        ...,
        description="Event type (e.g. 'FILE_UPDATE', 'FILE_VERSION_UPDATE', 'FILE_COMMENT').",
    )
    team_id: str = Field(..., min_length=1, description="Team ID.")
    endpoint: str = Field(..., min_length=1, description="HTTPS callback URL.")
    passcode: str = Field(
        ..., min_length=1, description="Secret passcode sent with each webhook event."
    )
    description: str | None = Field(
        default=None, description="Optional description of the webhook."
    )


class UpdateWebhookInput(WebhookIdInput):
    """Input model for update_webhook."""

    endpoint: str | None = Field(default=None, description="New HTTPS callback URL.")
    passcode: str | None = Field(default=None, description="New secret passcode.")
    description: str | None = Field(default=None, description="New description.")
    status: Literal["ACTIVE", "PAUSED"] | None = Field(default=None, description="Webhook status.")


# Enterprise & Analytics
class ActivityLogsInput(BaseModel):
    """Input model for get_activity_logs."""

    events: str | None = Field(default=None, description="Comma-separated event names.")
    start_time: str | None = Field(
        default=None, description="Start timestamp in ISO 8601 or UNIX epoch."
    )
    end_time: str | None = Field(
        default=None, description="End timestamp in ISO 8601 or UNIX epoch."
    )
    limit: int | None = Field(default=50, ge=1, le=500, description="Max events to return.")
    cursor: str | None = Field(default=None, description="Pagination cursor.")


class AIUsageInput(BaseModel):
    """Input model for get_ai_usage."""

    start_date: str = Field(..., description="Start date (YYYY-MM-DD).")
    end_date: str = Field(..., description="End date (YYYY-MM-DD).")
    user_email: str | None = Field(default=None, description="Optional user email filter.")
    cursor: str | None = Field(default=None, description="Pagination cursor.")


class LibraryAnalyticsInput(BaseModel):
    """Input model for get_library_analytics."""

    library_file_key: str = Field(..., description="Figma library file key.")
    asset_type: Literal["component", "style", "variable"] = Field(
        default="component",
        description="Asset type to query.",
    )
    metric_type: Literal["usages", "actions"] = Field(
        default="usages",
        description="Metric type: 'usages' (adoption) or 'actions' (insertions/detachments).",
    )
    group_by: Literal["component", "style", "variable", "team", "file"] | None = Field(
        default=None,
        description="Dimension to group analytics by.",
    )
    start_date: str | None = Field(default=None, description="Start date (YYYY-MM-DD).")
    end_date: str | None = Field(default=None, description="End date (YYYY-MM-DD).")


# Compound Tools Input
class CompoundAnalysisInput(FileKeyInput):
    """Input model for compound analysis tools."""

    include_remote: bool = Field(
        default=True,
        description="Whether to analyze dependencies and references to remote libraries.",
    )
    depth: int | None = Field(
        default=3,
        ge=1,
        le=10,
        description="Depth of document AST traversal for node analysis.",
    )


class ErrorResponse(BaseModel):
    """Structured error payload returned to MCP clients on failure."""

    error: str
    status_code: int | None = None
    retry_after: int | None = None
    action: str
