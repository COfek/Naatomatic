"""Shared enumerations for the CombatAI domain.

These mirror the enums defined in DESIGN.md (§3-§7). Stored as strings in the
database for readability when inspecting the SQLite file directly.
"""

from __future__ import annotations

import enum


class Population(str, enum.Enum):
    KEVA = "KEVA"
    SADIR = "SADIR"


class Rank(str, enum.Enum):
    LIEUTENANT = "LIEUTENANT"
    CAPTAIN = "CAPTAIN"
    MAJOR = "MAJOR"


class Role(str, enum.Enum):
    NETWORK_MANAGER = "NETWORK_MANAGER"
    LOGISTICS_OFFICER = "LOGISTICS_OFFICER"
    SHIFT_MANAGER = "SHIFT_MANAGER"


class Classification(str, enum.Enum):
    CIVILIAN = "CIVILIAN"
    GLOBAL = "GLOBAL"
    SECRET = "SECRET"
    TOP_SECRET = "TOP_SECRET"


# --- Tickets (internal branch requests) ---
class TicketType(str, enum.Enum):
    NETWORK_REQUEST = "NETWORK_REQUEST"
    EQUIPMENT_REQUEST = "EQUIPMENT_REQUEST"


class TicketStatus(str, enum.Enum):
    OPEN = "OPEN"
    ON_HOLD = "ON_HOLD"
    RESOLVED = "RESOLVED"


class DateBlockStatus(str, enum.Enum):
    """A soldier-submitted constraint needs SHIFT_MANAGER approval before it takes effect."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"  # only APPROVED blocks count for HC-GD-5
    REJECTED = "REJECTED"


class ConstraintLevel(str, enum.Enum):
    """Priority of a constraint. CRITICAL is never overridden (hard); the rest are
    soft — overridden lowest-first only as a last resort to fill a duty (SC-GD-5)."""
    CRITICAL = "CRITICAL"  # e.g. close-family wedding/funeral, medical — never overridden
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# --- Network ---
class PortStatus(str, enum.Enum):
    DISCONNECTED = "DISCONNECTED"  # not wired to a wall jack / available
    CONNECTED = "CONNECTED"        # wired to a wall jack and allocated to a person


# --- Equipment ---
class EquipmentKind(str, enum.Enum):
    MONITOR = "MONITOR"
    COMPUTER = "COMPUTER"


class MonitorStatus(str, enum.Enum):
    FUNCTIONAL = "FUNCTIONAL"
    BROKEN = "BROKEN"
    DECOMMISSIONED = "DECOMMISSIONED"  # out of service, removed from the branch (terminal)


class ComputerStatus(str, enum.Enum):
    FORMATTING = "FORMATTING"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    READY_TO_USE = "READY_TO_USE"
    IN_USE = "IN_USE"
    BROKEN = "BROKEN"
    DECOMMISSIONED = "DECOMMISSIONED"  # IT couldn't fix it; removed from the branch (terminal)


# --- Guard duty / scheduling ---
class ShiftType(str, enum.Enum):
    WEEK_LONG = "WEEK_LONG"
    SINGLE_DAY = "SINGLE_DAY"
    SUPPORT = "SUPPORT"  # customer-support standby; Sadir-only


class TimeOfDay(str, enum.Enum):
    DAY = "DAY"
    NIGHT = "NIGHT"


class AssignmentStatus(str, enum.Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# --- Calendars ---
class CalendarKind(str, enum.Enum):
    GUARD = "GUARD"
    ADHOC = "ADHOC"
    FORMATTING = "FORMATTING"


class CalendarSubjectType(str, enum.Enum):
    SHIFT = "SHIFT"
    ADHOC_MISSION = "ADHOC_MISSION"
    EQUIPMENT_ITEM = "EQUIPMENT_ITEM"


# --- Org structure (General Knowledge agent) ---
class OrgUnitKind(str, enum.Enum):
    DEPARTMENT = "DEPARTMENT"
    TEAM = "TEAM"


# --- Domain constants ---
DEPOT_PERSONAL_NUMBER = "1234567"  # reserved holder for broken/formatting items
FORMATTING_DURATION_DAYS = 14
RANGE_QUAL_VALID_DAYS = 183  # shooting-range qualification valid ~6 months (HC-GD-9)
SMARTBASE_TEST_URL = "https://smartbase.example.mil/weapon-safety-test"  # placeholder
