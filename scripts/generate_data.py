"""Generate a random-but-valid Naatomatic database.

Usage:
    python scripts/generate_data.py [num_personnel] [--seed N] [--db PATH]

Produces data that respects the hard constraints in DESIGN.md so it actually
exercises the system (HC-NET-1, HC-LOG-1/2, HC-GD-0/5/6, Sadir-only SUPPORT,
the depot holder, etc.). Default: 30 personnel.
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta

from faker import Faker

# Allow running as a plain script (python scripts/generate_data.py).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.db import DEFAULT_DB_PATH, create_all, create_session, get_engine
from models.enums import (
    DEPOT_PERSONAL_NUMBER,
    FORMATTING_DURATION_DAYS,
    AssignmentStatus,
    CalendarKind,
    CalendarSubjectType,
    Classification,
    ComputerStatus,
    EquipmentKind,
    MonitorStatus,
    Population,
    PortStatus,
    Rank,
    Role,
    ShiftType,
    TicketStatus,
    TicketType,
    TimeOfDay,
)
from models import tables as m

YEAR = 2026
YEAR_START = date(YEAR, 1, 1)
BURDEN = {ShiftType.WEEK_LONG: 7.0, ShiftType.SINGLE_DAY: 1.0, ShiftType.SUPPORT: 1.0}


def rand_date_in_year(fake: Faker) -> date:
    return fake.date_between(start_date=YEAR_START, end_date=date(YEAR, 12, 31))


# --------------------------------------------------------------------------- #
def generate(session, num_personnel: int, fake: Faker) -> None:
    # --- Depot holder (always present) ---
    depot = m.Personnel(
        personal_number=DEPOT_PERSONAL_NUMBER,
        full_name="Equipment Depot",
        population=Population.SADIR,
        rank=None,
        roles=[],
        can_do_week_long=False,
        can_do_single_day=False,
        can_do_support=False,
        can_do_adhoc=False,
        active=True,
    )
    session.add(depot)
    session.flush()

    # --- Personnel ---
    people: list[m.Personnel] = []
    for _ in range(num_personnel):
        population = random.choice([Population.KEVA, Population.SADIR])
        is_sadir = population == Population.SADIR
        p = m.Personnel(
            personal_number=str(fake.unique.random_int(min=2000000, max=8999999)),
            full_name=fake.name(),
            population=population,
            rank=random.choice(list(Rank)),
            roles=[],
            can_do_week_long=random.random() > 0.1,
            can_do_single_day=random.random() > 0.1,
            # SUPPORT is Sadir-only and course-gated (default false).
            can_do_support=is_sadir and random.random() > 0.5,
            can_do_adhoc=random.random() > 0.1,
            active=random.random() > 0.05,
        )
        people.append(p)
        session.add(p)
    session.flush()

    # --- Manager roles: assign one of each among active people ---
    for role in (Role.NETWORK_MANAGER, Role.LOGISTICS_OFFICER, Role.SHIFT_MANAGER):
        candidate = random.choice(people)
        candidate.roles = list(candidate.roles) + [role.value]
    session.flush()

    real_people = people  # everyone except depot

    # --- Date blocks for ~20% of people (tracked so we never assign over them) ---
    date_blocks: dict[int, list[tuple[date, date]]] = {p.id: [] for p in real_people}
    for p in real_people:
        if random.random() < 0.2:
            start = rand_date_in_year(fake)
            end = start + timedelta(days=random.randint(1, 5))
            date_blocks[p.id].append((start, end))
            session.add(
                m.PersonnelDateBlock(
                    personnel_id=p.id,
                    start_date=start,
                    end_date=end,
                    reason=random.choice(["trip", "appointment", "family event", "course"]),
                )
            )

    # --- Network: switches + ports + wall jacks ---
    num_switches = max(2, num_personnel // 6)
    all_ports: list[m.Port] = []
    for i in range(num_switches):
        classification = random.choice(list(Classification))
        total_ports = random.choice([8, 16, 24])
        sw = m.Switch(
            name=f"SW-{i + 1:02d}",
            location=fake.city(),
            classification=classification,
            total_ports=total_ports,
        )
        session.add(sw)
        session.flush()
        for pn in range(1, total_ports + 1):
            port = m.Port(switch_id=sw.id, port_number=pn, status=PortStatus.FREE)
            session.add(port)
            all_ports.append((port, classification))
    session.flush()

    # Allocate some ports, respecting HC-NET-1 (<=1 port per classification per person).
    used_class_by_person: dict[int, set] = {p.id: set() for p in real_people}
    wall_jack_count = 0
    for port, classification in all_ports:
        if random.random() < 0.4:
            eligible = [
                p for p in real_people
                if classification not in used_class_by_person[p.id] and p.active
            ]
            if eligible:
                holder = random.choice(eligible)
                port.status = PortStatus.OCCUPIED
                port.allocated_to = holder.id
                used_class_by_person[holder.id].add(classification)
                wall_jack_count += 1
                session.add(
                    m.WallJack(
                        label=f"WJ-{wall_jack_count:03d}",
                        room=f"Room {random.randint(100, 399)}",
                        port_id=port.id,
                    )
                )
    # A few unconnected wall jacks too.
    for _ in range(max(1, num_personnel // 10)):
        wall_jack_count += 1
        session.add(
            m.WallJack(label=f"WJ-{wall_jack_count:03d}", room=f"Room {random.randint(100, 399)}", port_id=None)
        )
    session.flush()

    # --- Logistics: equipment ---
    monitor_count_by_person: dict[int, int] = {p.id: 0 for p in real_people}
    computer_class_by_person: dict[int, set] = {p.id: set() for p in real_people}
    catalog = 100000

    def next_catalog() -> str:
        nonlocal catalog
        catalog += 1
        return f"CAT-{catalog}"

    # Monitors (HC-LOG-1: max 2 per person)
    for _ in range(int(num_personnel * 1.5)):
        if random.random() < 0.1:
            status = MonitorStatus.BROKEN
            signed = depot.id
        else:
            status = MonitorStatus.FUNCTIONAL
            eligible = [p for p in real_people if monitor_count_by_person[p.id] < 2 and p.active]
            if eligible and random.random() < 0.7:
                holder = random.choice(eligible)
                monitor_count_by_person[holder.id] += 1
                signed = holder.id
            else:
                signed = depot.id
        session.add(
            m.EquipmentItem(
                catalog_number=next_catalog(),
                kind=EquipmentKind.MONITOR,
                status=status.value,
                classification=None,
                signed_to=signed,
            )
        )

    # Computers (HC-LOG-2: max 1 per classification per person)
    formatting_items: list[tuple[str, date]] = []
    for _ in range(int(num_personnel * 1.2)):
        classification = random.choice(list(Classification))
        roll = random.random()
        cat = next_catalog()
        if roll < 0.1:  # broken -> depot
            status, signed = ComputerStatus.BROKEN, depot.id
        elif roll < 0.2:  # formatting -> depot, calendar event
            status, signed = ComputerStatus.FORMATTING, depot.id
            sent = date.today() - timedelta(days=random.randint(0, FORMATTING_DURATION_DAYS - 1))
            formatting_items.append((cat, sent))
        elif roll < 0.3:  # ready for pickup -> depot
            status, signed = ComputerStatus.READY_FOR_PICKUP, depot.id
        elif roll < 0.55:  # ready to use (inventory) -> depot
            status, signed = ComputerStatus.READY_TO_USE, depot.id
        else:  # in use -> a person, respecting per-classification cap
            eligible = [
                p for p in real_people
                if classification not in computer_class_by_person[p.id] and p.active
            ]
            if eligible:
                holder = random.choice(eligible)
                computer_class_by_person[holder.id].add(classification)
                status, signed = ComputerStatus.IN_USE, holder.id
            else:
                status, signed = ComputerStatus.READY_TO_USE, depot.id
        session.add(
            m.EquipmentItem(
                catalog_number=cat,
                kind=EquipmentKind.COMPUTER,
                status=status.value,
                classification=classification,
                signed_to=signed,
            )
        )
    session.flush()

    # --- Tickets (internal requests) ---
    for _ in range(max(3, num_personnel // 3)):
        ttype = random.choice(list(TicketType))
        requester = random.choice(real_people)
        session.add(
            m.Ticket(
                type=ttype,
                requester_id=requester.id,
                status=random.choice(list(TicketStatus)),
                subject=(
                    "Connect new workstation" if ttype == TicketType.NETWORK_REQUEST
                    else "Draw equipment"
                ),
                description=fake.sentence(),
            )
        )

    # --- Calendars (the three kinds) ---
    guard_cal = m.Calendar(kind=CalendarKind.GUARD, name="Guard Duties")
    adhoc_cal = m.Calendar(kind=CalendarKind.ADHOC, name="AdHoc Missions")
    fmt_cal = m.Calendar(kind=CalendarKind.FORMATTING, name="Formatting")
    session.add_all([guard_cal, adhoc_cal, fmt_cal])
    session.flush()

    # Formatting calendar events
    for cat, sent in formatting_items:
        session.add(
            m.CalendarEvent(
                calendar_id=fmt_cal.id,
                start_date=sent,
                end_date=sent + timedelta(days=FORMATTING_DURATION_DAYS),
                subject_type=CalendarSubjectType.EQUIPMENT_ITEM,
                subject_id=cat,
                label=f"Formatting {cat}",
                status=ComputerStatus.FORMATTING.value,
            )
        )

    # --- Justice table seed (zeroed; counts accumulate from assignments below) ---
    jt: dict[int, m.JusticeTable] = {}
    for p in real_people:
        row = m.JusticeTable(personnel_id=p.id, period_start=YEAR_START)
        jt[p.id] = row
        session.add(row)
    session.flush()

    def is_blocked(person_id: int, start: date, end: date) -> bool:
        return any(bs <= end and start <= be for bs, be in date_blocks[person_id])

    def eligible_for(shift_type: ShiftType, population, rank, start, end) -> m.Personnel | None:
        pool = []
        for p in real_people:
            if not p.active:
                continue
            if population is not None and p.population != population:
                continue
            if rank is not None and p.rank != rank:
                continue
            # HC-GD-6: duty-type flags
            if shift_type == ShiftType.WEEK_LONG and not p.can_do_week_long:
                continue
            if shift_type == ShiftType.SINGLE_DAY and not p.can_do_single_day:
                continue
            if shift_type == ShiftType.SUPPORT and not (p.population == Population.SADIR and p.can_do_support):
                continue
            # HC-GD-3: Keva annual quota
            if p.population == Population.KEVA:
                if shift_type == ShiftType.WEEK_LONG and jt[p.id].week_long_count >= 2:
                    continue
                if shift_type == ShiftType.SINGLE_DAY and jt[p.id].single_day_count >= 4:
                    continue
            # HC-GD-5: not date-blocked over the shift dates
            if is_blocked(p.id, start, end):
                continue
            pool.append(p)
        if not pool:
            return None
        # SC-GD-1: prefer the lowest current burden.
        pool.sort(key=lambda x: jt[x.id].total_burden_points)
        return pool[0]

    # --- Shifts (assigned to lowest-burden eligible person) ---
    num_shifts = num_personnel * 2
    for _ in range(num_shifts):
        stype = random.choices(
            [ShiftType.WEEK_LONG, ShiftType.SINGLE_DAY, ShiftType.SUPPORT],
            weights=[2, 5, 3],
        )[0]
        start = rand_date_in_year(fake)
        if stype == ShiftType.WEEK_LONG:
            end = start + timedelta(days=6)
            tod = None
        else:
            end = start
            tod = random.choice(list(TimeOfDay)) if stype == ShiftType.SINGLE_DAY else None
        # SUPPORT is Sadir-only; sometimes target a population/rank.
        population = Population.SADIR if stype == ShiftType.SUPPORT else (
            random.choice([None, Population.KEVA, Population.SADIR])
        )
        rank = random.choice([None, None, None, *list(Rank)])
        holder = eligible_for(stype, population, rank, start, end)
        shift = m.Shift(
            type=stype,
            time_of_day=tod,
            start_date=start,
            end_date=end,
            eligible_population=population,
            required_rank=rank,
            assigned_to=holder.id if holder else None,
            status=AssignmentStatus.ASSIGNED if holder else AssignmentStatus.OPEN,
        )
        session.add(shift)
        session.flush()
        if holder:
            jt[holder.id].total_burden_points += BURDEN[stype]
            if stype == ShiftType.WEEK_LONG:
                jt[holder.id].week_long_count += 1
            elif stype == ShiftType.SINGLE_DAY:
                jt[holder.id].single_day_count += 1
            session.add(
                m.CalendarEvent(
                    calendar_id=guard_cal.id,
                    start_date=start,
                    end_date=end,
                    subject_type=CalendarSubjectType.SHIFT,
                    subject_id=str(shift.id),
                    label=f"{stype.value} ({holder.full_name})",
                    status=AssignmentStatus.ASSIGNED.value,
                )
            )

    # --- AdHoc missions (0.5 x days) ---
    for _ in range(max(2, num_personnel // 4)):
        days = random.randint(1, 3)
        start = rand_date_in_year(fake)
        end = start + timedelta(days=days - 1)
        pool = [
            p for p in real_people
            if p.active and p.can_do_adhoc and not is_blocked(p.id, start, end)
        ]
        holder = min(pool, key=lambda x: jt[x.id].total_burden_points) if pool else None
        mission = m.AdHocMission(
            title=random.choice(["Memorial ceremony", "Volunteering day", "Branch ceremony"]),
            description=fake.sentence(),
            start_date=start,
            end_date=end,
            days=days,
            assigned_to=holder.id if holder else None,
            status=AssignmentStatus.ASSIGNED if holder else AssignmentStatus.OPEN,
        )
        session.add(mission)
        session.flush()
        if holder:
            jt[holder.id].total_burden_points += 0.5 * days
            session.add(
                m.CalendarEvent(
                    calendar_id=adhoc_cal.id,
                    start_date=start,
                    end_date=end,
                    subject_type=CalendarSubjectType.ADHOC_MISSION,
                    subject_id=str(mission.id),
                    label=f"{mission.title} ({holder.full_name})",
                    status=AssignmentStatus.ASSIGNED.value,
                )
            )


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate random Naatomatic data.")
    parser.add_argument("num_personnel", nargs="?", type=int, default=30,
                        help="how many personnel to create (default 30)")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducibility")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite path (default naatomatic.db)")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)
    fake = Faker()

    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()  # fresh database each run

    engine = get_engine(db_path)
    create_all(engine)
    session = create_session(engine)
    try:
        generate(session, args.num_personnel, fake)
        session.commit()
    finally:
        session.close()

    print(f"Generated database at {db_path} with {args.num_personnel} personnel (+ depot).")


if __name__ == "__main__":
    main()
