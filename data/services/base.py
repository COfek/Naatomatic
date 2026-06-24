"""Repository base — the ONLY layer that writes the database.

Every pillar gets a repository (e.g. `LogisticsRepo`) that subclasses `Repository`.
Tools never touch the session directly except through a repo. The base provides:

- a held `session`,
- `audit(...)` — write an AuditLog row (call on every mutation; satisfies R2-9),
- `transfer(...)` — write an EquipmentTransfer row (equipment moves),
- `validate(checks)` — run constraint-engine checks against the *pending* session
  state and return violations (used for the apply → validate → commit/rollback
  pattern; see the Logistics reference tool),
- `commit()` / `rollback()`.

Pattern for a mutating action (copy this shape in every mutating tool):

    repo = SomeRepo(ctx.session)
    # 1. look up entities (return ToolResult.err with suggestions if not found)
    # 2. apply the proposed change to the ORM objects, then session.flush()
    # 3. violations = repo.validate([check_fn, ...]); if violations: rollback + err
    # 4. repo.transfer(...) / repo.audit(...)
    # 5. repo.commit(); return ToolResult.of(...)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy.orm import Session

from models import tables as t


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- write helpers (history) -------------------------------------------
    def audit(self, *, actor: str | None, action: str, entity_type: str,
              entity_id: str, before: dict | None = None, after: dict | None = None) -> None:
        """Append an AuditLog row. Call for every mutation (R2-9)."""
        self.session.add(t.AuditLog(
            actor=actor, action=action, entity_type=entity_type,
            entity_id=str(entity_id), before=before, after=after,
        ))

    def transfer(self, *, catalog_number: str, from_personnel: int | None,
                 to_personnel: int | None, reason: str) -> None:
        """Append an EquipmentTransfer row (equipment custody move)."""
        self.session.add(t.EquipmentTransfer(
            catalog_number=catalog_number, from_personnel=from_personnel,
            to_personnel=to_personnel, reason=reason,
        ))

    # --- validation gate ----------------------------------------------------
    def validate(self, checks: Iterable[Callable[[Session], list[str]]]) -> list[str]:
        """Flush pending changes, run the given constraint checks, return all
        violations (empty = OK). Caller decides commit vs rollback."""
        self.session.flush()
        violations: list[str] = []
        for check in checks:
            violations.extend(check(self.session))
        return violations

    # --- transaction --------------------------------------------------------
    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
