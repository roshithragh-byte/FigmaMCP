# Governed Figma Remote MCP Server (Agent Gateway)

Production-ready remote Model Context Protocol (MCP) server and governance gateway in Python wrapping the full surface of the [Figma REST API](https://www.figma.com/developers/api) over **Streamable HTTP** (`FastMCP`), packaged for **Google Cloud Run** with IAM authentication.

## Features

- **Streamable HTTP MCP Transport** (`POST /mcp`) via official `mcp` Python SDK (`FastMCP`, stateless HTTP mode).
- **Security & Mutation Governance**:
  - `FIGMA_READ_ONLY`: Defaults to `true` (secure by default); mutating write actions fail closed with structured `403 Forbidden`.
  - `dry_run=True`: Supported on bulk mutation operations (e.g. `post_variables_bulk_update`) for safe inspection prior to commit.
  - `FIGMA_ALLOWED_FILE_KEYS`: Optional allowlist restricting agent access to specific design file keys.
- **AST Compaction Engine (`compact=True`)**:
  - Recursively strips heavy vector curves, transforms, and export bloat while preserving semantic components, text, and layout parameters (<10% payload size to fit LLM context).
  - Defaults to `compact=False` for 100% backward compatibility.
- **Rate-Limit Shield & In-Memory TTL Cache**:
  - Thread-safe LRU cache (`maxsize=500`, `FIGMA_CACHE_TTL_SECONDS=300`) with SingleFlight async request coalescing to prevent thundering-herd 429 rate limits.
  - `force_refresh=True` parameter to bypass cache on demand. 4xx/5xx/429 errors are never cached.

## 40+ Comprehensive Figma Tools

The server is organized into modular tool domains in `src/figma_mcp/tools/`:

### 1. Files & Nodes (`files.py`)
- `get_figma_file(file_key, depth=2, node_ids=None, compact=False, force_refresh=False)`
- `get_figma_nodes(file_key, node_ids, depth=None, compact=False, force_refresh=False)`
- `export_figma_images(file_key, node_ids, format="png", scale=1.0, force_refresh=False)`
- `get_file_versions(file_key, page_size=30, before=None, after=None)`

### 2. Design System Components & Styles (`components_styles.py`)
- `get_file_components(file_key)`
- `get_file_component_sets(file_key)`
- `get_file_styles(file_key)`
- `get_team_components(team_id, page_size=30, cursor=None)`
- `get_team_styles(team_id, page_size=30, cursor=None)`

### 3. Comments & Reactions (`comments.py`)
- `get_file_comments(file_key, as_md=True)`
- `post_file_comment(file_key, message, node_id=None, comment_id=None)`
- `delete_file_comment(file_key, comment_id)`
- `get_comment_reactions(file_key, comment_id, cursor=None)`
- `post_comment_reaction(file_key, comment_id, emoji)`
- `delete_comment_reaction(file_key, comment_id, emoji)`

### 4. Variables & Design Tokens (`variables.py`)
- `get_local_variables(file_key)`
- `get_published_variables(file_key)`
- `post_variables_bulk_update(file_key, variable_collections=None, variable_modes=None, variables=None, variable_mode_values=None, dry_run=False)`

### 5. Dev Resources (`dev_resources.py`)
- `get_dev_resources(file_key, node_ids=None)`
- `post_dev_resources(dev_resources)`
- `put_dev_resources(dev_resources)`
- `delete_dev_resource(file_key, dev_resource_id)`

### 6. Teams & Folders (`projects_folders.py`)
- `get_team(team_id)`
- `get_team_folders(team_id)`
- `get_folder_files(folder_id)`
- `get_folder_subfolders(folder_id)`
- `create_folder(team_id, name)`

### 7. Webhooks v2 (`webhooks.py`)
- `list_webhooks(context=None, context_id=None)`
- `get_webhook(webhook_id)`
- `create_webhook(event_type, team_id, endpoint, passcode, description=None)`
- `update_webhook(webhook_id, endpoint=None, passcode=None, description=None, status=None)`
- `delete_webhook(webhook_id)`
- `get_webhook_requests(webhook_id)`

### 8. Enterprise & Analytics (`enterprise.py`)
- `get_activity_logs(events=None, start_time=None, end_time=None, limit=50, cursor=None)`
- `get_ai_usage(start_date, end_date, user_email=None, cursor=None)`
- `get_library_analytics(library_file_key, asset_type="component", metric_type="usages", group_by=None, start_date=None, end_date=None)`

### 9. Compound Intelligence Tools (`compound.py`)
- `analyze_design_system(file_key)`: Synthesize components, styles, and variables into a unified design system report.
- `check_token_drift(file_key)`: Compare local and published variables to identify unlinked or drifted tokens.
- `triage_comments(file_key)`: Categorize file comments into actionable threads, unresolved tasks, and author activity.
- `build_dependency_graph(file_key, depth=3, include_remote=True)`: Traverse file AST and map component instance relationships and style linkages.
- `generate_library_usage_report(library_file_key, asset_type="component", group_by="component")`: Aggregate adoption metrics and action trends for library assets.

---

## Local Development

```bash
cp .env.example .env
# Edit .env and set FIGMA_ACCESS_TOKEN

uv sync --all-groups
uv run figma-mcp-server
```

Verify locally:

```bash
curl -s http://localhost:8080/healthz
```

## Lint, Typecheck & Tests

```bash
uv run ruff check .
uv run mypy src tests
uv run pytest -v
```

## Container Build

```bash
docker build -t figma-mcp-server .
docker run --rm -p 8080:8080 -e FIGMA_ACCESS_TOKEN="$FIGMA_ACCESS_TOKEN" figma-mcp-server
```

## Deploy to Google Cloud Run

Ensure `gcloud` is authenticated and `PROJECT_ID` and `FIGMA_ACCESS_TOKEN` are set:

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export FIGMA_ACCESS_TOKEN="figd_..."

chmod +x deploy.sh
./deploy.sh
```

Verify deployment status:

```bash
gcloud run services describe figma-mcp-server --region="${REGION}" --project="${PROJECT_ID}"
```

Connect local MCP clients securely via IAM proxy:

```bash
gcloud run services proxy figma-mcp-server --region="${REGION}" --project="${PROJECT_ID}" --port=8080
```

Then point your Streamable HTTP MCP client to `http://localhost:8080/mcp`.
