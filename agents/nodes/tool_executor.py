"""Tool Executor node — STUB (deterministic, no LLM). Runs the Worker's chosen
tool through the shared registry and puts the ToolOutput back on the state for the
Worker's next turn."""

from __future__ import annotations

from agents.state import GraphState


def run(state: GraphState) -> GraphState:
    call = state.get("tool_to_call") or {}
    runtime = state["runtime"]
    # Tools self-validate (apply -> rules -> commit/rollback) and return a ToolOutput.
    result = runtime.run_tool(call["name"], **call.get("args", {}))
    state["tool_result"] = result
    state["tool_to_call"] = None
    # TODO: append a result message to state["messages"] for the Worker.
    return state
