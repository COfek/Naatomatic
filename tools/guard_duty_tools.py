"""Guard Duty + Support domain tools — STUBS. Owns shifts, the Justice Table,
constraints (date-blocks), and the quarterly SUPPORT roster. Implement following
the Logistics reference; assignment validates HC-GD-0/3/5/6/7/9 and balances per
SC-GD-1/2/3/4/5.
"""

from __future__ import annotations

from typing import Literal

from tools.base import ToolContext, ToolOutput, require_role
from models import tables as t
from models.enums import AssignmentStatus
from services.scheduling import SchedulingService


def create_shifts(ctx: ToolContext, *, source: str) -> ToolOutput[dict]:
    """Bulk create shifts from text lines formatted as 'TYPE YYYY-MM-DD'."""
    created = []
    lines = source.strip().split("\n")
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 2:
            stype = parts[0]
            sdate = parts[1]
            res = create_shift(ctx, type=stype, start_date=sdate)
            if res.ok:
                created.append(res.value)
    return ToolOutput.of({"created_count": len(created), "shifts": created})

def create_shift(ctx: ToolContext, *, type: str, start_date: str) -> ToolOutput[dict]:
    """Create a single shift."""
    try:
        import datetime
        dt_start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return ToolOutput.err("start_date must be in YYYY-MM-DD format.")
        
    try:
        from models.enums import ShiftType
        shift_type = ShiftType[type]
    except KeyError:
        return ToolOutput.err(f"Invalid shift type: {type}")
        
    if shift_type == ShiftType.WEEK_LONG:
        dt_end = dt_start + datetime.timedelta(days=6)
    elif shift_type == ShiftType.SINGLE_DAY:
        dt_end = dt_start
    elif shift_type == ShiftType.SUPPORT:
        # Friday support covers Fri+Sat
        dt_end = dt_start + datetime.timedelta(days=1) if dt_start.weekday() == 4 else dt_start
    else:
        dt_end = dt_start
        
    shift = t.Shift(
        type=shift_type,
        start_date=dt_start,
        end_date=dt_end,
        status=AssignmentStatus.OPEN
    )
    ctx.session.add(shift)
    ctx.session.commit()
    
    return ToolOutput.of({
        "shift_id": shift.id, 
        "type": type, 
        "start_date": str(dt_start), 
        "end_date": str(dt_end)
    })

def assign_shift(ctx: ToolContext, *, shift_id: int, personnel_id: int) -> ToolOutput[dict]:
    """commit a manual assignment (validate HC-GD-0/5/6/7/9 + quotas)."""

    shift = ctx.session.get(t.Shift, shift_id)
    if not shift:
        return ToolOutput.err(f"Shift {shift_id} not found.")

    if shift.status not in (AssignmentStatus.OPEN, AssignmentStatus.ASSIGNED):
        return ToolOutput.err(f"Shift {shift_id} is not open for assignment.")

    svc = SchedulingService(ctx.session)
    candidates = svc._get_eligible_candidates(
        start_date=shift.start_date,
        end_date=shift.end_date,
        duty_type=shift.type,
        eligible_population=shift.eligible_population,
        required_rank=shift.required_rank,
    )

    if personnel_id not in candidates:
        return ToolOutput.err(f"Personnel {personnel_id} does not meet hard constraints for this shift.")

    shift.assigned_to = personnel_id
    shift.status = AssignmentStatus.ASSIGNED
    
    audit = t.AuditLog(
        actor=ctx.actor_personal_number,
        action="ASSIGN_SHIFT",
        entity_type="Shift",
        entity_id=str(shift.id),
        after={"assigned_to": personnel_id, "status": shift.status.value}
    )
    ctx.session.add(audit)
    ctx.session.commit()

    return ToolOutput.of({
        "shift_id": shift.id,
        "assigned_to": personnel_id,
        "status": shift.status.name,
    })

