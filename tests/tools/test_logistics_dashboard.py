"""Tests for the logistics dashboard framework.

Covers: no data, no shortages, top_n, unsupported metric, chart generation, chart URL.
"""

from __future__ import annotations

import pytest

from models import tables as t
from models.db import create_all, create_session, get_engine
from models.enums import (
    ComputerStatus,
    DEPOT_PERSONAL_NUMBER,
    EquipmentKind,
    MonitorStatus,
    Population,
)
from tools.base import ToolContext
from tools.logistics_tools import GenerateLogisticsDashboardArgs, generate_logistics_dashboard


@pytest.fixture
def clean_session():
    """Empty in-memory DB — no seeded data."""
    engine = get_engine(":memory:")
    create_all(engine)
    s = create_session(engine)
    yield s
    s.close()


# ---- DB helpers ------------------------------------------------------------

def _depot(session) -> t.Personnel:
    d = t.Personnel(
        personal_number=DEPOT_PERSONAL_NUMBER,
        full_name="Equipment Depot",
        population=Population.SADIR,
        active=True,
    )
    session.add(d)
    session.flush()
    return d


def _person(session, pn: str = "T-0001") -> t.Personnel:
    p = t.Personnel(
        personal_number=pn,
        full_name=f"Test {pn}",
        population=Population.SADIR,
        active=True,
    )
    session.add(p)
    session.flush()
    return p


def _monitor(session, cat: str, signed_to: int | None, status: str = MonitorStatus.FUNCTIONAL.value) -> t.EquipmentItem:
    item = t.EquipmentItem(
        catalog_number=cat,
        kind=EquipmentKind.MONITOR,
        status=status,
        signed_to=signed_to,
    )
    session.add(item)
    session.flush()
    return item


# ============================================================================
# No-data tests
# ============================================================================

def test_no_equipment_items_returns_empty_rows(clean_session):
    _depot(clean_session)
    _person(clean_session)
    clean_session.commit()

    ctx = ToolContext(session=clean_session)
    result = generate_logistics_dashboard(
        ctx, GenerateLogisticsDashboardArgs(metric="equipment_shortage")
    )

    assert result.ok
    assert result.value["rows"] == []
    assert result.value["chart_url"] is None
    assert "no equipment" in result.value["summary"].lower()


def test_no_active_personnel_returns_empty_rows(clean_session):
    clean_session.commit()

    ctx = ToolContext(session=clean_session)
    result = generate_logistics_dashboard(
        ctx, GenerateLogisticsDashboardArgs(metric="equipment_shortage")
    )

    assert result.ok
    assert result.value["rows"] == []


# ============================================================================
# No-shortages test
# ============================================================================

def test_no_shortages_detected(clean_session):
    depot = _depot(clean_session)
    _person(clean_session, "T-9001")
    clean_session.commit()

    # 20 monitors at depot for 1 active person (required = 1) → all surplus
    for i in range(20):
        _monitor(clean_session, f"M-{i:03d}", signed_to=depot.id)
    clean_session.commit()

    ctx = ToolContext(session=clean_session)
    result = generate_logistics_dashboard(
        ctx, GenerateLogisticsDashboardArgs(metric="equipment_shortage")
    )

    assert result.ok
    rows = result.value["rows"]
    assert rows, "expected at least one row for MONITOR category"
    assert all(r["shortage"] <= 0 for r in rows), f"unexpected shortages: {rows}"
    assert "no shortage" in result.value["summary"].lower()


# ============================================================================
# top_n test
# ============================================================================

def test_top_n_caps_row_count(session):
    """Seeded DB has multiple equipment categories; top_n=2 must cap at 2 rows."""
    ctx = ToolContext(session=session)
    result = generate_logistics_dashboard(
        ctx, GenerateLogisticsDashboardArgs(metric="equipment_shortage", top_n=2)
    )

    assert result.ok
    assert len(result.value["rows"]) <= 2


# ============================================================================
# Unsupported metric
# ============================================================================

def test_unsupported_metric_returns_error(session):
    ctx = ToolContext(session=session)
    result = generate_logistics_dashboard(
        ctx, GenerateLogisticsDashboardArgs(metric="does_not_exist")
    )

    assert not result.ok
    assert "does_not_exist" in result.error
    assert "valid metrics" in result.error.lower()


# ============================================================================
# Chart generation tests (via render_chart directly to avoid FS side-effects)
# ============================================================================

def test_render_chart_creates_png_file(session, tmp_path):
    """render_chart must write a PNG to charts_dir and return a URL string."""
    from services.dashboard.metrics import METRIC_PROVIDERS
    from services.dashboard.renderer import render_chart

    metric_result = METRIC_PROVIDERS["equipment_shortage"].fetch(session)
    if not metric_result.rows:
        pytest.skip("seeded DB produced no shortage rows — cannot test chart creation")

    url = render_chart(metric_result, "bar", tmp_path)

    chart_files = list(tmp_path.glob("dashboard_*.png"))
    assert len(chart_files) == 1
    assert chart_files[0].stat().st_size > 0


def test_render_chart_url_format(session, tmp_path):
    """chart_url must start with CHARTS_BASE_URL and reference the file name."""
    from config.settings import CHARTS_BASE_URL
    from services.dashboard.metrics import METRIC_PROVIDERS
    from services.dashboard.renderer import render_chart

    metric_result = METRIC_PROVIDERS["ticket_status_distribution"].fetch(session)
    if not metric_result.rows:
        pytest.skip("no tickets in seeded DB")

    url = render_chart(metric_result, "bar", tmp_path)

    assert url.startswith(CHARTS_BASE_URL)
    assert url.endswith(".png")
    # Filename in URL must match the file on disk
    filename = url.split("/")[-1]
    assert (tmp_path / filename).exists()


# ============================================================================
# Additional metric smoke tests (verify all providers return valid MetricResult)
# ============================================================================

@pytest.mark.parametrize("metric", [
    "equipment_shortage",
    "ticket_status_distribution",
    "inventory_by_category",
    "broken_by_type",
    "tickets_over_time",
])
def test_all_metrics_return_valid_result(session, metric):
    from services.dashboard.metrics import METRIC_PROVIDERS

    result = METRIC_PROVIDERS[metric].fetch(session)

    assert result.title
    assert result.summary
    assert isinstance(result.rows, list)
    for row in result.rows:
        assert "label" in row