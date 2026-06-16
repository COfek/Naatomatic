"""Agent node graph (LangGraph) — see DESIGN.md §2 Node Architecture.

Planned:
  orchestrator.py  builds & runs the graph
  router.py        Router node (classify intent -> pillar + role scope)
  nodes/           Worker, Validator, Presenter
  pillars/         per-pillar worker config (prompts, tool subsets)
"""
