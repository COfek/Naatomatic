"""Router node — STUB. Classifies the user's intent into a domain and seeds the
Worker with that domain's tool specs + role-permitted actions. (LLM via runtime.llm
+ registry.specs_for(domain).)"""

from __future__ import annotations

from agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError  # classify -> state["domain"]; init state["messages"]
