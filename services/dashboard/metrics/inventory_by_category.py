"""Inventory by category metric — active item counts, excluding decommissioned."""

from __future__ import annotations

from sqlalchemy import select

from models import tables as t
from models.enums import ComputerStatus, EquipmentKind, MonitorStatus
from services.dashboard.base import MetricProvider, MetricResult


class InventoryByCategoryMetric(MetricProvider):
    _DECOMMISSIONED = frozenset({
        ComputerStatus.DECOMMISSIONED.value,
        MonitorStatus.DECOMMISSIONED.value,
    })

    def fetch(self, session, *, date_range=None, group_by=None, top_n=None, filters=None) -> MetricResult:
        items = session.scalars(select(t.EquipmentItem)).all()
        if not items:
            return MetricResult(
                title="Inventory by Category",
                summary="No equipment found.",
                rows=[],
            )

        counts: dict[str, int] = {}
        for item in items:
            if item.status in self._DECOMMISSIONED:
                continue
            if item.kind == EquipmentKind.MONITOR:
                cat = "MONITOR"
            else:
                cls = item.classification.value if item.classification else "UNCLASSIFIED"
                cat = f"COMPUTER-{cls}"
            counts[cat] = counts.get(cat, 0) + 1

        if not counts:
            return MetricResult(
                title="Inventory by Category",
                summary="No active equipment found.",
                rows=[],
            )

        rows = sorted(
            [{"label": cat, "value": count} for cat, count in counts.items()],
            key=lambda r: -r["value"],
        )
        if top_n:
            rows = rows[:top_n]

        total = sum(r["value"] for r in rows)
        return MetricResult(
            title="Inventory by Category",
            summary=f"Total active equipment: {total} across {len(rows)} categories.",
            rows=rows,
            y_label="Item Count",
        )