"""Presenter node — STUB. Turns the final result into a clean, user-facing answer
(chat-only, bilingual HE/EN — match the user's language). Sets state["final_answer"].
May start folded into the Worker and split out later. (LLM via runtime.llm.)"""

from __future__ import annotations

from agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError  # format state -> state["final_answer"]
