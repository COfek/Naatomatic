"""Tool registry — the single catalog of all pillar tools.

Aggregates each pillar's `TOOLS` / `MUTATING` into one namespace. Both the
in-process Tool Executor (agents/nodes/tool_executor.py) and the MCP server
(mcp/server.py) build on this — so tools are written **once** as plain functions
and exposed either way.

Tool names are a single global namespace (the model sees them) — keep them unique.
"""

from __future__ import annotations

from collections.abc import Callable

from tools import (
    adhoc_tools,
    general_knowledge_tools,
    guard_duty_tools,
    logistics_tools,
    network_tools,
)
from tools.base import ToolContext, ToolResult, tool_spec

# Pillar name -> its module (used for routing: the Router picks a pillar,
# the Worker is offered that pillar's tools).
PILLARS = {
    "network": network_tools,
    "logistics": logistics_tools,
    "guard_duty": guard_duty_tools,
    "adhoc": adhoc_tools,
    "general_knowledge": general_knowledge_tools,
}

TOOLS_BY_NAME: dict[str, Callable[..., ToolResult]] = {}
MUTATING: set[str] = set()
PILLAR_OF: dict[str, str] = {}

for _pillar, _mod in PILLARS.items():
    for _fn in _mod.TOOLS:
        if _fn.__name__ in TOOLS_BY_NAME:
            raise RuntimeError(f"Duplicate tool name across pillars: {_fn.__name__}")
        TOOLS_BY_NAME[_fn.__name__] = _fn
        PILLAR_OF[_fn.__name__] = _pillar
    MUTATING |= set(_mod.MUTATING)

SPECS: list[dict] = [tool_spec(fn) for fn in TOOLS_BY_NAME.values()]


def specs_for(pillar: str) -> list[dict]:
    """Tool specs for one pillar (what the Router exposes to that pillar's Worker)."""
    return [tool_spec(fn) for n, fn in TOOLS_BY_NAME.items() if PILLAR_OF[n] == pillar]


def call_tool(ctx: ToolContext, name: str, **args) -> ToolResult:
    """Dispatch a tool by name. Unknown name -> error (the caller can offer
    did-you-mean over TOOLS_BY_NAME keys). Used by the executor and the MCP server."""
    fn = TOOLS_BY_NAME.get(name)
    if fn is None:
        return ToolResult.err(f"Unknown tool: {name}")
    return fn(ctx, **args)
