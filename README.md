# Governed Figma Remote MCP Server (Agent Gateway)

Production-ready remote Model Context Protocol (MCP) server and governance gateway in Python wrapping the [Figma REST API](https://www.figma.com/developers/api) over **Streamable HTTP** (`FastMCP`), packaged for **Google Cloud Run** with IAM authentication.

## Features

- **Streamable HTTP MCP Transport** (`POST /mcp`) via official `mcp` Python SDK (`FastMCP`, stateless HTTP mode).
- **Security & Authorization Gate**:
  - `FIGMA_READ_ONLY`: Defaults to `true` (secure by default); mutating comment tools fail closed with structured `403 Forbidden`.
  - `FIGMA_ALLOWED_FILE_KEYS`: Optional allowlist restricting agent access to specific design file keys.
- **AST Compaction Engine (`compact=True`)**:
  - Recursively strips heavy vector curves, transforms, and export bloat while preserving semantic components, text, and layout parameters (<10% payload size to fit LLM context).
  - Defaults to `compact=False` for 100% backward compatibility.
- **Rate-Limit Shield & In-Memory TTL Cache**:
  - Thread-safe LRU cache (`maxsize=500`, `FIGMA_CACHE_TTL_SECONDS=300`) with SingleFlight async request coalescing to prevent thundering-herd 429 rate limits.
  - `force_refresh=True` parameter to bypass cache on demand. 4xx/5xx/429 errors are never cached.
- **7 Typed Figma Tools**:
  - `get_figma_file(file_key, depth=2, node_ids=None, compact=False, force_refresh=False)`
  - `get_figma_nodes(file_key, node_ids, depth=None, compact=False, force_refresh=False)`
  - `export_figma_images(file_key, node_ids, format="png", scale=1.0, force_refresh=False)`
  - `get_file_components(file_key)`
  - `get_file_styles(file_key)`
  - `get_file_comments(file_key, as_md=True)`
  - `post_file_comment(file_key, message, node_id=None, comment_id=None)`
- **Cloud Run & CI/CD Integration**:
  - Non-root `python:3.11-slim` container deployed with `--max-instances=1` (for cache coherence) and `--no-allow-unauthenticated`.
  - Reusable GitHub Actions workflow (`.github/workflows/figma-mcp-agent.yml`) with Google Cloud Workload Identity Federation (WIF).

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
uv run mypy src
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
