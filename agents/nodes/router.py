"""Router node — STUB. Classifies the user's intent into a pillar and seeds the
Worker with that pillar's tool specs + role-permitted actions. (LLM via runtime.llm
+ registry.specs_for(pillar).)"""

from __future__ import annotations

from agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError  # classify -> state["pillar"]; init state["messages"]
