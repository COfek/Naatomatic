"""Metric provider registry — the only whitelist of allowed dashboard queries."""

from services.dashboard.base import MetricProvider
from services.dashboard.metrics.broken_by_type import BrokenByTypeMetric
from services.dashboard.metrics.equipment_shortage import EquipmentShortageMetric
from services.dashboard.metrics.inventory_by_category import InventoryByCategoryMetric
from services.dashboard.metrics.ticket_status import TicketStatusMetric
from services.dashboard.metrics.tickets_over_time import TicketsOverTimeMetric

METRIC_PROVIDERS: dict[str, MetricProvider] = {
    "equipment_shortage":        EquipmentShortageMetric(),
    "ticket_status_distribution": TicketStatusMetric(),
    "inventory_by_category":     InventoryByCategoryMetric(),
    "broken_by_type":            BrokenByTypeMetric(),
    "tickets_over_time":         TicketsOverTimeMetric(),
}

__all__ = ["METRIC_PROVIDERS"]