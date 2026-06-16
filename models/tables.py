"""SQLAlchemy models — one class per entity table in DESIGN.md (§3-§7).

Conventions:
- Integer surrogate primary keys (``id``) except EquipmentItem, whose natural
  key is ``catalog_number``.
- Enums stored as their string values for human-readable DB inspection.
- ``roles`` is a JSON list of Role values.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.db import Base
from models.enums import (
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
    ShiftType,
    TicketStatus,
    TicketType,
    TimeOfDay,
)


def _enum(py_enum):
    """String-valued Enum column helper (stores .value, not .name)."""
    return Enum(py_enum, values_callable=lambda e: [m.value for m in e], native_enum=False)


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
class Personnel(Base):
    __tablename__ = "personnel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    personal_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String)
    population: Mapped[Population] = mapped_column(_enum(Population))
    rank: Mapped[Rank | None] = mapped_column(_enum(Rank), nullable=True)
    roles: Mapped[list] = mapped_column(JSON, default=list)

    # Duty-type eligibility (HC-GD-6). can_do_support is Sadir-only & course-gated.
    can_do_week_long: Mapped[bool] = mapped_column(Boolean, default=True)
    can_do_single_day: Mapped[bool] = mapped_column(Boolean, default=True)
    can_do_support: Mapped[bool] = mapped_column(Boolean, default=False)
    can_do_adhoc: Mapped[bool] = mapped_column(Boolean, default=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    date_blocks: Mapped[list["PersonnelDateBlock"]] = relationship(
        back_populates="personnel", cascade="all, delete-orphan"
    )


class PersonnelDateBlock(Base):
    """Date-based unavailability (HC-GD-5)."""

    __tablename__ = "personnel_date_block"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    personnel_id: Mapped[int] = mapped_column(ForeignKey("personnel.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)

    personnel: Mapped[Personnel] = relationship(back_populates="date_blocks")


class Ticket(Base):
    """Internal branch request (network / equipment). NOT a SUPPORT shift."""

    __tablename__ = "ticket"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[TicketType] = mapped_column(_enum(TicketType))
    requester_id: Mapped[int] = mapped_column(ForeignKey("personnel.id"))
    status: Mapped[TicketStatus] = mapped_column(_enum(TicketStatus), default=TicketStatus.OPEN)
    subject: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --------------------------------------------------------------------------- #
# Pillar 1 — Network
# --------------------------------------------------------------------------- #
class Switch(Base):
    __tablename__ = "switch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    classification: Mapped[Classification] = mapped_column(_enum(Classification))
    total_ports: Mapped[int] = mapped_column(Integer)

    ports: Mapped[list["Port"]] = relationship(
        back_populates="switch", cascade="all, delete-orphan"
    )


class Port(Base):
    __tablename__ = "port"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    switch_id: Mapped[int] = mapped_column(ForeignKey("switch.id"))
    port_number: Mapped[int] = mapped_column(Integer)
    # classification is derived from switch.classification (single-class switches).
    status: Mapped[PortStatus] = mapped_column(_enum(PortStatus), default=PortStatus.FREE)
    allocated_to: Mapped[int | None] = mapped_column(ForeignKey("personnel.id"), nullable=True)

    switch: Mapped[Switch] = relationship(back_populates="ports")
    wall_jack: Mapped["WallJack | None"] = relationship(back_populates="port", uselist=False)


class WallJack(Base):
    __tablename__ = "wall_jack"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String, unique=True)
    room: Mapped[str | None] = mapped_column(String, nullable=True)
    # classification is derived via port_id -> port.switch.classification.
    port_id: Mapped[int | None] = mapped_column(ForeignKey("port.id"), nullable=True)

    port: Mapped[Port | None] = relationship(back_populates="wall_jack")


# --------------------------------------------------------------------------- #
# Pillar 2 — Logistics
# --------------------------------------------------------------------------- #
class EquipmentItem(Base):
    __tablename__ = "equipment_item"

    catalog_number: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[EquipmentKind] = mapped_column(_enum(EquipmentKind))
    # status string is validated against MonitorStatus/ComputerStatus by kind.
    status: Mapped[str] = mapped_column(String)
    classification: Mapped[Classification | None] = mapped_column(
        _enum(Classification), nullable=True
    )  # computers only
    signed_to: Mapped[int | None] = mapped_column(ForeignKey("personnel.id"), nullable=True)
    # Who the item is promised to while it is at the depot (e.g. during formatting).
    # signed_to = custody (often the depot); reserved_for = destination on return.
    reserved_for: Mapped[int | None] = mapped_column(ForeignKey("personnel.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class EquipmentTransfer(Base):
    __tablename__ = "equipment_transfer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_number: Mapped[str] = mapped_column(ForeignKey("equipment_item.catalog_number"))
    from_personnel: Mapped[int | None] = mapped_column(ForeignKey("personnel.id"), nullable=True)
    to_personnel: Mapped[int | None] = mapped_column(ForeignKey("personnel.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --------------------------------------------------------------------------- #
# Pillar 3 — Guard Duty + AdHoc
# --------------------------------------------------------------------------- #
class Shift(Base):
    __tablename__ = "shift"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[ShiftType] = mapped_column(_enum(ShiftType))
    time_of_day: Mapped[TimeOfDay | None] = mapped_column(_enum(TimeOfDay), nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    eligible_population: Mapped[Population | None] = mapped_column(_enum(Population), nullable=True)
    required_rank: Mapped[Rank | None] = mapped_column(_enum(Rank), nullable=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("personnel.id"), nullable=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        _enum(AssignmentStatus), default=AssignmentStatus.OPEN
    )


class AdHocMission(Base):
    __tablename__ = "adhoc_mission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    days: Mapped[int] = mapped_column(Integer, default=1)
    eligible_population: Mapped[Population | None] = mapped_column(_enum(Population), nullable=True)
    required_rank: Mapped[Rank | None] = mapped_column(_enum(Rank), nullable=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("personnel.id"), nullable=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        _enum(AssignmentStatus), default=AssignmentStatus.OPEN
    )


class JusticeTable(Base):
    """Per-person scheduling tally (calendar year)."""

    __tablename__ = "justice_table"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    personnel_id: Mapped[int] = mapped_column(ForeignKey("personnel.id"), unique=True)
    week_long_count: Mapped[int] = mapped_column(Integer, default=0)
    single_day_count: Mapped[int] = mapped_column(Integer, default=0)
    week_long_carryover: Mapped[int] = mapped_column(Integer, default=0)
    single_day_carryover: Mapped[int] = mapped_column(Integer, default=0)
    total_burden_points: Mapped[float] = mapped_column(Float, default=0.0)
    period_start: Mapped[date] = mapped_column(Date)


# --------------------------------------------------------------------------- #
# Calendars
# --------------------------------------------------------------------------- #
class Calendar(Base):
    __tablename__ = "calendar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[CalendarKind] = mapped_column(_enum(CalendarKind))
    name: Mapped[str] = mapped_column(String)

    events: Mapped[list["CalendarEvent"]] = relationship(
        back_populates="calendar", cascade="all, delete-orphan"
    )


class CalendarEvent(Base):
    __tablename__ = "calendar_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendar.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    subject_type: Mapped[CalendarSubjectType] = mapped_column(_enum(CalendarSubjectType))
    subject_id: Mapped[str] = mapped_column(String)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)

    calendar: Mapped[Calendar] = relationship(back_populates="events")
