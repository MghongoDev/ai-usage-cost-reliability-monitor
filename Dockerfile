FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install deps first for layer caching
COPY pyproject.toml .python-version ./
RUN uv sync --no-dev --no-install-project

COPY src/ src/
RUN uv sync --no-dev

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "monitor.simulator.app:app", "--host", "0.0.0.0", "--port", "8001"]
