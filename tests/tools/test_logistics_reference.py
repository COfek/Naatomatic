"""Reference tool test — the pattern for every pillar's tool tests.

Covers both paths against the in-memory seeded `session` fixture:
- accept: a valid sign-out succeeds and the DB reflects it,
- reject: an action that breaks a hard rule (HC-LOG-1) is blocked and the DB is
  left unchanged,
- permission: a non-manager is refused.
"""

from __future__ import annotations

from sqlalchemy import select

from models import tables as t
from models.enums import EquipmentKind, MonitorStatus, Population
from tools.base import ToolContext
from tools.logistics_tools import SignEquipmentArgs, sign_equipment

MANAGER = ["LOGISTICS_OFFICER"]


def _person(session, pn: str) -> t.Personnel:
    p = t.Personnel(personal_number=pn, full_name=f"Test {pn}", population=Population.SADIR)
    session.add(p)
    session.flush()
    return p


def _monitor(session, cat: str, signed_to: int | None) -> t.EquipmentItem:
    m = t.EquipmentItem(catalog_number=cat, kind=EquipmentKind.MONITOR,
                        status=MonitorStatus.FUNCTIONAL.value, signed_to=signed_to)
    session.add(m)
    session.flush()
    return m


def test_sign_equipment_accept(session):
    p = _person(session, "T-1001")
    _monitor(session, "T-M1", None)
    session.commit()
    ctx = ToolContext(session=session, actor_personal_number="9999", roles=MANAGER)

    res = sign_equipment(ctx, SignEquipmentArgs(catalog_number="T-M1", personnel_id=p.id))

    assert res.ok, res.error
    assert session.get(t.EquipmentItem, "T-M1").signed_to == p.id
    assert res.value["handover_pending"] is True


def test_sign_equipment_rejects_third_monitor(session):
    p = _person(session, "T-1002")
    _monitor(session, "T-M2", p.id)   # already holds 2
    _monitor(session, "T-M3", p.id)
    _monitor(session, "T-M4", None)   # the 3rd we try to add
    session.commit()
    ctx = ToolContext(session=session, actor_personal_number="9999", roles=MANAGER)

    res = sign_equipment(ctx, SignEquipmentArgs(catalog_number="T-M4", personnel_id=p.id))

    assert not res.ok                                   # HC-LOG-1 blocks it
    assert session.get(t.EquipmentItem, "T-M4").signed_to is None  # rolled back


def test_sign_requires_role(session):
    p = _person(session, "T-1003")
    _monitor(session, "T-M5", None)
    session.commit()
    ctx = ToolContext(session=session, actor_personal_number="9999", roles=[])  # no role

    res = sign_equipment(ctx, SignEquipmentArgs(catalog_number="T-M5", personnel_id=p.id))

    assert not res.ok and "LOGISTICS_OFFICER" in res.error
