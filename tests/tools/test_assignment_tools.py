from __future__ import annotations

import datetime
from sqlalchemy.orm import Session

from models import tables as t
from models.enums import AssignmentStatus, ShiftType, Population
from tools.base import ToolContext
from tools.guard_duty_tools import assign_shift, suggest_assignment, auto_assign
from tools.adhoc_tools import assign_adhoc_mission, suggest_adhoc_assignment

def test_suggest_assignment(session: Session):
    ctx = ToolContext(session=session, actor_personal_number="test_actor", roles=["SHIFT_MANAGER"])
    shift = t.Shift(
        type=ShiftType.SINGLE_DAY,
        start_date=datetime.date.today() + datetime.timedelta(days=100),
        end_date=datetime.date.today() + datetime.timedelta(days=100),
        status=AssignmentStatus.OPEN
    )
    session.add(shift)
    session.commit()

    res = suggest_assignment(ctx, shift_id=shift.id)
    assert res.ok
    assert res.value["primary_id"] is not None
    assert res.value["reserve_id"] is not None

def test_assign_shift_valid(session: Session):
    ctx = ToolContext(session=session, actor_personal_number="test_actor", roles=["SHIFT_MANAGER"])
    shift = t.Shift(
        type=ShiftType.SINGLE_DAY,
        start_date=datetime.date.today() + datetime.timedelta(days=150),
        end_date=datetime.date.today() + datetime.timedelta(days=150),
        status=AssignmentStatus.OPEN
    )
    session.add(shift)
    session.commit()

    res = suggest_assignment(ctx, shift_id=shift.id)
    pid = res.value["primary_id"]

    assign_res = assign_shift(ctx, shift_id=shift.id, personnel_id=pid)
    assert assign_res.ok
    assert assign_res.value["status"] == "ASSIGNED"
    
    s = session.get(t.Shift, shift.id)
    assert s.assigned_to == pid
    assert s.status == AssignmentStatus.ASSIGNED

def test_assign_shift_invalid_role(session: Session):
    ctx = ToolContext(session=session, actor_personal_number="test_actor", roles=["SOME_OTHER_ROLE"])
    res = assign_shift(ctx, shift_id=1, personnel_id=1)
    assert not res.ok
    assert "SHIFT_MANAGER" in res.error

def test_auto_assign(session: Session):
    ctx = ToolContext(session=session, actor_personal_number="test_actor", roles=["SHIFT_MANAGER"])
    shift = t.Shift(
        type=ShiftType.WEEK_LONG,
        start_date=datetime.date.today() + datetime.timedelta(days=200),
        end_date=datetime.date.today() + datetime.timedelta(days=200),
        status=AssignmentStatus.OPEN
    )
    session.add(shift)
    session.commit()

    res = auto_assign(ctx, shift_ids=[shift.id])
    assert res.ok
    assert res.value["assigned_count"] == 1
    
    s = session.get(t.Shift, shift.id)
    assert s.assigned_to is not None
    assert s.reserve_id is not None
    assert s.status == AssignmentStatus.ASSIGNED

def test_adhoc_mission(session: Session):
    ctx = ToolContext(session=session, actor_personal_number="test_actor", roles=["SHIFT_MANAGER"])
    mission = t.AdHocMission(
        title="Test Mission",
        start_date=datetime.date.today() + datetime.timedelta(days=250),
        end_date=datetime.date.today() + datetime.timedelta(days=250),
        status=AssignmentStatus.OPEN
    )
    session.add(mission)
    session.commit()

    soldier = session.query(t.Personnel).filter_by(population=Population.SADIR, active=True, can_do_adhoc=True).first()
    session.commit()

    sug = suggest_adhoc_assignment(ctx, mission_id=mission.id)
    assert sug.ok
    assert sug.value["primary_id"] is not None

    assign_res = assign_adhoc_mission(ctx, mission_id=mission.id, personnel_id=sug.value["primary_id"])
    assert assign_res.ok
    
    m = session.get(t.AdHocMission, mission.id)
    assert m.assigned_to == sug.value["primary_id"]
    assert m.status == AssignmentStatus.ASSIGNED

def test_create_and_complete_adhoc_mission(session: Session):
    from tools.adhoc_tools import create_adhoc_mission, mark_adhoc_completed
    ctx = ToolContext(session=session, actor_personal_number="test_actor", roles=["SHIFT_MANAGER"])
    
    # Create mission
    create_res = create_adhoc_mission(ctx, title="Escort Duty", start_date="2026-10-01", days=2)
    assert create_res.ok
    mission_id = create_res.value["mission_id"]

    # Assign it
    soldier = session.query(t.Personnel).filter_by(population=Population.SADIR, active=True, can_do_adhoc=True).first()
    session.commit()
    
    assign_res = assign_adhoc_mission(ctx, mission_id=mission_id, personnel_id=soldier.id)
    assert assign_res.ok, assign_res.error

    # Get initial burden points
    jt = session.query(t.JusticeTable).filter_by(personnel_id=soldier.id).first()
    if not jt:
        jt = t.JusticeTable(personnel_id=soldier.id, period_start=datetime.date.today())
        session.add(jt)
        session.commit()
    initial_points = jt.shifts_burden_points

    # Complete it
    complete_res = mark_adhoc_completed(ctx, mission_id=mission_id)
    assert complete_res.ok
    assert complete_res.value["status"] == "COMPLETED"
    assert complete_res.value["burden_added_to_assignee"] == 1.0  # 0.5 * 2 days

    # Verify burden points increased
    jt = session.query(t.JusticeTable).filter_by(personnel_id=soldier.id).first()
    assert jt.shifts_burden_points == initial_points + 1.0

def test_get_mission_list(session: Session):
    from tools.adhoc_tools import get_mission_list
    ctx = ToolContext(session=session, actor_personal_number="test_actor", roles=[])
    
    # Just verify the read-only query doesn't crash and returns the seeded data
    res = get_mission_list(ctx)
    assert res.ok
    assert isinstance(res.value, list)
    
    # Filter by OPEN
    res_open = get_mission_list(ctx, status="OPEN")
    assert res_open.ok
    for m in res_open.value:
        assert m["status"] == "OPEN"
        
    # Invalid status
    res_err = get_mission_list(ctx, status="FAKE_STATUS")
    assert not res_err.ok
