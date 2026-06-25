"""Equipment shortage metric — computes depot availability vs demand per category."""

from __future__ import annotations

from sqlalchemy import select

from config.settings import COMPUTER_DEMAND_PER_PERSON, MONITOR_DEMAND_PER_PERSON
from models import tables as t
from models.enums import (
    ComputerStatus,
    DEPOT_PERSONAL_NUMBER,
    EquipmentKind,
    MonitorStatus,
    TicketStatus,
    TicketType,
)
from services.dashboard.base import MetricProvider, MetricResult


class EquipmentShortageMetric(MetricProvider):
    """Shortage = demand - depot-available, per equipment category.

    Demand source priority:
      1. Open equipment-request tickets (explicit, per-category count).
      2. Config-driven per-person ratio (MONITOR_DEMAND_PER_PERSON /
         COMPUTER_DEMAND_PER_PERSON) — a policy estimate, not a hardcoded guess.
    """

    def fetch(
        self,
        session,
        *,
        date_range=None,
        group_by=None,
        top_n=None,
        filters=None,
    ) -> MetricResult:
        active_personnel = session.scalars(
            select(t.Personnel).where(t.Personnel.active == True)  # noqa: E712
        ).all()
        active_non_depot = [p for p in active_personnel if p.personal_number != DEPOT_PERSONAL_NUMBER]
        num_personnel = len(active_non_depot)

        if num_personnel == 0:
            return MetricResult(
                title="Equipment Shortage Dashboard",
                summary="No active personnel found.",
                rows=[],
            )

        depot = session.scalars(
            select(t.Personnel).where(t.Personnel.personal_number == DEPOT_PERSONAL_NUMBER)
        ).first()
        depot_id = depot.id if depot else None

        all_items = session.scalars(select(t.EquipmentItem)).all()
        if not all_items:
            return MetricResult(
                title="Equipment Shortage Dashboard",
                summary="No equipment items found.",
                rows=[],
            )

        # Bucket items into available-at-depot / in-use / broken (skip decommissioned)
        available: dict[str, int] = {}
        in_use: dict[str, int] = {}
        broken: dict[str, int] = {}

        for item in all_items:
            cat = _category(item)
            if item.status in (MonitorStatus.DECOMMISSIONED.value, ComputerStatus.DECOMMISSIONED.value):
                continue
            if item.status in (
                ComputerStatus.BROKEN.value,
                MonitorStatus.BROKEN.value,
                ComputerStatus.FORMATTING.value,
            ):
                broken[cat] = broken.get(cat, 0) + 1
            elif item.signed_to in (depot_id, None):
                available[cat] = available.get(cat, 0) + 1
            else:
                in_use[cat] = in_use.get(cat, 0) + 1

        # Explicit demand from open equipment-request tickets
        open_tickets = session.scalars(
            select(t.Ticket).where(
                t.Ticket.type == TicketType.EQUIPMENT_REQUEST.value,
                t.Ticket.status == TicketStatus.OPEN.value,
            )
        ).all()

        ticket_demand: dict[str, int] = {}
        for ticket in open_tickets:
            payload = ticket.payload or {}
            kind = payload.get("kind")
            classification = payload.get("classification")
            if kind == EquipmentKind.COMPUTER.value:
                cat = f"COMPUTER-{classification}" if classification else "COMPUTER-UNCLASSIFIED"
            elif kind == EquipmentKind.MONITOR.value:
                cat = "MONITOR"
            else:
                continue
            ticket_demand[cat] = ticket_demand.get(cat, 0) + 1

        all_categories = set(available) | set(in_use) | set(broken) | set(ticket_demand)
        if not all_categories:
            return MetricResult(
                title="Equipment Shortage Dashboard",
                summary="No equipment categories found.",
                rows=[],
            )

        rows: list[dict] = []
        for cat in sorted(all_categories):
            avail = available.get(cat, 0)
            if ticket_demand.get(cat, 0) > 0:
                # Explicit open-ticket count is the most accurate demand signal.
                required = ticket_demand[cat]
            elif cat == "MONITOR":
                required = max(1, round(num_personnel * MONITOR_DEMAND_PER_PERSON))
            else:
                required = max(1, round(num_personnel * COMPUTER_DEMAND_PER_PERSON))

            rows.append({
                "label":    cat,
                "available": avail,
                "in_use":   in_use.get(cat, 0),
                "broken":   broken.get(cat, 0),
                "required": required,
                "shortage": required - avail,
            })

        rows.sort(key=lambda r: -r["shortage"])
        if top_n:
            rows = rows[:top_n]

        critical = [(r["label"], r["shortage"]) for r in rows if r["shortage"] > 0]
        if critical:
            top3 = ", ".join(f"{cat} (need {s} more)" for cat, s in critical[:3])
            summary = (
                f"{len(critical)} equipment category(ies) below required stock. "
                f"Most critical: {top3}. Active personnel: {num_personnel}."
            )
        else:
            summary = (
                f"No shortages detected across {len(rows)} equipment category(ies). "
                f"All depot stock meets current demand. Active personnel: {num_personnel}."
            )

        return MetricResult(
            title="Equipment Shortage Dashboard",
            summary=summary,
            rows=rows,
            y_label="Item Count",
            series=["available", "required"],
            secondary_series=["shortage"],
            primary_title="Current Stock vs Required",
            secondary_title="Shortage (+) / Surplus (−) per Category",
        )


def _category(item: t.EquipmentItem) -> str:
    if item.kind == EquipmentKind.MONITOR:
        return "MONITOR"
    cls = item.classification.value if item.classification else "UNCLASSIFIED"
    return f"COMPUTER-{cls}"