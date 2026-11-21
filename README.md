# Figma Remote MCP Server

Production-ready remote Model Context Protocol (MCP) server in Python wrapping the [Figma REST API](https://www.figma.com/developers/api) over **Streamable HTTP** (`FastMCP`), packaged for **Google Cloud Run** with IAM authentication.

## Features

- **Streamable HTTP MCP Transport** (`POST /mcp`) via the official `mcp` Python SDK (`FastMCP`, stateless HTTP mode for horizontal scaling on Cloud Run).
- **Health Probe** (`GET /healthz` returning `200 {"status": "ok"}`).
- **7 Typed Figma Tools**:
  - `get_figma_file(file_key, depth=2, node_ids=None)`
  - `get_figma_nodes(file_key, node_ids, depth=None)`
  - `export_figma_images(file_key, node_ids, format="png", scale=1.0)`
  - `get_file_components(file_key)`
  - `get_file_styles(file_key)`
  - `get_file_comments(file_key, as_md=True)`
  - `post_file_comment(file_key, message, node_id=None, comment_id=None)`
- **Pooled Async Client** (`httpx.AsyncClient`) with structured handling of `401`, `403`, `404`, and `429` (`Retry-After`) responses and zero token/header leakage.
- **Secure Cloud Run Deployment**: Non-root `python:3.11-slim` container, `FIGMA_ACCESS_TOKEN` stored in Secret Manager, and `--no-allow-unauthenticated` IAM enforcement.

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