def auto_assign(ctx: ToolContext, *, shift_ids: list) -> ToolOutput[dict]:
    """assign a batch, balanced by the Justice Table."""

    svc = SchedulingService(ctx.session)
    results = []

    for sid in shift_ids:
        try:
            sid_int = int(sid)
        except ValueError:
            continue
        shift = ctx.session.get(t.Shift, sid_int)
        if not shift or shift.status not in (AssignmentStatus.OPEN, AssignmentStatus.ASSIGNED):
            continue

        rec = svc.recommend_assignment(
            start_date=shift.start_date,
            end_date=shift.end_date,
            duty_type=shift.type,
            eligible_population=shift.eligible_population,
            required_rank=shift.required_rank,
        )

        if rec["primary_id"] is not None:
            shift.assigned_to = rec["primary_id"]
            shift.reserve_id = rec["reserve_id"]
            shift.status = AssignmentStatus.ASSIGNED
            
            audit = t.AuditLog(
                actor=ctx.actor_personal_number,
                action="AUTO_ASSIGN_SHIFT",
                entity_type="Shift",
                entity_id=str(shift.id),
                after={"assigned_to": shift.assigned_to, "reserve_id": shift.reserve_id}
            )
            ctx.session.add(audit)
            
            results.append({
                "shift_id": shift.id,
                "assigned_to": shift.assigned_to,
                "reserve_id": shift.reserve_id,
                "warnings": rec["warnings"]
            })
            
    ctx.session.commit()
    return ToolOutput.of({"assigned_count": len(results), "details": results})

def suggest_assignment(ctx: ToolContext, *, shift_id: int) -> ToolOutput[dict]:
    """Preview the recommended person(s) without committing."""
    shift = ctx.session.get(t.Shift, shift_id)
    if not shift:
        return ToolOutput.err(f"Shift {shift_id} not found.")

    svc = SchedulingService(ctx.session)
    rec = svc.recommend_assignment(
        start_date=shift.start_date,
        end_date=shift.end_date,
        duty_type=shift.type,
        eligible_population=shift.eligible_population,
        required_rank=shift.required_rank,
    )

    if rec["primary_id"] is None:
        return ToolOutput.err("No eligible candidates found for this shift.")

    return ToolOutput.of(rec)

def swap_shifts(ctx: ToolContext, *, shift_a: int, shift_b: int) -> ToolOutput[dict]:
    """Swap two assignees (same population + same type; re-validate)."""
    sa = ctx.session.get(t.Shift, shift_a)
    sb = ctx.session.get(t.Shift, shift_b)
    
    if not sa or not sb:
        return ToolOutput.err("One or both shifts not found.")
        
    if sa.type != sb.type:
        return ToolOutput.err("Shifts must be of the same type to swap.")
        
    if sa.eligible_population != sb.eligible_population:
        return ToolOutput.err("Shifts must target the same population to swap.")
        
    assignee_a = sa.assigned_to
    assignee_b = sb.assigned_to
    
    # Temporarily detach so _get_eligible_candidates doesn't count them as overlapping with themselves
    sa.assigned_to = None
    sb.assigned_to = None
    ctx.session.flush()
    
    svc = SchedulingService(ctx.session)
    
    # Check if assignee_b can take shift_a
    if assignee_b:
        cands_a = svc._get_eligible_candidates(start_date=sa.start_date, end_date=sa.end_date, duty_type=sa.type, eligible_population=sa.eligible_population, required_rank=sa.required_rank)
        if assignee_b not in cands_a:
            ctx.session.rollback()
            return ToolOutput.err(f"Assignee of shift {shift_b} is not eligible for shift {shift_a}.")
            
    # Check if assignee_a can take shift_b
    if assignee_a:
        cands_b = svc._get_eligible_candidates(start_date=sb.start_date, end_date=sb.end_date, duty_type=sb.type, eligible_population=sb.eligible_population, required_rank=sb.required_rank)
        if assignee_a not in cands_b:
            ctx.session.rollback()
            return ToolOutput.err(f"Assignee of shift {shift_a} is not eligible for shift {shift_b}.")
            
    sa.assigned_to = assignee_b
    sb.assigned_to = assignee_a
    
    sa.status = AssignmentStatus.ASSIGNED if assignee_b else AssignmentStatus.OPEN
    sb.status = AssignmentStatus.ASSIGNED if assignee_a else AssignmentStatus.OPEN
    
    ctx.session.commit()
    return ToolOutput.of({
        "swapped": True, 
        f"shift_{sa.id}_assigned_to": sa.assigned_to, 
        f"shift_{sb.id}_assigned_to": sb.assigned_to
    })

