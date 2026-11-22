"""Compound intelligence and workflow tools synthesizing multiple Figma APIs."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import ValidationError

from figma_mcp.client import FigmaAPIError, FigmaClient
from figma_mcp.config import Settings
from figma_mcp.models import CompoundAnalysisInput, FileKeyInput
from figma_mcp.tools.common import (
    check_file_authorization,
    get_client,
    validation_error_dict,
)


def _walk_ast_dependencies(
    node: dict[str, Any],
    instances: list[dict[str, Any]],
    style_refs: set[str],
) -> None:
    node_type = node.get("type")
    if node_type == "INSTANCE":
        instances.append(
            {
                "id": node.get("id"),
                "name": node.get("name"),
                "component_id": node.get("componentId"),
                "is_exposed_instance": node.get("isExposedInstance", False),
            }
        )

    styles = node.get("styles")
    if isinstance(styles, dict):
        for style_type, style_id in styles.items():
            style_refs.add(f"{style_type}:{style_id}")

    for child in node.get("children", []):
        if isinstance(child, dict):
            _walk_ast_dependencies(child, instances, style_refs)


def register_compound_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: FigmaClient | None = None,
) -> None:
    """Register compound analysis tools."""

    @mcp.tool()
    async def analyze_design_system(
        file_key: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Synthesize components, styles, and variables into a unified design system report."""
        try:
            validated = FileKeyInput(file_key=file_key)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            c = get_client(ctx, client)

            # Query components, component_sets, styles, and local variables in parallel
            components_data = await c.get_file_components(validated.file_key)
            styles_data = await c.get_file_styles(validated.file_key)
            component_sets_data = await c.get_file_component_sets(validated.file_key)

            variables_data: dict[str, Any] = {}
            try:
                variables_data = await c.get_local_variables(validated.file_key)
            except FigmaAPIError:
                variables_data = {"meta": {"variableCollections": {}, "variables": {}}}

            comps = components_data.get("meta", {}).get("components", [])
            sets = component_sets_data.get("meta", {}).get("component_sets", [])
            styles = styles_data.get("meta", {}).get("styles", [])

            var_meta = variables_data.get("meta", {})
            collections = var_meta.get("variableCollections", {})
            vars_dict = var_meta.get("variables", {})

            # Categorize styles
            styles_by_type: dict[str, int] = {}
            for s in styles:
                stype = s.get("style_type", "OTHER")
                styles_by_type[stype] = styles_by_type.get(stype, 0) + 1

            return {
                "file_key": validated.file_key,
                "summary": {
                    "total_components": len(comps),
                    "total_component_sets": len(sets),
                    "total_styles": len(styles),
                    "total_variable_collections": len(collections),
                    "total_variables": len(vars_dict),
                },
                "styles_breakdown": styles_by_type,
                "components": [
                    {
                        "key": c.get("key"),
                        "name": c.get("name"),
                        "description": c.get("description", ""),
                    }
                    for c in comps[:50]
                ],
                "component_sets": [
                    {
                        "key": cs.get("key"),
                        "name": cs.get("name"),
                        "description": cs.get("description", ""),
                    }
                    for cs in sets[:50]
                ],
                "variable_collections": [
                    {
                        "id": col_id,
                        "name": col.get("name"),
                        "modes_count": len(col.get("modes", [])),
                    }
                    for col_id, col in collections.items()
                ],
            }
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def check_token_drift(
        file_key: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Compare local and published variables to identify unlinked or drifted tokens."""
        try:
            validated = FileKeyInput(file_key=file_key)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            c = get_client(ctx, client)

            local_vars = await c.get_local_variables(validated.file_key)
            published_vars = await c.get_published_variables(validated.file_key)

            local_meta = local_vars.get("meta", {})
            pub_meta = published_vars.get("meta", {})

            local_map = {v.get("name"): v for v in local_meta.get("variables", {}).values()}
            pub_map = {v.get("name"): v for v in pub_meta.get("variables", {}).values()}

            unpublished_tokens = [name for name in local_map if name not in pub_map]
            modified_or_matching = [name for name in local_map if name in pub_map]

            return {
                "file_key": validated.file_key,
                "drift_summary": {
                    "local_variables_count": len(local_map),
                    "published_variables_count": len(pub_map),
                    "unpublished_local_count": len(unpublished_tokens),
                    "synchronized_tokens_count": len(modified_or_matching),
                },
                "unpublished_tokens": unpublished_tokens[:100],
            }
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def triage_comments(
        file_key: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Categorize file comments into actionable threads, unresolved tasks, and activity."""
        try:
            validated = FileKeyInput(file_key=file_key)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            c = get_client(ctx, client)

            comments_res = await c.get_file_comments(validated.file_key, as_md=True)
            comments = comments_res.get("comments", [])

            threads: dict[str, list[dict[str, Any]]] = {}
            unresolved: list[dict[str, Any]] = []
            authors: dict[str, int] = {}

            for c_obj in comments:
                cid = c_obj.get("id")
                parent_id = c_obj.get("parent_id") or cid
                threads.setdefault(parent_id, []).append(c_obj)

                user = c_obj.get("user", {}).get("handle", "Anonymous")
                authors[user] = authors.get(user, 0) + 1

                if not c_obj.get("resolved_at"):
                    unresolved.append(
                        {
                            "id": cid,
                            "author": user,
                            "created_at": c_obj.get("created_at"),
                            "message": c_obj.get("message"),
                            "node_id": c_obj.get("client_meta", {}).get("node_id"),
                        }
                    )

            return {
                "file_key": validated.file_key,
                "total_comments": len(comments),
                "total_threads": len(threads),
                "unresolved_count": len(unresolved),
                "author_activity": authors,
                "unresolved_action_items": unresolved[:50],
            }
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def build_dependency_graph(
        file_key: str,
        depth: int | None = 3,
        include_remote: bool = True,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Traverse file AST and map component instance relationships and style linkages."""
        try:
            validated = CompoundAnalysisInput(
                file_key=file_key,
                depth=depth,
                include_remote=include_remote,
            )
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            c = get_client(ctx, client)

            file_data = await c.get_file(validated.file_key, depth=validated.depth)
            document = file_data.get("document", {})

            instances: list[dict[str, Any]] = []
            style_refs: set[str] = set()

            _walk_ast_dependencies(document, instances, style_refs)

            # Aggregate instances by componentId
            comp_usage: dict[str, int] = {}
            for inst in instances:
                cid = inst.get("component_id") or "unlinked"
                comp_usage[cid] = comp_usage.get(cid, 0) + 1

            return {
                "file_key": validated.file_key,
                "analyzed_depth": validated.depth,
                "graph_summary": {
                    "total_instances_found": len(instances),
                    "unique_components_referenced": len(comp_usage),
                    "style_references_found": len(style_refs),
                },
                "component_frequency": comp_usage,
                "styles_referenced": sorted(list(style_refs))[:100],
            }
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()

    @mcp.tool()
    async def generate_library_usage_report(
        library_file_key: str,
        asset_type: str = "component",
        group_by: str = "component",
        ctx: Context[Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Aggregate adoption metrics and action trends for library components/styles/variables."""
        try:
            validated = FileKeyInput(file_key=library_file_key)
            auth_err = check_file_authorization(settings, validated.file_key)
            if auth_err is not None:
                return auth_err
            assert ctx is not None
            c = get_client(ctx, client)

            usages = await c.get_library_analytics(
                validated.file_key,
                asset_type=asset_type,
                metric_type="usages",
                group_by=group_by,
            )
            actions = await c.get_library_analytics(
                validated.file_key,
                asset_type=asset_type,
                metric_type="actions",
                group_by=group_by,
            )

            return {
                "library_file_key": validated.file_key,
                "asset_type": asset_type,
                "grouped_by": group_by,
                "usages_data": usages,
                "actions_data": actions,
            }
        except ValidationError as exc:
            return validation_error_dict(exc)
        except FigmaAPIError as exc:
            return exc.to_dict()
