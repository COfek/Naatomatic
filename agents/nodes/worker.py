"""Worker node. The ReAct step: given the transcript + the domain's tools, the model
either emits a tool call (-> state["tool_to_call"]) or a final answer
(-> state["final_answer"]). Must NOT fabricate args — ask the user instead (DESIGN §2).
Increments state["turn"]. (LLM via runtime.llm.call_with_tools.)"""

from __future__ import annotations

from agents.state import GraphState
from tools.registry import specs_for


def run(state: GraphState) -> GraphState:
    runtime = state["runtime"]
    specs = specs_for(state["domain"])

    tool_choice = "required" if state.get("turn", 0) == 0 else "auto"
    response = runtime.llm.call_with_tools(messages=state["messages"], tools=specs, tool_choice=tool_choice)
    state["messages"].append(response)
    state["turn"] = state.get("turn", 0) + 1

    if response.tool_calls:
        call = response.tool_calls[0]  # one tool call per turn keeps the loop simple
        state["tool_to_call"] = {"name": call["name"], "args": call["args"], "id": call["id"]}
        state["final_answer"] = None
    else:
        state["tool_to_call"] = None
        state["final_answer"] = response.content

    return state