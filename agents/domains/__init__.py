"""Per-domain agent configuration (system prompts + tool subsets).

Each domain is a sub-package containing:
  config.py  — the Worker's system prompt + tool names
  tools.py   — the domain's tool functions (validate → act → return ToolOutput)
"""
