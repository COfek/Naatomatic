"""Validator node. Hard rules are enforced *inside* tools (apply → rules →
commit/rollback), so a rejected action already comes back as ToolOutput.ok == False.
This node's job is to surface that cleanly to the Worker (turn a rule rejection /
did-you-mean into a message the Worker relays to the user) — never to silently
re-commit. It is the explicit 'engine decides' gate of the §2 boundary."""

from __future__ import annotations

import json

from langchain_core.messages import ToolMessage

from agents.state import GraphState


def run(state: GraphState) -> GraphState:
    call = state["tool_to_call"]
    result = state["tool_result"]

    if result.ok:
        content = result.value if isinstance(result.value, str) else json.dumps(result.value, default=str)
    else:
        content = f"ERROR: {result.error}"
        if result.suggestions:
            content += f" Did you mean one of: {', '.join(result.suggestions)}?"

    state["messages"].append(ToolMessage(content=content, tool_call_id=call["id"]))
    state["tool_to_call"] = None
    return state