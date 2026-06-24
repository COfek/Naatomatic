"""Authentication + the per-call ToolContext.

Login is by personal number alone (local deployment; DESIGN §9). This module turns
a personal number into a `ToolContext` carrying the actor's roles, which tools use
to gate manager-only actions.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import tables as t
from tools.base import ToolContext


def authenticate(session: Session, personal_number: str) -> ToolContext | None:
    """Return a ToolContext for the given personal number, or None if not found
    (or inactive)."""
    person = session.scalar(
        select(t.Personnel).where(t.Personnel.personal_number == personal_number)
    )
    if person is None or not person.active:
        return None
    return ToolContext(
        session=session,
        actor_personal_number=person.personal_number,
        roles=list(person.roles or []),
    )
