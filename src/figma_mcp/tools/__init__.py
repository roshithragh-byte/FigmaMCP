"""Tool registry loader."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from figma_mcp.client import FigmaClient
from figma_mcp.config import Settings
from figma_mcp.tools.comments import register_comments_tools
from figma_mcp.tools.components_styles import register_components_styles_tools
from figma_mcp.tools.compound import register_compound_tools
from figma_mcp.tools.dev_resources import register_dev_resources_tools
from figma_mcp.tools.enterprise import register_enterprise_tools
from figma_mcp.tools.files import register_files_tools
from figma_mcp.tools.projects_folders import register_projects_folders_tools
from figma_mcp.tools.variables import register_variables_tools
from figma_mcp.tools.webhooks import register_webhooks_tools


def register_all_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register all modular domain tools into FastMCP."""
    register_files_tools(mcp, settings, client=client)
    register_components_styles_tools(mcp, settings, client=client)
    register_comments_tools(mcp, settings, client=client)
    register_variables_tools(mcp, settings, client=client)
    register_dev_resources_tools(mcp, settings, client=client)
    register_projects_folders_tools(mcp, settings, client=client)
    register_webhooks_tools(mcp, settings, client=client)
    register_enterprise_tools(mcp, settings, client=client)
    register_compound_tools(mcp, settings, client=client)
