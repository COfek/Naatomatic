from __future__ import annotations

import datetime

from models import tables as t
from models.enums import (
    ConstraintLevel,
    DateBlockStatus,
    Population,
    Rank,
    ShiftType,
    RANGE_QUAL_VALID_DAYS,
)
from services.scheduling import SchedulingService

def test_scheduling_service_basic(session):
    """Test that the scheduling service can find candidates in a seeded DB."""
    service = SchedulingService(session)
    
    # We should have some Sadir soldiers eligible for ADHOC
    result = service.recommend_assignment(
        start_date=datetime.date.today() + datetime.timedelta(days=1),
        end_date=datetime.date.today() + datetime.timedelta(days=1),
        duty_type="ADHOC",
        eligible_population=Population.SADIR,
        required_rank=None,
    )
    
    assert result["primary_id"] is not None
    # Adhoc does not need a reserve
    assert result["reserve_id"] is None
    assert isinstance(result["warnings"], list)


def test_scheduling_service_shift_with_reserve(session):
    """Test that a guard shift correctly picks a primary and a reserve."""
    service = SchedulingService(session)
    
    result = service.recommend_assignment(
        start_date=datetime.date.today() + datetime.timedelta(days=3),
        end_date=datetime.date.today() + datetime.timedelta(days=3),
        duty_type=ShiftType.SINGLE_DAY,
        eligible_population=None,
        required_rank=None,
    )
    
    assert result["primary_id"] is not None
    assert result["reserve_id"] is not None
    assert result["primary_id"] != result["reserve_id"]


def test_scheduling_service_hard_constraints_exclude(session):
    """Test that a soldier with a CRITICAL date block is excluded."""
    # Find an active Sadir soldier
    soldier = session.query(t.Personnel).filter_by(population=Population.SADIR, active=True).first()
    
    start = datetime.date.today() + datetime.timedelta(days=10)
    end = start

    # Add a CRITICAL approved block
    block = t.PersonnelDateBlock(
        personnel_id=soldier.id,
        start_date=start,
        end_date=end,
        status=DateBlockStatus.APPROVED,
        level=ConstraintLevel.CRITICAL
    )
    session.add(block)
    session.commit()

    service = SchedulingService(session)
    result = service.recommend_assignment(
        start_date=start,
        end_date=end,
        duty_type="ADHOC",
        eligible_population=Population.SADIR,
        required_rank=None,
    )
    
    assert result["primary_id"] != soldier.id


def test_scheduling_service_soft_constraints_warning(session):
    """Test that soft constraints push candidates to a lower tier and trigger warnings."""
    # Suspend all Sadir except one to force selection of a candidate with a constraint
    sadir_soldiers = session.query(t.Personnel).filter_by(population=Population.SADIR, active=True).all()
    assert len(sadir_soldiers) >= 1
    
    target_soldier = sadir_soldiers[0]
    target_soldier.can_do_adhoc = True
    for s in sadir_soldiers[1:]:
        s.active = False
    
    start = datetime.date.today() + datetime.timedelta(days=300)
    end = start

    # Add a HIGH approved block (soft)
    block = t.PersonnelDateBlock(
        personnel_id=target_soldier.id,
        start_date=start,
        end_date=end,
        status=DateBlockStatus.APPROVED,
        level=ConstraintLevel.HIGH
    )
    session.add(block)
    session.commit()

    service = SchedulingService(session)
    result = service.recommend_assignment(
        start_date=start,
        end_date=end,
        duty_type="ADHOC",
        eligible_population=Population.SADIR,
        required_rank=None,
    )
    
    # It should still pick the target soldier since they are the only active one
    assert result["primary_id"] == target_soldier.id
    # Should include a warning about the HIGH constraint
    assert len(result["warnings"]) > 0
    assert "HIGH constraint" in result["warnings"][0]

