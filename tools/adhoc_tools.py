"""AdHoc Missions domain tools — STUBS. Shares the Justice Table (shifts pool).
Implement following the Logistics reference.
"""

from __future__ import annotations

from tools.base import ToolContext, ToolOutput, require_role
from models import tables as t
from models.enums import AssignmentStatus
from services.scheduling import SchedulingService


def create_adhoc_mission(ctx: ToolContext, *, title: str, start_date: str,
                         days: int = 1) -> ToolOutput[dict]:
    """SHIFT_MANAGER: create a sudden mission (0.5 x days burden, shifts pool)."""
    raise NotImplementedError

def assign_adhoc_mission(ctx: ToolContext, *, mission_id: int, personnel_id: int) -> ToolOutput[dict]:
    """SHIFT_MANAGER: assign (validate HC-GD-0/5/6/7; balance via shifts pool)."""
    if (deny := require_role(ctx, "SHIFT_MANAGER")): return deny

    mission = ctx.session.get(t.AdHocMission, mission_id)
    if not mission:
        return ToolOutput.err(f"Mission {mission_id} not found.")

    if mission.status not in (AssignmentStatus.OPEN, AssignmentStatus.ASSIGNED):
        return ToolOutput.err(f"Mission {mission_id} is not open for assignment.")

    svc = SchedulingService(ctx.session)
    candidates = svc._get_eligible_candidates(
        start_date=mission.start_date,
        end_date=mission.end_date,
        duty_type="ADHOC",
        eligible_population=mission.eligible_population,
        required_rank=mission.required_rank,
    )

    if personnel_id not in candidates:
        return ToolOutput.err(f"Personnel {personnel_id} does not meet hard constraints for this mission (overlaps, date blocks, or eligibility).")

    mission.assigned_to = personnel_id
    mission.status = AssignmentStatus.ASSIGNED
    
    audit = t.AuditLog(
        actor=ctx.actor_personal_number,
        action="ASSIGN_ADHOC_MISSION",
        entity_type="AdHocMission",
        entity_id=str(mission.id),
        after={"assigned_to": personnel_id, "status": mission.status.value}
    )
    ctx.session.add(audit)
    ctx.session.commit()

    return ToolOutput.of({
        "mission_id": mission.id,
        "assigned_to": personnel_id,
        "status": mission.status.name,
    })

def suggest_adhoc_assignment(ctx: ToolContext, *, mission_id: int) -> ToolOutput[dict]:
    """Preview the recommended person(s)."""
    mission = ctx.session.get(t.AdHocMission, mission_id)
    if not mission:
        return ToolOutput.err(f"Mission {mission_id} not found.")

    svc = SchedulingService(ctx.session)
    rec = svc.recommend_assignment(
        start_date=mission.start_date,
        end_date=mission.end_date,
        duty_type="ADHOC",
        eligible_population=mission.eligible_population,
        required_rank=mission.required_rank,
    )

    if rec["primary_id"] is None:
        return ToolOutput.err("No eligible candidates found for this mission.")

    return ToolOutput.of(rec)

def mark_adhoc_completed(ctx: ToolContext, *, mission_id: int) -> ToolOutput[dict]:
    """Mark a mission COMPLETED."""
    raise NotImplementedError


TOOLS = (create_adhoc_mission, assign_adhoc_mission, suggest_adhoc_assignment, mark_adhoc_completed)
MUTATING = {create_adhoc_mission.__name__, assign_adhoc_mission.__name__, mark_adhoc_completed.__name__}
