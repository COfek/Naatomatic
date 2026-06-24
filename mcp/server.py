"""MCP server — STUB. Exposes the SAME tools (tools/registry.py) over MCP, so the
tool code is written once and reachable either in-process or via MCP.

Add `mcp` to requirements when implementing. Lazy import keeps this module loadable
without it. Each registered MCP tool authenticates (services.auth) to build a
ToolContext, then dispatches via registry.call_tool — identical to the in-process
Tool Executor.

⚠️ NAME CLASH: this local package is named `mcp`, which shadows the PyPI `mcp`
library. Before implementing, rename this folder to `mcp_server/` (recommended) so
`from mcp.server.fastmcp import FastMCP` resolves to the library, not us.
"""

from __future__ import annotations

from models.db import create_session, get_engine
from services.auth import authenticate
from tools.registry import SPECS, call_tool


def build_server():
    """Register every registry tool with an MCP server and return it.
    (Lazy import so the package loads without the `mcp` dependency.)"""
    from mcp.server.fastmcp import FastMCP  # type: ignore

    server = FastMCP("naatomatic")

    # TODO for the MCP owner:
    #   - resolve the caller's personal_number (MCP session / arg) -> ToolContext via authenticate()
    #   - for each spec in SPECS, register an MCP tool that calls registry.call_tool(ctx, name, **args)
    #   - map ToolOutput -> MCP response (ok -> value; not ok -> error + suggestions)
    _ = (SPECS, call_tool, authenticate, create_session, get_engine)
    raise NotImplementedError("Wire SPECS -> MCP tool registrations.")


if __name__ == "__main__":
    build_server().run()
