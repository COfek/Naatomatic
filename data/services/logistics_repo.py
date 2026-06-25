"""Logistics repository (REFERENCE) — read/write access for equipment.

This is the worked example every pillar's repo should mirror. Add lookups (with
nearest-match suggestions for the did-you-mean rule) and mutations here; keep all
DB writes behind methods like these. Mutations record audit/transfer via the base.
"""

from __future__ import annotations

from sqlalchemy import select

from data.services.base import Repository
from models import tables as t
from models.enums import ComputerStatus, EquipmentKind, MonitorStatus


class LogisticsRepo(Repository):
    # --- lookups ------------------------------------------------------------
    def get_equipment(self, catalog_number: str) -> t.EquipmentItem | None:
        return self.session.get(t.EquipmentItem, catalog_number)

    def get_personnel(self, personnel_id: int) -> t.Personnel | None:
        return self.session.get(t.Personnel, personnel_id)

    def nearest_catalog_numbers(self, typed: str, limit: int = 5) -> list[str]:
        """Did-you-mean candidates for a mistyped catalog number (prefix match)."""
        rows = self.session.scalars(
            select(t.EquipmentItem.catalog_number)
            .where(t.EquipmentItem.catalog_number.like(f"%{typed[-4:]}%"))
            .limit(limit)
        ).all()
        return list(rows)

    def monitors_signed_to(self, personnel_id: int) -> list[t.EquipmentItem]:
        return list(self.session.scalars(
            select(t.EquipmentItem).where(
                t.EquipmentItem.kind == EquipmentKind.MONITOR,
                t.EquipmentItem.signed_to == personnel_id,
            )
        ).all())

    def get_personnel_by_personal_number(self, personal_number: str) -> t.Personnel | None:
        return self.session.scalar(
            select(t.Personnel).where(t.Personnel.personal_number == personal_number)
        )

    # --- mutations (apply only; the tool validates + commits) ---------------
    def sign_to(self, item: t.EquipmentItem, personnel_id: int) -> None:
        """Apply: hand `item` to a person. Computers go IN_USE; clears reservation.
        Does NOT commit — the tool validates then commits/rolls back."""
        item.signed_to = personnel_id
        item.reserved_for = None
        if item.kind == EquipmentKind.COMPUTER:
            item.status = ComputerStatus.IN_USE.value
        item.handover_pending = True  # Kitbag acceptance still required
