"""Tool registry — the single catalog of all domain tools.

Aggregates each domain's `TOOLS` / `MUTATING` into one namespace. Both the
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
from tool_infra.base import ToolContext, ToolOutput, args_model, tool_spec

# Domain name -> its tools module (used for routing: the Router picks a domain,
# the Worker is offered that domain's tools).
DOMAINS = {
    "network": network_tools,
    "logistics": logistics_tools,
    "guard_duty": guard_duty_tools,
    "adhoc": adhoc_tools,
    "general_knowledge": general_knowledge_tools,
}

TOOLS_BY_NAME: dict[str, Callable[..., ToolOutput]] = {}
MUTATING: set[str] = set()
DOMAIN_OF: dict[str, str] = {}

for _domain, _mod in DOMAINS.items():
    for _fn in _mod.TOOLS:
        if _fn.__name__ in TOOLS_BY_NAME:
            raise RuntimeError(f"Duplicate tool name across domains: {_fn.__name__}")
        TOOLS_BY_NAME[_fn.__name__] = _fn
        DOMAIN_OF[_fn.__name__] = _domain
    MUTATING |= set(_mod.MUTATING)

SPECS: list[dict] = [tool_spec(fn) for fn in TOOLS_BY_NAME.values()]


def specs_for(domain: str) -> list[dict]:
    """Tool specs for one domain (what the Router exposes to that domain's Worker)."""
    return [tool_spec(fn) for n, fn in TOOLS_BY_NAME.items() if DOMAIN_OF[n] == domain]


def call_tool(ctx: ToolContext, name: str, **args) -> ToolOutput:
    """Dispatch a tool by name, validating the model-supplied `args` through the
    tool's Pydantic args model. Unknown name / invalid args -> error ToolOutput
    (the caller can offer did-you-mean over TOOLS_BY_NAME keys). Used by both the
    in-process executor and the MCP server."""
    fn = TOOLS_BY_NAME.get(name)
    if fn is None:
        return ToolOutput.err(f"Unknown tool: {name}")
    model = args_model(fn)
    if model is not None:
        try:
            return fn(ctx, model(**args))          # validated args object
        except Exception as exc:                   # pydantic ValidationError etc.
            return ToolOutput.err(f"Invalid arguments for {name}: {exc}")
    return fn(ctx, **args)                          # legacy/stub (keyword args)
