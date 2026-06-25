"""Logistics domain tools. `sign_equipment` is the REFERENCE implementation —
copy its shape for every mutating tool in every domain.

Each tool: (1) role-gate, (2) look up entities (err + suggestions if missing),
(3) apply the change, (4) validate via rules + rollback on violation, (5) record
transfer/audit, (6) commit, (7) return a ToolOutput.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from data.services.logistics_repo import LogisticsRepo
from models.enums import ComputerStatus, MonitorStatus
from rules.constraints import check_hc_log_1, check_hc_log_2
from tools.base import ToolContext, ToolOutput, require_role


class SignEquipmentArgs(BaseModel):
    """Args for signing an equipment item out to a person."""

    catalog_number: str = Field(description="Catalog number of the equipment item to sign out.")
    personnel_id: int = Field(description="Id of the person who will receive (be signed for) the item.")


def sign_equipment(ctx: ToolContext, args: SignEquipmentArgs) -> ToolOutput[dict]:
    """Sign an equipment item out to a person (REFERENCE TOOL).

    Use when a LOGISTICS_OFFICER hands a usable item to a soldier. Validates
    HC-LOG-1/2 against the *pending* change and rolls back if violated; on success
    the item still needs Kitbag acceptance. Requires the LOGISTICS_OFFICER role.
    """
    if (deny := require_role(ctx, "LOGISTICS_OFFICER")):
        return deny

    repo = LogisticsRepo(ctx.session)

    item = repo.get_equipment(args.catalog_number)
    if item is None:  # did-you-mean (DESIGN §2)
        return ToolOutput.err(
            f"No equipment with catalog number {args.catalog_number}.",
            suggestions=repo.nearest_catalog_numbers(args.catalog_number),
        )
    person = repo.get_personnel(args.personnel_id)
    if person is None:
        return ToolOutput.err(f"No personnel with id {args.personnel_id}.")

    if item.status in (ComputerStatus.BROKEN.value, ComputerStatus.FORMATTING.value,
                       ComputerStatus.DECOMMISSIONED.value, MonitorStatus.BROKEN.value):
        return ToolOutput.err(f"{args.catalog_number} is {item.status} and cannot be signed out.")

    before = {"signed_to": item.signed_to, "status": item.status}

    repo.sign_to(item, args.personnel_id)                  # apply
    violations = repo.validate([check_hc_log_1, check_hc_log_2])  # validate pending state
    if violations:
        repo.rollback()
        return ToolOutput.err("Rejected by rules: " + "; ".join(violations))

    repo.transfer(catalog_number=args.catalog_number, from_personnel=before["signed_to"],
                  to_personnel=args.personnel_id, reason="signed out")
    repo.audit(actor=ctx.actor_personal_number, action="sign_equipment",
               entity_type="equipment_item", entity_id=args.catalog_number,
               before=before, after={"signed_to": args.personnel_id, "status": item.status})
    repo.commit()
    return ToolOutput.of({
        "catalog_number": args.catalog_number, "signed_to": args.personnel_id,
        "status": item.status, "handover_pending": True,
        "note": "Complete the hand-over in Kitbag; the recipient must accept it there.",
    })


# --- The rest of the Logistics tools — implement following the reference above ---
def return_equipment(ctx: ToolContext, *, catalog_number: str) -> ToolOutput[dict]:
    """Return a signed item to inventory (computer -> READY_TO_USE; clears signed_to)."""
    raise NotImplementedError

def resolve_equipment_ticket(ctx: ToolContext, *, ticket_id: int, catalog_number: str) -> ToolOutput[dict]:
    """Resolve an equipment ticket: re-validate, sign over, set handover_pending,
    link the ticket, close it, record transfer/audit. Did-you-mean on a bad id."""
    raise NotImplementedError

def set_equipment_status(ctx: ToolContext, *, catalog_number: str, status: str) -> ToolOutput[dict]:
    """Change an item's status — guard the §5 transition table (legal moves only)."""
    raise NotImplementedError

def decommission_item(ctx: ToolContext, *, catalog_number: str) -> ToolOutput[dict]:
    """Mark an item DECOMMISSIONED (removed from branch); clear custody; record removal."""
    raise NotImplementedError

def query_inventory(ctx: ToolContext, *, kind: str | None = None,
                    classification: str | None = None) -> ToolOutput[list]:
    """Read-only inventory query."""
    raise NotImplementedError


class GenerateLogisticsDashboardArgs(BaseModel):
    """Args for the generic logistics analytics dashboard tool."""

    metric: str = Field(
        description=(
            "Metric to visualize. Valid values: "
            "equipment_shortage, ticket_status_distribution, "
            "inventory_by_category, broken_by_type, tickets_over_time."
        )
    )
    chart_type: Literal["bar", "horizontal_bar", "line", "pie"] = Field(
        default="bar",
        description="Chart type. Use 'line' for time-series metrics, 'pie' for distributions.",
    )
    date_range: dict | None = Field(
        default=None,
        description='Optional date filter: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}. Supported by tickets_over_time.',
    )
    group_by: str | None = Field(
        default=None,
        description="Time grouping for tickets_over_time. One of: day, week, month. Default: week.",
    )
    top_n: int = Field(
        default=10,
        description="Maximum number of rows/bars to display. Default: 10.",
    )
    filters: dict = Field(
        default_factory=dict,
        description='Optional filters, e.g. {"ticket_type": "EQUIPMENT_REQUEST"}.',
    )


def generate_logistics_dashboard(ctx: ToolContext, args: GenerateLogisticsDashboardArgs) -> ToolOutput[dict]:
    """Generate a logistics analytics chart and return its URL plus the underlying data.

    Dispatches to the named metric provider (whitelist-only — no arbitrary DB queries),
    renders a PNG chart, and returns JSON with summary, chart_url, and rows. The caller
    should embed the chart as: ![Dashboard](chart_url).
    """
    import config.settings as _cfg
    from services.dashboard.metrics import METRIC_PROVIDERS
    from services.dashboard.renderer import render_chart

    provider = METRIC_PROVIDERS.get(args.metric)
    if provider is None:
        valid = ", ".join(sorted(METRIC_PROVIDERS))
        return ToolOutput.err(f"Unknown metric '{args.metric}'. Valid metrics: {valid}.")

    try:
        result = provider.fetch(
            ctx.session,
            date_range=args.date_range,
            group_by=args.group_by,
            top_n=args.top_n,
            filters=args.filters,
        )
    except Exception as exc:
        return ToolOutput.err(f"Failed to fetch '{args.metric}' data: {exc}")

    if not result.rows:
        return ToolOutput.of({"summary": result.summary, "chart_url": None, "rows": []})

    try:
        chart_url = render_chart(result, args.chart_type, _cfg.CHARTS_DIR)
    except Exception as exc:
        return ToolOutput.err(f"Chart rendering failed: {exc}")

    return ToolOutput.of({
        "summary": result.summary,
        "chart_url": chart_url,
        "rows": result.rows,
    })


TOOLS = (sign_equipment, return_equipment, resolve_equipment_ticket,
         set_equipment_status, decommission_item, query_inventory,
         generate_logistics_dashboard)
MUTATING = {sign_equipment.__name__, return_equipment.__name__, resolve_equipment_ticket.__name__,
            set_equipment_status.__name__, decommission_item.__name__}
