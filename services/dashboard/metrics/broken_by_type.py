"""Broken / formatting equipment by type metric."""

from __future__ import annotations

from sqlalchemy import select

from models import tables as t
from models.enums import ComputerStatus, EquipmentKind, MonitorStatus
from services.dashboard.base import MetricProvider, MetricResult


class BrokenByTypeMetric(MetricProvider):
    _BROKEN_STATUSES = frozenset({
        ComputerStatus.BROKEN.value,
        MonitorStatus.BROKEN.value,
        ComputerStatus.FORMATTING.value,
    })

    def fetch(self, session, *, date_range=None, group_by=None, top_n=None, filters=None) -> MetricResult:
        items = session.scalars(select(t.EquipmentItem)).all()

        counts: dict[str, int] = {}
        for item in items:
            if item.status not in self._BROKEN_STATUSES:
                continue
            if item.kind == EquipmentKind.MONITOR:
                cat = "MONITOR"
            else:
                cls = item.classification.value if item.classification else "UNCLASSIFIED"
                cat = f"COMPUTER-{cls}"
            counts[cat] = counts.get(cat, 0) + 1

        if not counts:
            return MetricResult(
                title="Broken Equipment by Type",
                summary="No broken or formatting equipment found.",
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
            title="Broken Equipment by Type",
            summary=f"{total} broken/formatting items across {len(rows)} category(ies).",
            rows=rows,
            y_label="Item Count",
        )