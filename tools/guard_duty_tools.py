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
    """SHIFT_MANAGER: ingest the date list (chat text or CSV/Excel path), confirm, create."""
    raise NotImplementedError

def create_shift(ctx: ToolContext, *, type: Literal["WEEK_LONG", "SINGLE_DAY", "SUPPORT"],
                 start_date: str) -> ToolOutput[dict]:
    """SHIFT_MANAGER: create a single shift (the edge case)."""
    raise NotImplementedError

def assign_shift(ctx: ToolContext, *, shift_id: int, personnel_id: int) -> ToolOutput[dict]:
    """SHIFT_MANAGER: commit a manual assignment (validate HC-GD-0/5/6/7/9 + quotas)."""
    if (deny := require_role(ctx, "SHIFT_MANAGER")): return deny

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
    """SHIFT_MANAGER: assign a batch, balanced by the Justice Table."""
    if (deny := require_role(ctx, "SHIFT_MANAGER")): return deny

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
    """SHIFT_MANAGER: swap two assignees (same population + same type; re-validate)."""
    raise NotImplementedError

def add_date_block(ctx: ToolContext, *, start_date: str, end_date: str, reason: str,
                   level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]) -> ToolOutput[dict]:
    """A soldier submits a constraint (-> PENDING; reject if it overlaps own assignment)."""
    raise NotImplementedError

def review_date_blocks(ctx: ToolContext) -> ToolOutput[list]:
    """SHIFT_MANAGER: list pending constraints to approve/reject."""
    raise NotImplementedError

def approve_date_block(ctx: ToolContext, *, block_id: int) -> ToolOutput[dict]:
    """SHIFT_MANAGER: approve a pending constraint (re-check conflicts — GD-7)."""
    raise NotImplementedError

def list_my_shifts(ctx: ToolContext, *, include_past: bool = True) -> ToolOutput[list]:
    """A soldier's own assignments, upcoming and past (self only)."""
    raise NotImplementedError

def get_justice_table(ctx: ToolContext, *, population: str | None = None) -> ToolOutput[list]:
    """Read-only fairness standings."""
    raise NotImplementedError

def generate_support_roster(ctx: ToolContext, *, quarter: str) -> ToolOutput[dict]:
    """SHIFT_MANAGER / maintenance: tile a quarter into daily+weekend SUPPORT slots, assign ahead."""
    raise NotImplementedError

def check_support_coverage(ctx: ToolContext, *, start_date: str, end_date: str) -> ToolOutput[dict]:
    """Read-only: report gaps/overlaps in the SUPPORT roster."""
    raise NotImplementedError


TOOLS = (create_shifts, create_shift, assign_shift, auto_assign, suggest_assignment,
         swap_shifts, add_date_block, review_date_blocks, approve_date_block,
         list_my_shifts, get_justice_table, generate_support_roster, check_support_coverage)
MUTATING = {create_shifts.__name__, create_shift.__name__, assign_shift.__name__,
            auto_assign.__name__, swap_shifts.__name__, add_date_block.__name__,
            approve_date_block.__name__, generate_support_roster.__name__}
