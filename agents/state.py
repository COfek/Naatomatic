"""Shared graph state passed between nodes (LangGraph). Every node receives and
returns this dict. Keep it the single shared shape — don't add per-node ad-hoc keys."""

from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    runtime: Any            # services.agent_runtime.AgentRuntime (session, llm, actor)
    user_message: str       # the incoming chat message
    pillar: str | None      # chosen by the Router: network/logistics/guard_duty/adhoc/general_knowledge
    messages: list[dict]    # running ReAct transcript for the Worker
    tool_to_call: dict | None   # {"name": str, "args": dict} the Worker decided on
    tool_result: Any        # ToolResult from the Tool Executor
    final_answer: str | None    # set when done -> Presenter formats it
    turn: int
