"""Tickets opened over time metric — groups by day / week / month."""

from __future__ import annotations

from sqlalchemy import func, select

from models import tables as t
from services.dashboard.base import MetricProvider, MetricResult

_STRFTIME = {
    "day":   "%Y-%m-%d",
    "week":  "%Y-W%W",
    "month": "%Y-%m",
}


class TicketsOverTimeMetric(MetricProvider):
    def fetch(self, session, *, date_range=None, group_by=None, top_n=None, filters=None) -> MetricResult:
        period_key = group_by if group_by in _STRFTIME else "week"
        fmt = _STRFTIME[period_key]

        period_col = func.strftime(fmt, t.Ticket.created_at).label("period")
        query = (
            select(period_col, func.count(t.Ticket.id).label("count"))
            .group_by(period_col)
            .order_by(period_col)
        )

        ticket_type = (filters or {}).get("ticket_type")
        if ticket_type:
            query = query.where(t.Ticket.type == ticket_type)

        if date_range:
            if start := date_range.get("start"):
                query = query.where(t.Ticket.created_at >= start)
            if end := date_range.get("end"):
                query = query.where(t.Ticket.created_at <= end)

        rows_raw = session.execute(query).all()
        if not rows_raw:
            return MetricResult(
                title="Tickets Over Time",
                summary="No tickets found.",
                rows=[],
            )

        rows = [{"label": row.period, "value": row.count} for row in rows_raw]
        if top_n:
            rows = rows[:top_n]

        total = sum(r["value"] for r in rows)
        return MetricResult(
            title=f"Tickets Opened Over Time (by {period_key.title()})",
            summary=f"Total tickets: {total} over {len(rows)} {period_key}(s).",
            rows=rows,
            x_label=period_key.title(),
            y_label="Ticket Count",
        )