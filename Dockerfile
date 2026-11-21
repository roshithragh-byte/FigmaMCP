# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.5-python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies deterministically from pyproject.toml (and uv.lock if present)
COPY pyproject.toml ./
COPY uv.lock* ./
RUN if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev --no-install-project; \
    else \
        uv sync --no-dev --no-install-project; \
    fi

COPY src ./src
RUN if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev; \
    else \
        uv sync --no-dev; \
    fi

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080 \
    HOST=0.0.0.0

WORKDIR /app

RUN groupadd --gid 10001 appuser && \
    useradd --uid 10001 --gid 10001 --shell /usr/sbin/nologin --create-home appuser

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src

USER appuser

EXPOSE 8080

CMD ["figma-mcp-server"]