def add_date_block(ctx: ToolContext, *, start_date: str, end_date: str, reason: str,
                   level: str) -> ToolOutput[dict]:
    """Create a pending unavailability constraint for the current user."""
    try:
        import datetime
        dt_start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        dt_end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return ToolOutput.err("Dates must be in YYYY-MM-DD format.")
        
    try:
        from models.enums import ConstraintLevel, DateBlockStatus
        constraint_level = ConstraintLevel[level]
    except KeyError:
        return ToolOutput.err(f"Invalid level. Must be one of CRITICAL, HIGH, MEDIUM, LOW.")
        
    person = ctx.session.query(t.Personnel).filter_by(personal_number=ctx.actor_personal_number).first()
    if not person:
        return ToolOutput.err("Personnel record not found for actor.")
        
    overlapping_shift = ctx.session.query(t.Shift).filter(
        t.Shift.assigned_to == person.id,
        t.Shift.end_date >= dt_start,
        t.Shift.start_date <= dt_end
    ).first()
    
    if overlapping_shift:
        return ToolOutput.err(f"Cannot add block: you are already assigned to shift {overlapping_shift.id}.")
        
    block = t.PersonnelDateBlock(
        personnel_id=person.id,
        start_date=dt_start,
        end_date=dt_end,
        reason=reason,
        status=DateBlockStatus.PENDING,
        level=constraint_level
    )
    ctx.session.add(block)
    ctx.session.commit()
    
    return ToolOutput.of({"block_id": block.id, "status": "PENDING"})

def review_date_blocks(ctx: ToolContext) -> ToolOutput[list]:
    """List pending constraints to approve/reject."""
    from models.enums import DateBlockStatus
    blocks = ctx.session.query(t.PersonnelDateBlock).filter_by(status=DateBlockStatus.PENDING).all()
    out = []
    for b in blocks:
        person = ctx.session.get(t.Personnel, b.personnel_id)
        out.append({
            "block_id": b.id,
            "personnel_id": b.personnel_id,
            "name": person.full_name if person else "Unknown",
            "start_date": str(b.start_date),
            "end_date": str(b.end_date),
            "reason": b.reason,
            "level": b.level.name
        })
    return ToolOutput.of(out)

def approve_date_block(ctx: ToolContext, *, block_id: int) -> ToolOutput[dict]:
    """Approve a pending constraint (re-check conflicts — GD-7)."""
    from models.enums import DateBlockStatus
    block = ctx.session.get(t.PersonnelDateBlock, block_id)
    if not block:
        return ToolOutput.err(f"Block {block_id} not found.")
        
    if block.status == DateBlockStatus.APPROVED:
        return ToolOutput.err(f"Block {block_id} is already approved.")
        
    overlapping_shift = ctx.session.query(t.Shift).filter(
        t.Shift.assigned_to == block.personnel_id,
        t.Shift.end_date >= block.start_date,
        t.Shift.start_date <= block.end_date
    ).first()
    
    if overlapping_shift:
        return ToolOutput.err(f"Cannot approve: overlapping shift {overlapping_shift.id} was assigned.")
        
    block.status = DateBlockStatus.APPROVED
    ctx.session.commit()
    
    return ToolOutput.of({"block_id": block.id, "status": "APPROVED"})

def list_my_shifts(ctx: ToolContext, *, include_past: bool = True) -> ToolOutput[list]:
    """A soldier's own assignments, upcoming and past (self only)."""
    person = ctx.session.query(t.Personnel).filter_by(personal_number=ctx.actor_personal_number).first()
    if not person:
        return ToolOutput.err("Personnel record not found for actor.")
        
    query = ctx.session.query(t.Shift).filter(t.Shift.assigned_to == person.id)
    if not include_past:
        import datetime
        query = query.filter(t.Shift.start_date >= datetime.date.today())
        
    shifts = query.order_by(t.Shift.start_date).all()
    
    out = []
    for s in shifts:
        out.append({
            "shift_id": s.id,
            "type": s.type.name,
            "start_date": str(s.start_date),
            "end_date": str(s.end_date),
            "status": s.status.name
        })
    return ToolOutput.of(out)

def get_justice_table(ctx: ToolContext, *, population: str | None = None) -> ToolOutput[list]:
    """Read-only fairness standings."""
    query = ctx.session.query(t.JusticeTable, t.Personnel).join(t.Personnel, t.JusticeTable.personnel_id == t.Personnel.id)
    if population:
        try:
            from models.enums import Population
            pop_enum = Population[population]
            query = query.filter(t.Personnel.population == pop_enum)
        except KeyError:
            return ToolOutput.err(f"Invalid population: {population}")
            
    results = query.all()
    
    out = []
    for jt, person in results:
        out.append({
            "personnel_id": person.id,
            "name": person.full_name,
            "population": person.population.name,
            "shifts_burden_points": jt.shifts_burden_points,
            "support_burden_points": jt.support_burden_points,
            "week_long_count": jt.week_long_count,
            "single_day_count": jt.single_day_count
        })
    return ToolOutput.of(out)

