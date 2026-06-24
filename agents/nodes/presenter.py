"""Presenter node. Turns the final result into a clean, user-facing answer
(chat-only, bilingual HE/EN — match the user's language). Today the Worker already
writes a direct final answer, so this node is a thin pass-through — split out a real
formatting LLM call here if/when answers need polishing."""

from __future__ import annotations

from agents.state import GraphState


def run(state: GraphState) -> GraphState:
    state["final_answer"] = state.get("final_answer") or "(no answer)"
    return state