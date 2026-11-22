# Governed Figma Remote MCP Server (Agent Gateway)

[![CI](https://github.com/roshithragh-byte/FigmaMCP/actions/workflows/figma-mcp-agent.yml/badge.svg)](https://github.com/roshithragh-byte/FigmaMCP/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/mcp-FastMCP-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Production-ready remote Model Context Protocol (MCP) server and governance gateway in Python wrapping the full surface of the [Figma REST API](https://www.figma.com/developers/api) (v1 and v2) over **Streamable HTTP** (`FastMCP`), packaged for **Google Cloud Run** with IAM authentication.

Tailored for autonomous coding agents (Claude Code, Antigravity, Devin, Cursor) and headless CI/CD design-to-code pipelines.

---

## Architecture & Governance Highlights

- **Streamable HTTP MCP Transport** (`POST /mcp`): Built on the official Python MCP SDK using FastMCP stateless HTTP transport with Server-Sent Events (SSE) streaming support.
- **Fail-Closed Write Safety & Mutation Policy**:
  - `FIGMA_READ_ONLY`: Defaults to `true` (secure by default); mutating write actions fail closed with structured `HTTP 403 Forbidden`.
  - `dry_run=True`: Supported on bulk mutation operations (e.g. `post_variables_bulk_update`) for safe AST validation and diff simulation prior to committing changes to Figma.
  - `FIGMA_ALLOWED_FILE_KEYS`: Optional comma-separated allowlist restricting agent access to specific design file keys, rejecting unauthorized files prior to dispatch.
- **AST Compaction Engine (`compact=True`)**:
  - Recursively strips heavy vector curves, transforms, and export bloat while preserving semantic components, text, and layout parameters (<10% payload size to fit LLM context windows).
  - Defaults to `compact=False` for 100% backward compatibility.
- **Rate-Limit Shield & In-Memory TTL Cache**:
  - Thread-safe LRU cache (`maxsize=500`, `FIGMA_CACHE_TTL_SECONDS=300`) with `SingleFlight` async request coalescing to deduplicate concurrent agent requests and eliminate upstream Figma `429 Too Many Requests` rate limits.
  - `force_refresh=True` parameter to bypass cache on demand. 4xx/5xx/429 errors are never cached.
- **Hybrid Authentication**:
  - Supports standard Personal Access Tokens (`X-Figma-Token: figd_...`) and Enterprise OAuth2 Bearer tokens (`Authorization: Bearer ...`).
  - Strict credential hygiene: tokens are suppressed in `repr(Settings)`, silenced in HTTP loggers, and scrubbed via `_sanitize_text` to prevent leakage in error responses.

---

## 41 Comprehensive Figma Tools

The server is organized into modular tool domains in `src/figma_mcp/tools/`:

### 1. Files & Nodes (`src/figma_mcp/tools/files.py`)
- `get_figma_file(file_key, depth=2, node_ids=None, compact=False, force_refresh=False)`: Retrieve file document tree and metadata. Defaults to `depth=2` to avoid payload bloat.
- `get_figma_nodes(file_key, node_ids, depth=None, compact=False, force_refresh=False)`: Query specific node subtrees with optional AST compaction.
- `export_figma_images(file_key, node_ids, format="png", scale=1.0, force_refresh=False)`: Render and return download URLs for nodes in `png`, `svg`, `jpg`, or `pdf`.
- `get_file_versions(file_key, page_size=30, before=None, after=None)`: Retrieve the complete version history of a file.

### 2. Design System Components & Styles (`src/figma_mcp/tools/components_styles.py`)
- `get_file_components(file_key)`: List published components defined in a file.
- `get_file_component_sets(file_key)`: List published component variant sets in a file.
- `get_file_styles(file_key)`: List published styles (color, text, effect, grid) in a file.
- `get_team_components(team_id, page_size=30, cursor=None)`: List all published components in a team library.
- `get_team_styles(team_id, page_size=30, cursor=None)`: List all published styles in a team library.

### 3. Comments & Reactions (`src/figma_mcp/tools/comments.py`)
- `get_file_comments(file_key, as_md=True)`: Retrieve comments with parent/reply hierarchy and markdown formatting.
- `post_file_comment(file_key, message, node_id=None, comment_id=None)`: Post a new comment or reply to an existing comment thread. *(Requires `FIGMA_READ_ONLY=false`)*
- `delete_file_comment(file_key, comment_id)`: Delete a comment from a Figma file. *(Requires `FIGMA_READ_ONLY=false`)*
- `get_comment_reactions(file_key, comment_id, cursor=None)`: List emoji reactions on a comment.
- `post_comment_reaction(file_key, comment_id, emoji)`: Add an emoji reaction to a comment. *(Requires `FIGMA_READ_ONLY=false`)*
- `delete_comment_reaction(file_key, comment_id, emoji)`: Remove an emoji reaction from a comment. *(Requires `FIGMA_READ_ONLY=false`)*

### 4. Variables & Design Tokens (`src/figma_mcp/tools/variables.py`)
- `get_local_variables(file_key)`: Read all local variable collections, modes, and values.
- `get_published_variables(file_key)`: Read published variable collections across team libraries.
- `post_variables_bulk_update(file_key, variable_collections=None, variable_modes=None, variables=None, variable_mode_values=None, dry_run=False)`: Atomically create, update, or delete variables and collections. Set `dry_run=True` to simulate diffs without committing. *(Write commit requires `FIGMA_READ_ONLY=false`)*

### 5. Dev Resources (`src/figma_mcp/tools/dev_resources.py`)
- `get_dev_resources(file_key, node_ids=None)`: List external developer links (GitHub, Jira, Storybook, docs) attached to nodes.
- `post_dev_resources(dev_resources)`: Batch-attach dev links to nodes (`[{file_key, node_id, name, url}]`). *(Requires `FIGMA_READ_ONLY=false`)*
- `put_dev_resources(dev_resources)`: Batch-update existing dev links (`[{id, file_key, name, url}]`). *(Requires `FIGMA_READ_ONLY=false`)*
- `delete_dev_resource(file_key, dev_resource_id)`: Delete an attached dev resource link. *(Requires `FIGMA_READ_ONLY=false`)*

### 6. Teams & Folders (`src/figma_mcp/tools/projects_folders.py`)
- `get_team(team_id)`: Retrieve team details and sharing permissions.
- `get_team_folders(team_id)`: List all top-level team folders (v2 API).
- `get_folder_files(folder_id)`: List all Figma files inside a specific folder.
- `get_folder_subfolders(folder_id)`: List nested subfolder structures.
- `create_folder(team_id, name)`: Create a new project folder in a team. *(Requires `FIGMA_READ_ONLY=false`)*

### 7. Webhooks v2 (`src/figma_mcp/tools/webhooks.py`)
- `list_webhooks(context=None, context_id=None)`: List configured team/project webhooks.
- `get_webhook(webhook_id)`: Inspect specific webhook configuration.
- `create_webhook(event_type, team_id, endpoint, passcode, description=None)`: Subscribe to webhook events (`FILE_UPDATE`, `FILE_COMMENT`, etc.). *(Requires `FIGMA_READ_ONLY=false`)*
- `update_webhook(webhook_id, endpoint=None, passcode=None, description=None, status=None)`: Modify webhook endpoint or toggle `ACTIVE`/`PAUSED`. *(Requires `FIGMA_READ_ONLY=false`)*
- `delete_webhook(webhook_id)`: Delete a webhook subscription. *(Requires `FIGMA_READ_ONLY=false`)*
- `get_webhook_requests(webhook_id)`: Inspect recent delivery attempts and webhook health.

### 8. Enterprise & Analytics (`src/figma_mcp/tools/enterprise.py`)
- `get_activity_logs(events=None, start_time=None, end_time=None, limit=50, cursor=None)`: Query organization audit and security activity logs. *(Requires Enterprise Admin token)*
- `get_ai_usage(start_date, end_date, user_email=None, cursor=None)`: Inspect daily AI credit usage per user. *(Requires Enterprise Admin token)*
- `get_library_analytics(library_file_key, asset_type="component", metric_type="usages", group_by=None, start_date=None, end_date=None)`: Query adoption metrics (`usages`) or insert/detach trends (`actions`) for components, styles, or variables.

### 9. Compound Intelligence Workflows (`src/figma_mcp/tools/compound.py`)
- `analyze_design_system(file_key)`: Combines components, variants, styles, and variable tokens into an executive inventory report.
- `check_token_drift(file_key)`: Cross-references local variables against published libraries to highlight unlinked, drifted, or unpublished tokens.
- `triage_comments(file_key)`: Aggregates unresolved comment threads, identifies active participants, and extracts actionable developer tasks.
- `build_dependency_graph(file_key, depth=3, include_remote=True)`: Traverses AST to map component instance frequencies, style linkages, and remote library references.
- `generate_library_usage_report(library_file_key, asset_type="component", group_by="component")`: Aggregates usage metrics and action events for design system adoption tracking.

---

## Configuration Reference

Set these environment variables in `.env` or your deployment platform:

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `FIGMA_ACCESS_TOKEN` | String | **Required** | Figma Personal Access Token (`figd_...`) or OAuth Bearer token. |
| `FIGMA_READ_ONLY` | Boolean | `true` | When `true`, blocks all mutating API calls (comments, webhooks, variables, folders). |
| `FIGMA_ALLOWED_FILE_KEYS` | String | `None` (All) | Optional comma-separated list of allowed file keys (e.g. `key1,key2`). |
| `FIGMA_API_BASE_URL` | String | `https://api.figma.com` | Base Figma API URL (supports `/v1` and `/v2` endpoints). |
| `FIGMA_CACHE_TTL_SECONDS` | Float | `300.0` | Cache time-to-live in seconds for file ASTs and node queries. |
| `FIGMA_CACHE_MAX_SIZE` | Integer | `500` | Maximum items stored in the in-memory LRU cache. |
| `FIGMA_TIMEOUT_SECONDS` | Float | `30.0` | HTTP client request timeout. |
| `FIGMA_MAX_CONNECTIONS` | Integer | `20` | Maximum concurrent connections in the connection pool. |
| `FIGMA_MAX_KEEPALIVE_CONNECTIONS` | Integer | `10` | Maximum idle keep-alive connections in the pool. |
| `HOST` | String | `0.0.0.0` | Host binding for the MCP server. |
| `PORT` | Integer | `8080` | Port binding for the MCP server. |
| `LOG_LEVEL` | String | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## Connecting to MCP Clients

### Claude Code / Antigravity / Cursor Configuration

Add this server to your MCP settings file (`~/.claude/settings.json` or project `.mcp.json`):

#### Local Python Executable
```json
{
  "mcpServers": {
    "figma": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/figma-mcp-server",
        "run",
        "figma-mcp-server"
      ],
      "env": {
        "FIGMA_ACCESS_TOKEN": "figd_your_token_here",
        "FIGMA_READ_ONLY": "false"
      }
    }
  }
}
```

#### Remote Streamable HTTP (via Cloud Run or Gateway Proxy)
```json
{
  "mcpServers": {
    "figma": {
      "url": "http://localhost:8080/mcp",
      "transport": "http"
    }
  }
}
```

---

## Local Development

```bash
cp .env.example .env
# Edit .env and set your FIGMA_ACCESS_TOKEN

# Install dependencies with uv
uv sync --all-groups

# Run the server locally
uv run figma-mcp-server
```

Verify service liveness:

```bash
curl -s http://localhost:8080/healthz
# {"status":"ok"}
```

### Running Tests and Linting

```bash
# Run linter checks
uv run ruff check .

# Run type checking
uv run mypy src tests

# Run complete automated test suite (30 test cases)
uv run pytest -v
```

---

## Container Build & Cloud Deployment

### Docker Build

```bash
docker build -t figma-mcp-server .
docker run --rm -p 8080:8080 -e FIGMA_ACCESS_TOKEN="$FIGMA_ACCESS_TOKEN" figma-mcp-server
```

### Deploy to Google Cloud Run

Ensure `gcloud` is authenticated and configured:

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

Proxy remote Cloud Run service locally over authenticated IAM:

```bash
gcloud run services proxy figma-mcp-server --region="${REGION}" --project="${PROJECT_ID}" --port=8080
```
