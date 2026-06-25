"""AdHoc domain config — STUB prompt + tool subset."""

from __future__ import annotations

from tools import adhoc_tools

PROMPT = (
    "You are the AdHoc Missions assistant. Help create and assign sudden missions "
    "(ceremonies, memorials, volunteering). Only SHIFT_MANAGER may create/assign."
)
TOOL_NAMES = [fn.__name__ for fn in adhoc_tools.TOOLS]
