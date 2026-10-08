# The isotherm API and MCP server. No torch or scikit-learn: serving needs neither.
#   docker build -t isotherm . && docker run -p 8000:8000 isotherm
# Then: GET /health, GET /ladder/NY, POST /decide, MCP (streamable HTTP) at /mcp.
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY shadow/frozen.json ./shadow/frozen.json
RUN uv sync --locked --no-dev --no-default-groups
# Kalshi market data is public: no API key goes in this image.
ENV ISOTHERM_PUBLIC_HOST=0.0.0.0 PORT=8000 ISOTHERM_ANSWER_LOG=/app/data/served/answers.jsonl
EXPOSE 8000
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn isotherm.app:app --host 0.0.0.0 --port ${PORT}"]
