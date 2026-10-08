"""The deployed service: the REST API and the MCP server on one port.

    uv run uvicorn isotherm.app:app --host 0.0.0.0 --port 8000

REST routes as in `isotherm.serve`; MCP (streamable HTTP, stateless) at /mcp.
"""

from __future__ import annotations

import contextlib
import os

from .mcp_server import mcp
from .serve import app

_mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    host=os.environ.get("ISOTHERM_PUBLIC_HOST", "127.0.0.1"),
)


@contextlib.asynccontextmanager
async def _lifespan(_app):
    async with mcp.session_manager.run():
        yield


app.router.lifespan_context = _lifespan
app.mount("/", _mcp_app)  # after the REST routes, so only /mcp falls through to it
