"""Worker node — STUB. The ReAct step: given the transcript + the pillar's tools,
the model either emits a tool call (-> state["tool_to_call"]) or a final answer
(-> state["final_answer"]). Must NOT fabricate args — ask the user instead (DESIGN §2).
Increments state["turn"]. (LLM via runtime.llm.call_with_tools.)"""

from __future__ import annotations

from agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError  # set tool_to_call XOR final_answer; turn += 1
