"""Cross-cutting infrastructure used by the agent layer.

Planned:
  llm.py            LLM client wrapper (model ids, structured output, retries)
  agent_runtime.py  per-run runtime: DB session, telemetry, tool/LLM calls
  telemetry.py      tool/LLM metrics schemas
  auth.py           login by personal_number; role/permission checks (DESIGN.md §9)
"""
