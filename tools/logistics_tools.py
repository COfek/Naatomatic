"""Logistics pillar tools. `sign_equipment` is the REFERENCE implementation —
copy its shape for every mutating tool in every pillar.

Each tool: (1) role-gate, (2) look up entities (err + suggestions if missing),
(3) apply the change, (4) validate via rules + rollback on violation, (5) record
transfer/audit, (6) commit, (7) return a ToolResult.
"""

from __future__ import annotations

from typing import Any, Literal

from data.services.logistics_repo import LogisticsRepo
from models.enums import ComputerStatus, MonitorStatus
from rules.constraints import check_hc_log_1, check_hc_log_2
from tools.base import ToolContext, ToolResult, require_role


def sign_equipment(ctx: ToolContext, *, catalog_number: str, personnel_id: int) -> ToolResult[dict]:
    """Sign an equipment item out to a person (REFERENCE TOOL).

    Validates HC-LOG-1/2 against the *pending* change and rolls back if violated.
    Requires the LOGISTICS_OFFICER role.
    """
    if (deny := require_role(ctx, "LOGISTICS_OFFICER")):
        return deny

    repo = LogisticsRepo(ctx.session)

    item = repo.get_equipment(catalog_number)
    if item is None:  # did-you-mean (DESIGN §2)
        return ToolResult.err(
            f"No equipment with catalog number {catalog_number}.",
            suggestions=repo.nearest_catalog_numbers(catalog_number),
        )
    person = repo.get_personnel(personnel_id)
    if person is None:
        return ToolResult.err(f"No personnel with id {personnel_id}.")

    if item.status in (ComputerStatus.BROKEN.value, ComputerStatus.FORMATTING.value,
                       ComputerStatus.DECOMMISSIONED.value, MonitorStatus.BROKEN.value):
        return ToolResult.err(f"{catalog_number} is {item.status} and cannot be signed out.")

    before = {"signed_to": item.signed_to, "status": item.status}

    repo.sign_to(item, personnel_id)                       # apply
    violations = repo.validate([check_hc_log_1, check_hc_log_2])  # validate pending state
    if violations:
        repo.rollback()
        return ToolResult.err("Rejected by rules: " + "; ".join(violations))

    repo.transfer(catalog_number=catalog_number, from_personnel=before["signed_to"],
                  to_personnel=personnel_id, reason="signed out")
    repo.audit(actor=ctx.actor_personal_number, action="sign_equipment",
               entity_type="equipment_item", entity_id=catalog_number,
               before=before, after={"signed_to": personnel_id, "status": item.status})
    repo.commit()
    return ToolResult.of({
        "catalog_number": catalog_number, "signed_to": personnel_id,
        "status": item.status, "handover_pending": True,
        "note": "Complete the hand-over in Kitbag; the recipient must accept it there.",
    })


# --- The rest of the Logistics tools — implement following the reference above ---
def return_equipment(ctx: ToolContext, *, catalog_number: str) -> ToolResult[dict]:
    """Return a signed item to inventory (computer -> READY_TO_USE; clears signed_to)."""
    raise NotImplementedError

def create_equipment_request(ctx: ToolContext, *, kind: Literal["MONITOR", "COMPUTER"],
                             classification: str | None = None) -> ToolResult[dict]:
    """Open an EQUIPMENT_REQUEST ticket (gate via projected HC-LOG-1/2 + stock check)."""
    raise NotImplementedError

def resolve_equipment_ticket(ctx: ToolContext, *, ticket_id: int, catalog_number: str) -> ToolResult[dict]:
    """Resolve an equipment ticket: re-validate, sign over, set handover_pending,
    link the ticket, close it, record transfer/audit. Did-you-mean on a bad id."""
    raise NotImplementedError

def set_equipment_status(ctx: ToolContext, *, catalog_number: str, status: str) -> ToolResult[dict]:
    """Change an item's status — guard the §5 transition table (legal moves only)."""
    raise NotImplementedError

def decommission_item(ctx: ToolContext, *, catalog_number: str) -> ToolResult[dict]:
    """Mark an item DECOMMISSIONED (removed from branch); clear custody; record removal."""
    raise NotImplementedError

def query_inventory(ctx: ToolContext, *, kind: str | None = None,
                    classification: str | None = None) -> ToolResult[list]:
    """Read-only inventory query."""
    raise NotImplementedError


TOOLS = (sign_equipment, return_equipment, create_equipment_request, resolve_equipment_ticket,
         set_equipment_status, decommission_item, query_inventory)
MUTATING = {sign_equipment.__name__, return_equipment.__name__, resolve_equipment_ticket.__name__,
            set_equipment_status.__name__, decommission_item.__name__}
