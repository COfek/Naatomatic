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

    soldier = session.query(t.Personnel).filter_by(population=Population.SADIR, active=True).first()
    soldier.can_do_adhoc = True
    session.commit()

    sug = suggest_adhoc_assignment(ctx, mission_id=mission.id)
    assert sug.ok
    assert sug.value["primary_id"] is not None

    assign_res = assign_adhoc_mission(ctx, mission_id=mission.id, personnel_id=sug.value["primary_id"])
    assert assign_res.ok
    
    m = session.get(t.AdHocMission, mission.id)
    assert m.assigned_to == sug.value["primary_id"]
    assert m.status == AssignmentStatus.ASSIGNED
