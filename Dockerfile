# Single OCI container (D-10.2): the same image runs on Fly.io for the
# prototype and would run unchanged on Azure Government / GovCloud ECS.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.13-slim-bookworm
RUN useradd --create-home appuser
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
EXPOSE 8080
CMD ["uvicorn", "ttb_label_reviewer.main:app", "--host", "0.0.0.0", "--port", "8080"]
