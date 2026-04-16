# syntax=docker/dockerfile:1.7

# Two-stage image using the official uv binary pattern from
# https://docs.astral.sh/uv/guides/integration/docker/ — deps install on a
# cached layer, project source is copied on top.

FROM python:3.12-slim-trixie AS base

# uv binary (pinned) — lifted from the official distroless image.
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install deps in their own layer so source-only changes don't bust the cache.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --locked --no-install-project --no-dev

# Copy project and install it.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:${PATH}" \
    FLASK_APP=wsgi:app

EXPOSE 8000

# Run via gunicorn. Uploads/DB are expected to be on a mounted volume.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "wsgi:app"]
