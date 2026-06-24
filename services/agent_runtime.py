"""Per-run agent runtime — STUB. Carries everything a single chat turn needs:
the authenticated ToolContext (session + actor + roles), the LLM client, and
telemetry. Passed into the graph; keeps infra out of tool/node signatures.
(Modeled on agents_day2/services/agent_runtime.py.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.llm import LLMClient
from tools.base import ToolContext, ToolResult
from tools.registry import call_tool


@dataclass
class AgentRuntime:
    ctx: ToolContext          # session + actor + roles (from auth.authenticate)
    llm: LLMClient = field(default_factory=LLMClient)
    tool_metrics: list = field(default_factory=list)
    llm_metrics: list = field(default_factory=list)

    def run_tool(self, name: str, **args) -> ToolResult:
        """Execute a tool through the shared registry (records telemetry)."""
        result = call_tool(self.ctx, name, **args)
        self.tool_metrics.append({"tool": name, "ok": result.ok})
        return result
