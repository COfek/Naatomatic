"""Metric provider protocol and result type for the logistics dashboard framework."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy.orm import Session


@dataclass
class MetricResult:
    """Structured output from a metric provider, consumed by the chart renderer."""

    title: str
    summary: str
    rows: list[dict]         # each row must contain a "label" key plus data keys
    x_label: str = ""
    y_label: str = ""
    # Primary bar series — field names to plot per row. Empty defaults to ["value"].
    series: list[str] = field(default_factory=list)
    # When set, a second chart panel is rendered using this field from each row.
    secondary_series: list[str] = field(default_factory=list)
    # Panel titles used when secondary_series is present (left and right panels).
    primary_title: str = ""
    secondary_title: str = ""


class MetricProvider(ABC):
    @abstractmethod
    def fetch(
        self,
        session: Session,
        *,
        date_range: dict | None = None,
        group_by: str | None = None,
        top_n: int | None = None,
        filters: dict | None = None,
    ) -> MetricResult:
        """Query the DB and return a structured MetricResult. Never touches rendering."""
        ...