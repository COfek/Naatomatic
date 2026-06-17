"""Print a summary of the generated database and verify key hard constraints."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

from models.db import DEFAULT_DB_PATH, create_session, get_engine
from models.enums import DEPOT_PERSONAL_NUMBER, EquipmentKind, Population, ShiftType
from models import tables as m


def main() -> None:
    session = create_session(get_engine(DEFAULT_DB_PATH))

    def count(model) -> int:
        return session.scalar(select(func.count()).select_from(model))

    print("=== Row counts ===")
    for model in (
        m.Personnel, m.PersonnelDateBlock, m.Switch, m.Port, m.WallJack,
        m.EquipmentItem, m.Ticket, m.Shift, m.AdHocMission, m.JusticeTable,
        m.Calendar, m.CalendarEvent,
    ):
        print(f"  {model.__name__:22} {count(model)}")

    people = session.scalars(select(m.Personnel)).all()
    pops = Counter(p.population.value for p in people)
    print(f"\n=== Personnel ({len(people)}) ===")
    print(f"  Population: {dict(pops)}")
    print(f"  Managers:   {[p.full_name + ':' + ','.join(p.roles) for p in people if p.roles]}")

    print("\n=== Constraint checks (should all PASS) ===")
    problems = []

    # HC-LOG-1: max 2 monitors per person
    mon = Counter(
        e.signed_to for e in session.scalars(
            select(m.EquipmentItem).where(m.EquipmentItem.kind == EquipmentKind.MONITOR)
        ).all() if e.signed_to is not None
    )
    depot = session.scalar(select(m.Personnel).where(m.Personnel.personal_number == DEPOT_PERSONAL_NUMBER))
    over_mon = {pid: c for pid, c in mon.items() if c > 2 and pid != depot.id}
    problems.append(("HC-LOG-1 (<=2 monitors/person)", over_mon))

    # HC-LOG-2: max 1 computer per classification per person
    comp_pairs = Counter()
    for e in session.scalars(
        select(m.EquipmentItem).where(m.EquipmentItem.kind == EquipmentKind.COMPUTER)
    ).all():
        if e.signed_to is not None and e.signed_to != depot.id:
            comp_pairs[(e.signed_to, e.classification.value)] += 1
    over_comp = {k: v for k, v in comp_pairs.items() if v > 1}
    problems.append(("HC-LOG-2 (<=1 computer/classification/person)", over_comp))

    # SUPPORT shifts must be assigned to Sadir only
    bad_support = []
    for s in session.scalars(select(m.Shift).where(m.Shift.type == ShiftType.SUPPORT)).all():
        if s.assigned_to:
            holder = session.get(m.Personnel, s.assigned_to)
            if holder.population != Population.SADIR or not holder.can_do_support:
                bad_support.append(s.id)
    problems.append(("SUPPORT shifts -> Sadir w/ can_do_support", bad_support))

    for label, bad in problems:
        status = "PASS" if not bad else f"FAIL: {bad}"
        print(f"  [{status}] {label}")

    # Show the fairest vs busiest by guard burden (separate pools)
    jt = session.scalars(select(m.JusticeTable)).all()
    jt_sorted = sorted(jt, key=lambda r: r.guard_burden_points)
    print("\n=== Burden points (Justice Table) — guard / support / adhoc pools ===")
    for row in (jt_sorted[:3] + ["..."] + jt_sorted[-3:]):
        if row == "...":
            print("  ...")
            continue
        p = session.get(m.Personnel, row.personnel_id)
        print(f"  {p.full_name:24} {p.population.value:6} "
              f"guard={row.guard_burden_points:5.1f} support={row.support_burden_points:4.1f} "
              f"adhoc={row.adhoc_burden_points:4.1f}  week={row.week_long_count} day={row.single_day_count}")

    session.close()


if __name__ == "__main__":
    main()
