"""Logistics domain config — the Worker's system prompt + the tool subset the
Router exposes for this domain. (Pattern for all domain configs.)"""

from __future__ import annotations

from agents.domains.logistics import tools as logistics_tools

PROMPT = (
    "You are the Logistics assistant for the CombatAI branch. Help with equipment "
    "(computers, monitors): requests, sign-out/return, status, and ticket resolution. "
    "Never invent identifiers — if a detail is missing, ask; if an id isn't found, "
    "offer the closest matches. Only managers (LOGISTICS_OFFICER) may resolve/sign."
)
TOOL_NAMES = [fn.__name__ for fn in logistics_tools.TOOLS]
