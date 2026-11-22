"""Figma MCP tools for comments, replies, deletion, and reactions."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import (
    DeleteCommentReactionInput,
    DeleteFileCommentInput,
    GetCommentReactionsInput,
    GetFileCommentsInput,
    PostCommentReactionInput,
    PostFileCommentInput,
)
from figma_mcp.tools.common import (
    check_file_authorization,
    check_read_only,
    get_client,
    validation_error_dict,
)


def register_comments_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register tools for comment threads and reactions."""

    @mcp.tool()
    async def get_file_comments(
        file_key: str,
        as_md: bool = True,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve comments on a Figma file, optionally formatted as Markdown."""
        try:
            validated = GetFileCommentsInput(file_key=file_key, as_md=as_md)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).get_file_comments(
                validated.file_key,
                as_md=validated.as_md,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def post_file_comment(
        file_key: str,
        message: str,
        node_id: str | None = None,
        comment_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Post a new comment on a Figma file or reply to an existing comment."""
        try:
            ro_err = check_read_only(settings, "commenting")
            if ro_err is not None:
                return ro_err

            validated = PostFileCommentInput(
                file_key=file_key,
                message=message,
                node_id=node_id,
                comment_id=comment_id,
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).post_file_comment(
                validated.file_key,
                validated.message,
                node_id=validated.node_id,
                comment_id=validated.comment_id,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def delete_file_comment(
        file_key: str,
        comment_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Delete a comment on a Figma file."""
        try:
            ro_err = check_read_only(settings, "deleting comments")
            if ro_err is not None:
                return ro_err

            validated = DeleteFileCommentInput(file_key=file_key, comment_id=comment_id)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).delete_file_comment(
                validated.file_key,
                validated.comment_id,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def get_comment_reactions(
        file_key: str,
        comment_id: str,
        cursor: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve emoji reactions on a specific Figma comment."""
        try:
            validated = GetCommentReactionsInput(
                file_key=file_key, comment_id=comment_id, cursor=cursor
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).get_comment_reactions(
                validated.file_key,
                validated.comment_id,
                cursor=validated.cursor,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def post_comment_reaction(
        file_key: str,
        comment_id: str,
        emoji: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Add an emoji reaction to a comment."""
        try:
            ro_err = check_read_only(settings, "posting reactions")
            if ro_err is not None:
                return ro_err

            validated = PostCommentReactionInput(
                file_key=file_key, comment_id=comment_id, emoji=emoji
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).post_comment_reaction(
                validated.file_key,
                validated.comment_id,
                validated.emoji,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def delete_comment_reaction(
        file_key: str,
        comment_id: str,
        emoji: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Remove an emoji reaction from a comment."""
        try:
            ro_err = check_read_only(settings, "deleting reactions")
            if ro_err is not None:
                return ro_err

            validated = DeleteCommentReactionInput(
                file_key=file_key, comment_id=comment_id, emoji=emoji
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            return await get_client(ctx, client).delete_comment_reaction(
                validated.file_key,
                validated.comment_id,
                validated.emoji,
            )
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()
