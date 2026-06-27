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
    """SHIFT_MANAGER: Create an ad-hoc mission."""
    try:
        import datetime
        dt_start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return ToolOutput.err("start_date must be in YYYY-MM-DD format.")

    dt_end = dt_start + datetime.timedelta(days=max(0, days - 1))

    mission = t.AdHocMission(
        title=title,
        start_date=dt_start,
        end_date=dt_end,
        days=days,
        status=AssignmentStatus.OPEN
    )
    ctx.session.add(mission)
    ctx.session.flush()

    audit = t.AuditLog(
        actor=ctx.actor_personal_number,
        action="CREATE_ADHOC_MISSION",
        entity_type="AdHocMission",
        entity_id=str(mission.id),
        after={"title": title, "start_date": start_date, "days": days}
    )
    ctx.session.add(audit)
    ctx.session.commit()

    return ToolOutput.of({
        "mission_id": mission.id,
        "title": mission.title,
        "status": mission.status.name,
    })

def assign_adhoc_mission(ctx: ToolContext, *, mission_id: int, personnel_id: int) -> ToolOutput[dict]:
    """SHIFT_MANAGER: assign (validate HC-GD-0/5/6/7; balance via shifts pool)."""
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
    """SHIFT_MANAGER: Mark a mission COMPLETED and apply burden points."""
    if (deny := require_role(ctx, "SHIFT_MANAGER")): return deny

    mission = ctx.session.get(t.AdHocMission, mission_id)
    if not mission:
        return ToolOutput.err(f"Mission {mission_id} not found.")

    if mission.status == AssignmentStatus.COMPLETED:
        return ToolOutput.err(f"Mission {mission_id} is already completed.")

    mission.status = AssignmentStatus.COMPLETED

    burden_added = 0.0
    if mission.assigned_to:
        person = ctx.session.get(t.Personnel, mission.assigned_to)
        # Keva does not accrue burden points for AdHoc
        if person and person.population == t.Population.SADIR:
            jt = ctx.session.query(t.JusticeTable).filter_by(personnel_id=person.id).first()
            if jt:
                burden_added = 0.5 * mission.days
                jt.shifts_burden_points += burden_added

    audit = t.AuditLog(
        actor=ctx.actor_personal_number,
        action="MARK_ADHOC_COMPLETED",
        entity_type="AdHocMission",
        entity_id=str(mission.id),
        after={"status": "COMPLETED", "burden_added": burden_added}
    )
    ctx.session.add(audit)
    ctx.session.commit()

    return ToolOutput.of({
        "mission_id": mission.id,
        "status": "COMPLETED",
        "burden_added_to_assignee": burden_added,
    })

def get_mission_list(ctx: ToolContext, *, status: str | None = None) -> ToolOutput[list]:
    """Read-only: list all ad-hoc missions, optionally filtering by status."""
    query = ctx.session.query(t.AdHocMission)
    if status:
        try:
            status_enum = AssignmentStatus[status]
            query = query.filter(t.AdHocMission.status == status_enum)
        except KeyError:
            return ToolOutput.err(f"Invalid status: {status}. Must be one of {', '.join(e.name for e in AssignmentStatus)}")
            
    missions = query.all()
    
    return ToolOutput.of([{
        "id": m.id,
        "title": m.title,
        "start_date": str(m.start_date),
        "end_date": str(m.end_date),
        "days": m.days,
        "status": m.status.name,
        "assigned_to": m.assigned_to,
    } for m in missions])

TOOLS = (create_adhoc_mission, assign_adhoc_mission, suggest_adhoc_assignment, mark_adhoc_completed, get_mission_list)
MUTATING = {create_adhoc_mission.__name__, assign_adhoc_mission.__name__, mark_adhoc_completed.__name__}
