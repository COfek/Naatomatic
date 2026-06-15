"""Hard constraints (HC-*) defined once, as database-wide checks.

Each ``check_*`` function scans the database and returns a list of human-readable
violation strings (empty list == the rule holds). ``ALL_CHECKS`` registers every
rule with its code and description; ``run_all`` executes them.

Rule codes map directly to DESIGN.md:
  HC-NET-1   one network port per classification per person
  HC-LOG-1   max 2 monitors per person
  HC-LOG-2   max 1 computer per classification per person
  HC-GD-0    assignment population/rank match
  HC-GD-3    Keva not assigned beyond annual quota (2 week-long / 4 single-day)
  HC-GD-5    assignee not date-blocked on the assignment's dates
  HC-GD-6    assignee has the duty-type flag (incl. SUPPORT => Sadir + can_do_support)
  DEPOT      broken/formatting items live with the depot; in-use items don't
  STATUS     equipment status is valid for its kind
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.enums import (
    DEPOT_PERSONAL_NUMBER,
    AssignmentStatus,
    ComputerStatus,
    EquipmentKind,
    MonitorStatus,
    Population,
    ShiftType,
)
from models import tables as t

KEVA_WEEK_LONG_QUOTA = 2
KEVA_SINGLE_DAY_QUOTA = 4


def _depot_id(session: Session) -> int | None:
    depot = session.scalar(
        select(t.Personnel).where(t.Personnel.personal_number == DEPOT_PERSONAL_NUMBER)
    )
    return depot.id if depot else None


def _dates_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #
def check_hc_net_1(session: Session) -> list[str]:
    """HC-NET-1: a person holds at most one port per classification."""
    seen: dict[int, Counter] = defaultdict(Counter)
    ports = session.scalars(select(t.Port).where(t.Port.allocated_to.is_not(None))).all()
    for port in ports:
        classification = port.switch.classification  # derived from the switch
        seen[port.allocated_to][classification] += 1
    violations = []
    for person_id, by_class in seen.items():
        for classification, count in by_class.items():
            if count > 1:
                violations.append(
                    f"person id={person_id} holds {count} ports of {classification.value}"
                )
    return violations


# --------------------------------------------------------------------------- #
# Logistics
# --------------------------------------------------------------------------- #
def check_hc_log_1(session: Session) -> list[str]:
    """HC-LOG-1: at most 2 monitors per person (depot exempt)."""
    depot = _depot_id(session)
    counts: Counter = Counter()
    monitors = session.scalars(
        select(t.EquipmentItem).where(t.EquipmentItem.kind == EquipmentKind.MONITOR)
    ).all()
    for item in monitors:
        if item.signed_to is not None and item.signed_to != depot:
            counts[item.signed_to] += 1
    return [
        f"person id={pid} signed for {c} monitors (max 2)"
        for pid, c in counts.items() if c > 2
    ]


def check_hc_log_2(session: Session) -> list[str]:
    """HC-LOG-2: at most 1 computer per classification per person (depot exempt)."""
    depot = _depot_id(session)
    pairs: Counter = Counter()
    computers = session.scalars(
        select(t.EquipmentItem).where(t.EquipmentItem.kind == EquipmentKind.COMPUTER)
    ).all()
    for item in computers:
        if item.signed_to is not None and item.signed_to != depot:
            pairs[(item.signed_to, item.classification)] += 1
    return [
        f"person id={pid} signed for {c} computers of {cls.value if cls else '?'} (max 1)"
        for (pid, cls), c in pairs.items() if c > 1
    ]


# --------------------------------------------------------------------------- #
# Scheduling — shared helpers over assignments (shifts + ad-hoc)
# --------------------------------------------------------------------------- #
@dataclass
class _Assignment:
    kind: str           # "shift" or "adhoc"
    id: int
    holder_id: int
    population: Population | None
    rank: object
    start: date
    end: date
    shift_type: ShiftType | None  # None for ad-hoc


def _assignments(session: Session) -> list[_Assignment]:
    out: list[_Assignment] = []
    for s in session.scalars(
        select(t.Shift).where(t.Shift.assigned_to.is_not(None))
    ).all():
        out.append(_Assignment("shift", s.id, s.assigned_to, s.eligible_population,
                               s.required_rank, s.start_date, s.end_date, s.type))
    for a in session.scalars(
        select(t.AdHocMission).where(t.AdHocMission.assigned_to.is_not(None))
    ).all():
        out.append(_Assignment("adhoc", a.id, a.assigned_to, a.eligible_population,
                               a.required_rank, a.start_date, a.end_date, None))
    return out


def check_hc_gd_0(session: Session) -> list[str]:
    """HC-GD-0: assignee matches the assignment's population/rank targeting."""
    violations = []
    people = {p.id: p for p in session.scalars(select(t.Personnel)).all()}
    for a in _assignments(session):
        holder = people.get(a.holder_id)
        if holder is None:
            violations.append(f"{a.kind} id={a.id} assigned to missing person {a.holder_id}")
            continue
        if a.population is not None and holder.population != a.population:
            violations.append(
                f"{a.kind} id={a.id} wants {a.population.value} but holder is {holder.population.value}"
            )
        if a.rank is not None and holder.rank != a.rank:
            violations.append(f"{a.kind} id={a.id} wants rank {a.rank} but holder is {holder.rank}")
    return violations


