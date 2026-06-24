"""AdHoc Missions pillar tools — STUBS. Shares the Justice Table (shifts pool).
Implement following the Logistics reference.
"""

from __future__ import annotations

from tools.base import ToolContext, ToolResult


def create_adhoc_mission(ctx: ToolContext, *, title: str, start_date: str,
                         days: int = 1) -> ToolResult[dict]:
    """SHIFT_MANAGER: create a sudden mission (0.5 x days burden, shifts pool)."""
    raise NotImplementedError

def assign_adhoc_mission(ctx: ToolContext, *, mission_id: int, personnel_id: int) -> ToolResult[dict]:
    """SHIFT_MANAGER: assign (validate HC-GD-0/5/6/7; balance via shifts pool)."""
    raise NotImplementedError

def suggest_adhoc_assignment(ctx: ToolContext, *, mission_id: int) -> ToolResult[dict]:
    """Preview the recommended person(s)."""
    raise NotImplementedError

def mark_adhoc_completed(ctx: ToolContext, *, mission_id: int) -> ToolResult[dict]:
    """Mark a mission COMPLETED."""
    raise NotImplementedError


TOOLS = (create_adhoc_mission, assign_adhoc_mission, suggest_adhoc_assignment, mark_adhoc_completed)
MUTATING = {create_adhoc_mission.__name__, assign_adhoc_mission.__name__, mark_adhoc_completed.__name__}
