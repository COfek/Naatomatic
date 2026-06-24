"""Agent node graph (LangGraph) — see DESIGN.md §2 Node Architecture.

Planned:
  orchestrator.py  builds & runs the graph
  router.py        Router node (classify intent -> domain + role scope)
  nodes/           Worker, Validator, Presenter
  pillars/         per-domain worker config (prompts, tool subsets)
"""
