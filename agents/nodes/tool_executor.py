"""Tool Executor node (deterministic, no LLM). Runs the Worker's chosen tool
through the shared registry and puts the ToolOutput back on the state for the
Validator to turn into a message for the Worker's next turn."""

from __future__ import annotations

from agents.state import GraphState


def run(state: GraphState) -> GraphState:
    call = state["tool_to_call"]
    runtime = state["runtime"]
    # Tools self-validate (apply -> rules -> commit/rollback) and return a ToolOutput.
    state["tool_result"] = runtime.run_tool(call["name"], **call["args"])
    return state