def check_hc_gd_5(session: Session) -> list[str]:
    """HC-GD-5: assignee is not date-blocked over the assignment's dates."""
    violations = []
    blocks: dict[int, list] = defaultdict(list)
    for b in session.scalars(select(t.PersonnelDateBlock)).all():
        blocks[b.personnel_id].append(b)
    for a in _assignments(session):
        for b in blocks.get(a.holder_id, []):
            if _dates_overlap(a.start, a.end, b.start_date, b.end_date):
                violations.append(
                    f"{a.kind} id={a.id} ({a.start}..{a.end}) overlaps date block of person {a.holder_id}"
                )
                break
    return violations


def check_hc_gd_6(session: Session) -> list[str]:
    """HC-GD-6: assignee has the matching duty-type flag (SUPPORT => Sadir+can_do_support)."""
    violations = []
    people = {p.id: p for p in session.scalars(select(t.Personnel)).all()}
    for a in _assignments(session):
        holder = people.get(a.holder_id)
        if holder is None:
            continue
        if a.kind == "adhoc":
            if not holder.can_do_adhoc:
                violations.append(f"adhoc id={a.id} -> person {a.holder_id} lacks can_do_adhoc")
            continue
        if a.shift_type == ShiftType.WEEK_LONG and not holder.can_do_week_long:
            violations.append(f"shift id={a.id} WEEK_LONG -> person {a.holder_id} lacks can_do_week_long")
        elif a.shift_type == ShiftType.SINGLE_DAY and not holder.can_do_single_day:
            violations.append(f"shift id={a.id} SINGLE_DAY -> person {a.holder_id} lacks can_do_single_day")
        elif a.shift_type == ShiftType.SUPPORT and not (
            holder.population == Population.SADIR and holder.can_do_support
        ):
            violations.append(
                f"shift id={a.id} SUPPORT -> person {a.holder_id} not Sadir-with-can_do_support"
            )
    return violations


def check_hc_gd_3(session: Session) -> list[str]:
    """HC-GD-3: Keva not assigned beyond annual quota (2 week-long / 4 single-day)."""
    week: Counter = Counter()
    day: Counter = Counter()
    people = {p.id: p for p in session.scalars(select(t.Personnel)).all()}
    for s in session.scalars(select(t.Shift).where(t.Shift.assigned_to.is_not(None))).all():
        holder = people.get(s.assigned_to)
        if holder is None or holder.population != Population.KEVA:
            continue
        if s.type == ShiftType.WEEK_LONG:
            week[s.assigned_to] += 1
        elif s.type == ShiftType.SINGLE_DAY:
            day[s.assigned_to] += 1
    violations = []
    for pid, c in week.items():
        if c > KEVA_WEEK_LONG_QUOTA:
            violations.append(f"Keva person {pid} has {c} week-long shifts (quota {KEVA_WEEK_LONG_QUOTA})")
    for pid, c in day.items():
        if c > KEVA_SINGLE_DAY_QUOTA:
            violations.append(f"Keva person {pid} has {c} single-day shifts (quota {KEVA_SINGLE_DAY_QUOTA})")
    return violations


# --------------------------------------------------------------------------- #
# Equipment integrity
# --------------------------------------------------------------------------- #
def check_depot(session: Session) -> list[str]:
    """DEPOT: broken/formatting items belong to the depot; in-use items do not."""
    depot = _depot_id(session)
    violations = []
    if depot is None:
        return ["depot personnel (1234567) is missing"]
    for item in session.scalars(select(t.EquipmentItem)).all():
        status = item.status
        if status in (ComputerStatus.BROKEN.value, ComputerStatus.FORMATTING.value,
                      MonitorStatus.BROKEN.value):
            if item.signed_to != depot:
                violations.append(f"item {item.catalog_number} is {status} but not signed to depot")
        if status == ComputerStatus.IN_USE.value:
            if item.signed_to is None or item.signed_to == depot:
                violations.append(f"computer {item.catalog_number} is IN_USE but not signed to a real person")
    return violations


def check_status(session: Session) -> list[str]:
    """STATUS: equipment status is one of the valid values for its kind."""
    monitor_ok = {s.value for s in MonitorStatus}
    computer_ok = {s.value for s in ComputerStatus}
    violations = []
    for item in session.scalars(select(t.EquipmentItem)).all():
        ok = monitor_ok if item.kind == EquipmentKind.MONITOR else computer_ok
        if item.status not in ok:
            violations.append(f"item {item.catalog_number} ({item.kind.value}) has invalid status {item.status}")
    return violations


# --------------------------------------------------------------------------- #
# Registry + runner
# --------------------------------------------------------------------------- #
@dataclass
class Check:
    code: str
    description: str
    fn: Callable[[Session], list[str]]


ALL_CHECKS: list[Check] = [
    Check("HC-NET-1", "One port per classification per person", check_hc_net_1),
    Check("HC-LOG-1", "Max 2 monitors per person", check_hc_log_1),
    Check("HC-LOG-2", "Max 1 computer per classification per person", check_hc_log_2),
    Check("HC-GD-0", "Assignment population/rank match", check_hc_gd_0),
    Check("HC-GD-3", "Keva within annual quota (2 week / 4 day)", check_hc_gd_3),
    Check("HC-GD-5", "Assignee not date-blocked on the dates", check_hc_gd_5),
    Check("HC-GD-6", "Assignee has duty-type flag (SUPPORT=>Sadir)", check_hc_gd_6),
    Check("DEPOT", "Broken/formatting -> depot; in-use -> real person", check_depot),
    Check("STATUS", "Equipment status valid for its kind", check_status),
]


def run_all(session: Session) -> dict[str, list[str]]:
    """Run every check and return {code: [violations]} (empty list == pass)."""
    return {check.code: check.fn(session) for check in ALL_CHECKS}
