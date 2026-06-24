"""Guard Duty + Support pillar tools — STUBS. Owns shifts, the Justice Table,
constraints (date-blocks), and the quarterly SUPPORT roster. Implement following
the Logistics reference; assignment validates HC-GD-0/3/5/6/7/9 and balances per
SC-GD-1/2/3/4/5.
"""

from __future__ import annotations

from typing import Literal

from tools.base import ToolContext, ToolOutput


def create_shifts(ctx: ToolContext, *, source: str) -> ToolOutput[dict]:
    """SHIFT_MANAGER: ingest the date list (chat text or CSV/Excel path), confirm, create."""
    raise NotImplementedError

def create_shift(ctx: ToolContext, *, type: Literal["WEEK_LONG", "SINGLE_DAY", "SUPPORT"],
                 start_date: str) -> ToolOutput[dict]:
    """SHIFT_MANAGER: create a single shift (the edge case)."""
    raise NotImplementedError

def assign_shift(ctx: ToolContext, *, shift_id: int, personnel_id: int) -> ToolOutput[dict]:
    """SHIFT_MANAGER: commit a manual assignment (validate HC-GD-0/5/6/7/9 + quotas)."""
    raise NotImplementedError

def auto_assign(ctx: ToolContext, *, shift_ids: list) -> ToolOutput[dict]:
    """SHIFT_MANAGER: assign a batch, balanced by the Justice Table."""
    raise NotImplementedError

def suggest_assignment(ctx: ToolContext, *, shift_id: int) -> ToolOutput[dict]:
    """Preview the recommended person(s) without committing."""
    raise NotImplementedError

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
