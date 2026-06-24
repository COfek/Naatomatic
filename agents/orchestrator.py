"""Orchestrator — STUB. Builds and runs the LangGraph node graph (DESIGN §2):

    START → router → worker ⇄ tool_executor → validator → presenter → END
                       ▲__________|  (loop until the Worker emits a final answer)

`langgraph` is imported lazily so this module loads without it. Add `langgraph`
to requirements when implementing.
"""

from __future__ import annotations

from typing import Any

from agents.nodes import presenter, router, tool_executor, validator, worker
from agents.state import GraphState
from services.agent_runtime import AgentRuntime

MAX_TURNS = 20


def _route_after_worker(state: GraphState) -> str:
    """Loop to the tool executor while the Worker wants a tool; else go present."""
    if state.get("final_answer") is not None or state.get("turn", 0) >= MAX_TURNS:
        return "presenter"
    return "tool_executor" if state.get("tool_to_call") else "worker"


def build_graph() -> Any:
    """Wire the nodes into a LangGraph StateGraph. Implement the node bodies in
    agents/nodes/*. (Lazy import so the package loads without langgraph installed.)"""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(GraphState)
    #g.add_node("router", router.run)
    g.add_node("worker", worker.run)
    g.add_node("tool_executor", tool_executor.run)
    #g.add_node("validator", validator.run)
    g.add_node("presenter", presenter.run)

    g.add_edge(START, "router")
    g.add_edge("router", "worker")
    g.add_conditional_edges("worker", _route_after_worker,
                            {"tool_executor": "tool_executor", "worker": "worker", "presenter": "presenter"})
    g.add_edge("tool_executor", "validator")
    g.add_edge("validator", "worker")
    g.add_edge("presenter", END)
    return g.compile()


def run(user_message: str, runtime: AgentRuntime) -> str:
    """Entry point for one chat turn. Returns the user-facing answer."""
    graph = build_graph()
    final: GraphState = graph.invoke({
        "runtime": runtime, "user_message": user_message,
        "messages": [], "tool_to_call": None, "final_answer": None, "turn": 0,
    })
    return final.get("final_answer") or "(no answer)"