def generate_support_roster(ctx: ToolContext, *, quarter: str) -> ToolOutput[dict]:
    """Tile a quarter into daily+weekend SUPPORT slots, assign ahead."""
    import datetime
    try:
        parts = quarter.split("-")
        if len(parts) != 2:
            raise ValueError
            
        if parts[0].startswith("Q"):
            q_num = int(parts[0][1])
            year = int(parts[1])
        elif parts[1].startswith("Q"):
            year = int(parts[0])
            q_num = int(parts[1][1])
        else:
            raise ValueError
            
        start_month = (q_num - 1) * 3 + 1
        start_date = datetime.date(year, start_month, 1)
        if start_month == 10:
            end_date = datetime.date(year, 12, 31)
        else:
            end_date = datetime.date(year, start_month + 3, 1) - datetime.timedelta(days=1)
    except ValueError:
        return ToolOutput.err("Invalid quarter format. Use 'Q3-2026' or '2026-Q3'.")
        
    current_date = start_date
    shifts_created = 0
    
    while current_date <= end_date:
        res = create_shift(ctx, type="SUPPORT", start_date=str(current_date))
        if res.ok:
            shifts_created += 1
            
        if current_date.weekday() == 4: # Friday
            current_date += datetime.timedelta(days=2) # skip Saturday since Friday covers Fri+Sat
        else:
            current_date += datetime.timedelta(days=1)
            
    return ToolOutput.of({
        "quarter": quarter,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "shifts_created": shifts_created
    })

def check_support_coverage(ctx: ToolContext, *, start_date: str, end_date: str) -> ToolOutput[dict]:
    """Read-only: report gaps/overlaps in the SUPPORT roster."""
    import datetime
    from models.enums import ShiftType
    try:
        dt_start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        dt_end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return ToolOutput.err("Dates must be in YYYY-MM-DD format.")
        
    shifts = ctx.session.query(t.Shift).filter(
        t.Shift.type == ShiftType.SUPPORT,
        t.Shift.start_date >= dt_start,
        t.Shift.end_date <= dt_end + datetime.timedelta(days=1)
    ).all()
    
    coverage = {}
    current = dt_start
    while current <= dt_end:
        coverage[current] = 0
        current += datetime.timedelta(days=1)
        
    for s in shifts:
        c_date = s.start_date
        while c_date <= s.end_date:
            if c_date in coverage:
                coverage[c_date] += 1
            c_date += datetime.timedelta(days=1)
            
    gaps = [str(d) for d, count in coverage.items() if count == 0]
    overlaps = {str(d): count for d, count in coverage.items() if count > 1}
    
    return ToolOutput.of({
        "start_date": start_date,
        "end_date": end_date,
        "gaps": gaps,
        "overlaps": overlaps,
        "total_days_checked": len(coverage)
    })


def list_all_shifts(ctx: ToolContext, *, include_past: bool = True, status: str | None = None) -> ToolOutput[list]:
    """Read-only: list all shifts, optionally filtering by status and past dates."""
    query = ctx.session.query(t.Shift)
    
    if not include_past:
        import datetime
        query = query.filter(t.Shift.start_date >= datetime.date.today())
        
    if status:
        try:
            from models.enums import AssignmentStatus
            status_enum = AssignmentStatus[status]
            query = query.filter(t.Shift.status == status_enum)
        except KeyError:
            return ToolOutput.err(f"Invalid status: {status}")
            
    shifts = query.order_by(t.Shift.start_date).all()
    
    out = []
    for s in shifts:
        out.append({
            "shift_id": s.id,
            "type": s.type.name,
            "start_date": str(s.start_date),
            "end_date": str(s.end_date),
            "status": s.status.name,
            "assigned_to": s.assigned_to
        })
    return ToolOutput.of(out)


TOOLS = (create_shifts, create_shift, assign_shift, auto_assign, suggest_assignment,
         swap_shifts, add_date_block, review_date_blocks, approve_date_block,
         list_my_shifts, list_all_shifts, get_justice_table, generate_support_roster, check_support_coverage)
MUTATING = {create_shifts.__name__, create_shift.__name__, assign_shift.__name__,
            auto_assign.__name__, swap_shifts.__name__, add_date_block.__name__,
            approve_date_block.__name__, generate_support_roster.__name__}
