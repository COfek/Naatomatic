"""Smoke tests — prove the data layer + constraint engine + in-memory fixture work.

These also serve as the example pattern for unit tests (assert over a seeded session).
"""

from __future__ import annotations

from sqlalchemy import select

from models import tables as t
from models.enums import DEPOT_PERSONAL_NUMBER
from rules.constraints import run_all


def test_all_hard_constraints_pass(session):
    """Generated in-memory data satisfies every hard constraint (HC-*)."""
    violations = {code: v for code, v in run_all(session).items() if v}
    assert not violations, f"constraint violations: {violations}"


def test_depot_holder_exists(session):
    """The reserved equipment depot (personal number 1234567) is always present."""
    depot = session.scalar(
        select(t.Personnel).where(t.Personnel.personal_number == DEPOT_PERSONAL_NUMBER)
    )
    assert depot is not None
    assert depot.full_name == "Equipment Depot"


def test_personnel_were_generated(session):
    """Seed produced real personnel besides the depot."""
    people = session.scalars(select(t.Personnel)).all()
    assert len(people) > 1
