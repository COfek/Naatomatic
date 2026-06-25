"""General Knowledge repository — read-only lookups for org structure + personnel.

Mirrors LogisticsRepo's shape (data/services/logistics_repo.py) but keyed by name
since this domain is queried by what a person types, not by id.
"""

from __future__ import annotations

import difflib

from sqlalchemy import func, select

from data.services.base import Repository
from models import tables as t
from models.enums import OrgUnitKind


class GeneralKnowledgeRepo(Repository):
    # --- personnel ------------------------------------------------------
    def get_personnel(self, personnel_id: int) -> t.Personnel | None:
        return self.session.get(t.Personnel, personnel_id)

    def find_personnel_by_name(self, name: str) -> list[t.Personnel]:
        needle = name.strip().lower()
        return list(self.session.scalars(
            select(t.Personnel).where(func.lower(t.Personnel.full_name).like(f"%{needle}%"))
        ).all())

    def all_personnel_names(self) -> list[str]:
        return list(self.session.scalars(select(t.Personnel.full_name)).all())

    # --- org units --------------------------------------------------------
    def get_org_unit(self, unit_id: int) -> t.OrgUnit | None:
        return self.session.get(t.OrgUnit, unit_id)

    def find_org_unit_by_name(self, name: str) -> list[t.OrgUnit]:
        needle = name.strip().lower()
        return list(self.session.scalars(
            select(t.OrgUnit).where(func.lower(t.OrgUnit.name).like(f"%{needle}%"))
        ).all())

    def all_org_unit_names(self) -> list[str]:
        return list(self.session.scalars(select(t.OrgUnit.name)).all())

    def departments(self) -> list[t.OrgUnit]:
        return list(self.session.scalars(
            select(t.OrgUnit).where(t.OrgUnit.kind == OrgUnitKind.DEPARTMENT)
        ).all())

    def children(self, unit_id: int) -> list[t.OrgUnit]:
        return list(self.session.scalars(
            select(t.OrgUnit).where(t.OrgUnit.parent_id == unit_id)
        ).all())

    def team_members(self, team_id: int) -> list[t.Personnel]:
        return list(self.session.scalars(
            select(t.Personnel).where(t.Personnel.team_id == team_id, t.Personnel.active.is_(True))
        ).all())

    # --- did-you-mean -------------------------------------------------------
    def nearest_names(self, typed: str, limit: int = 5) -> list[str]:
        pool = self.all_personnel_names() + self.all_org_unit_names()
        return difflib.get_close_matches(typed, pool, n=limit, cutoff=0.4)