"""Ticket status distribution metric."""

from __future__ import annotations

from sqlalchemy import func, select

from models import tables as t
from services.dashboard.base import MetricProvider, MetricResult


class TicketStatusMetric(MetricProvider):
    def fetch(self, session, *, date_range=None, group_by=None, top_n=None, filters=None) -> MetricResult:
        query = (
            select(t.Ticket.status, func.count(t.Ticket.id).label("count"))
            .group_by(t.Ticket.status)
        )

        ticket_type = (filters or {}).get("ticket_type")
        if ticket_type:
            query = query.where(t.Ticket.type == ticket_type)

        rows_raw = session.execute(query).all()
        if not rows_raw:
            return MetricResult(
                title="Ticket Status Distribution",
                summary="No tickets found.",
                rows=[],
            )

        rows = sorted(
            [{"label": row.status, "value": row.count} for row in rows_raw],
            key=lambda r: -r["value"],
        )
        if top_n:
            rows = rows[:top_n]

        total = sum(r["value"] for r in rows)
        detail = ", ".join(f"{r['label']}: {r['value']}" for r in rows)
        return MetricResult(
            title="Ticket Status Distribution",
            summary=f"Total tickets: {total}. {detail}.",
            rows=rows,
            y_label="Ticket Count",
        )