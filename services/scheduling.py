"""Shared Scheduling Service for Guard Duty and AdHoc domains.

Provides the core engine for evaluating eligibility, ranking personnel by fairness
(burden points / quotas), handling date block constraints, and tie-breaking.
"""

from __future__ import annotations

import datetime
from typing import Any, Literal

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from models import tables as t
from models.enums import (
    AssignmentStatus,
    ConstraintLevel,
    DateBlockStatus,
    Population,
    RANGE_QUAL_VALID_DAYS,
    Rank,
    ShiftType,
)


def _dates_overlap(a_start: datetime.date, a_end: datetime.date, b_start: datetime.date, b_end: datetime.date) -> bool:
    return a_start <= b_end and b_start <= a_end


class SchedulingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def recommend_assignment(
        self,
        *,
        start_date: datetime.date,
        end_date: datetime.date,
        duty_type: ShiftType | Literal["ADHOC"],
        eligible_population: Population | None = None,
        required_rank: Rank | None = None,
    ) -> dict[str, Any]:
        """
        Determines the best primary and reserve candidates for the given duty.
        Returns:
            {
                "primary_id": int | None,
                "reserve_id": int | None,
                "warnings": list[str]  # e.g., if soft constraints were overridden
            }
        """
        candidates = self._get_eligible_candidates(
            start_date=start_date,
            end_date=end_date,
            duty_type=duty_type,
            eligible_population=eligible_population,
            required_rank=required_rank,
        )

        if not candidates:
            return {"primary_id": None, "reserve_id": None, "warnings": []}

        # 2. Constraint Tiering (Soft Constraints)
        # Tiers: None < LOW < MEDIUM < HIGH
        tiers = {
            None: [],
            ConstraintLevel.LOW: [],
            ConstraintLevel.MEDIUM: [],
            ConstraintLevel.HIGH: [],
        }
        
        for person_id, data in candidates.items():
            max_level = None
            for block in data["date_blocks"]:
                # Only approved blocks matter, CRITICAL was already filtered out
                if block.status == DateBlockStatus.APPROVED and _dates_overlap(start_date, end_date, block.start_date, block.end_date):
                    # We only care about soft levels here
                    if block.level != ConstraintLevel.CRITICAL:
                        if max_level is None or block.level.value > max_level.value: # Assuming string values sort correctly, but better to check manually
                            # Actually, ConstraintLevel enum values might not sort alphabetically by severity.
                            # Let's map them explicitly.
                            pass
            
            # Helper to map level to an integer for sorting
            level_weights = {
                None: 0,
                ConstraintLevel.LOW: 1,
                ConstraintLevel.MEDIUM: 2,
                ConstraintLevel.HIGH: 3,
            }
            
            best_weight = 0
            best_level = None
            for block in data["date_blocks"]:
                if block.status == DateBlockStatus.APPROVED and _dates_overlap(start_date, end_date, block.start_date, block.end_date):
                    if block.level in level_weights and level_weights[block.level] > best_weight:
                        best_weight = level_weights[block.level]
                        best_level = block.level
            
            tiers[best_level].append(data)

        # Iterate through tiers to find candidates
        ordered_tiers = [None, ConstraintLevel.LOW, ConstraintLevel.MEDIUM, ConstraintLevel.HIGH]
        selected_primary = None
        selected_reserve = None
        warnings = []

        # We will flatten and rank all candidates in the best available tier.
        for tier_level in ordered_tiers:
            tier_candidates = tiers[tier_level]
            if not tier_candidates:
                continue
            
            # Rank candidates within this tier
            ranked = self._rank_candidates(tier_candidates, duty_type)
            if not ranked:
                continue

            if not selected_primary:
                selected_primary = ranked[0]
                if tier_level is not None:
                    warnings.append(f"Primary assignee (ID: {selected_primary['personnel'].id}) has an overridden {tier_level.value} constraint.")
                
            if duty_type != "ADHOC" and not selected_reserve and len(ranked) > 1:
                # We need a reserve, and we haven't found one yet
                for c in ranked[1:]:
                    if c["personnel"].id != selected_primary["personnel"].id:
                        selected_reserve = c
                        if tier_level is not None:
                            warnings.append(f"Reserve assignee (ID: {selected_reserve['personnel'].id}) has an overridden {tier_level.value} constraint.")
                        break

            # If we need a reserve but didn't find one in this tier, we continue to the next tier for the reserve
            if duty_type != "ADHOC" and selected_primary and not selected_reserve:
                continue

            if selected_primary and (duty_type == "ADHOC" or selected_reserve):
                break

        return {
            "primary_id": selected_primary["personnel"].id if selected_primary else None,
            "reserve_id": selected_reserve["personnel"].id if selected_reserve else None,
            "warnings": warnings,
        }

    def _get_eligible_candidates(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        duty_type: ShiftType | Literal["ADHOC"],
        eligible_population: Population | None,
        required_rank: Rank | None,
    ) -> dict[int, dict[str, Any]]:
        query = select(t.Personnel).where(t.Personnel.active == True)
        if eligible_population:
            query = query.where(t.Personnel.population == eligible_population)
        if required_rank:
            query = query.where(t.Personnel.rank == required_rank)

        personnel_list = self.session.scalars(query).all()
        personnel_dict = {p.id: p for p in personnel_list}

        # Load date blocks
        blocks = self.session.scalars(
            select(t.PersonnelDateBlock).where(
                t.PersonnelDateBlock.personnel_id.in_(list(personnel_dict.keys())),
                t.PersonnelDateBlock.status == DateBlockStatus.APPROVED
            )
        ).all()
        blocks_by_person = {pid: [] for pid in personnel_dict}
        for b in blocks:
            blocks_by_person[b.personnel_id].append(b)

        # Load justice tables
        jt_list = self.session.scalars(
            select(t.JusticeTable).where(t.JusticeTable.personnel_id.in_(list(personnel_dict.keys())))
        ).all()
        jt_by_person = {jt.personnel_id: jt for jt in jt_list}

        # Load active assignments (to check overlaps HC-GD-7)
        active_shifts = self.session.scalars(
            select(t.Shift).where(
                t.Shift.assigned_to.is_not(None),
                t.Shift.status.in_([AssignmentStatus.OPEN, AssignmentStatus.ASSIGNED])
            )
        ).all()
        active_adhocs = self.session.scalars(
            select(t.AdHocMission).where(
                t.AdHocMission.assigned_to.is_not(None),
                t.AdHocMission.status.in_([AssignmentStatus.OPEN, AssignmentStatus.ASSIGNED])
            )
        ).all()

        assignments_by_person = {pid: [] for pid in personnel_dict}
        for s in active_shifts:
            if s.assigned_to in assignments_by_person:
                assignments_by_person[s.assigned_to].append((s.start_date, s.end_date, s.type))
        for a in active_adhocs:
            if a.assigned_to in assignments_by_person:
                assignments_by_person[a.assigned_to].append((a.start_date, a.end_date, "ADHOC"))

        # Pre-calculate last assignment dates for tie-breaking
        # "of that kind" evaluated at pool level (Shifts pool vs Support pool)
        # Shifts pool: WEEK_LONG, SINGLE_DAY, ADHOC
        # Support pool: SUPPORT
        last_assignment_shifts_pool = {pid: datetime.date.min for pid in personnel_dict}
        last_assignment_support_pool = {pid: datetime.date.min for pid in personnel_dict}
        
        # We also need completed/past assignments to find the true "last"
        all_shifts = self.session.scalars(select(t.Shift).where(t.Shift.assigned_to.is_not(None))).all()
        all_adhocs = self.session.scalars(select(t.AdHocMission).where(t.AdHocMission.assigned_to.is_not(None))).all()
        for s in all_shifts:
            if s.assigned_to in personnel_dict:
                if s.type == ShiftType.SUPPORT:
                    if s.end_date > last_assignment_support_pool[s.assigned_to]:
                        last_assignment_support_pool[s.assigned_to] = s.end_date
                else:
                    if s.end_date > last_assignment_shifts_pool[s.assigned_to]:
                        last_assignment_shifts_pool[s.assigned_to] = s.end_date
        for a in all_adhocs:
            if a.assigned_to in personnel_dict:
                if a.end_date > last_assignment_shifts_pool[a.assigned_to]:
                    last_assignment_shifts_pool[a.assigned_to] = a.end_date

        candidates = {}
        for pid, p in personnel_dict.items():
            # HC-GD-6: Duty-type flags
            if duty_type == "ADHOC" and not p.can_do_adhoc:
                continue
            elif duty_type == ShiftType.WEEK_LONG and not p.can_do_week_long:
                continue
            elif duty_type == ShiftType.SINGLE_DAY and not p.can_do_single_day:
                continue
            elif duty_type == ShiftType.SUPPORT and not (p.population == Population.SADIR and p.can_do_support):
                continue

            # HC-GD-9: Range qualification for armed guard shifts
            if duty_type in (ShiftType.WEEK_LONG, ShiftType.SINGLE_DAY):
                if p.last_range_qualification is None:
                    continue
                cutoff = datetime.date.today() - datetime.timedelta(days=RANGE_QUAL_VALID_DAYS)
                if p.last_range_qualification < cutoff:
                    continue

            # HC-GD-7: Overlapping assignments
            overlap = False
            for a_start, a_end, _ in assignments_by_person[pid]:
                if _dates_overlap(start_date, end_date, a_start, a_end):
                    overlap = True
                    break
            if overlap:
                continue

            # HC-GD-5: CRITICAL date blocks
            critical_overlap = False
            for b in blocks_by_person[pid]:
                if b.level == ConstraintLevel.CRITICAL and _dates_overlap(start_date, end_date, b.start_date, b.end_date):
                    critical_overlap = True
                    break
            if critical_overlap:
                continue
            
            # Keva Quota Limits (HC-GD-3)
            # Effective requirement = base quota - carryover. Exclude if done >= effective
            if p.population == Population.KEVA and duty_type in (ShiftType.WEEK_LONG, ShiftType.SINGLE_DAY):
                jt = jt_by_person.get(pid)
                if jt:
                    if duty_type == ShiftType.WEEK_LONG:
                        effective_req = 2 - jt.week_long_carryover
                        if jt.week_long_count >= effective_req:
                            continue
                    elif duty_type == ShiftType.SINGLE_DAY:
                        effective_req = 4 - jt.single_day_carryover
                        if jt.single_day_count >= effective_req:
                            continue

            candidates[pid] = {
                "personnel": p,
                "justice_table": jt_by_person.get(pid),
                "date_blocks": blocks_by_person[pid],
                "last_shifts_pool": last_assignment_shifts_pool[pid],
                "last_support_pool": last_assignment_support_pool[pid],
            }

        return candidates

    def _rank_candidates(self, tier_candidates: list[dict[str, Any]], duty_type: ShiftType | Literal["ADHOC"]) -> list[dict[str, Any]]:
        # Separate Keva and Sadir
        keva = [c for c in tier_candidates if c["personnel"].population == Population.KEVA]
        sadir = [c for c in tier_candidates if c["personnel"].population == Population.SADIR]

        # Rank Keva (for Shifts, ad-hoc tie break uses shifts pool points)
        # Sort Keva by fewer completed shifts of that type, then by last assignment
        def keva_sort_key(c):
            jt = c["justice_table"]
            if duty_type == ShiftType.WEEK_LONG:
                count = jt.week_long_count if jt else 0
                return (count, c["last_shifts_pool"])
            elif duty_type == ShiftType.SINGLE_DAY:
                count = jt.single_day_count if jt else 0
                return (count, c["last_shifts_pool"])
            else: # ADHOC
                points = jt.shifts_burden_points if jt else 0.0
                return (points, c["last_shifts_pool"])

        keva.sort(key=keva_sort_key)

        # Rank Sadir
        def sadir_sort_key(c):
            jt = c["justice_table"]
            if duty_type == ShiftType.SUPPORT:
                points = jt.support_burden_points if jt else 0.0
                return (points, c["last_support_pool"])
            else:
                points = jt.shifts_burden_points if jt else 0.0
                return (points, c["last_shifts_pool"])
                
        sadir.sort(key=sadir_sort_key)

        # The pool to draw from first depends on population targeting. 
        # But if population is mixed, who comes first?
        # Usually assignments are targeted by population. If not, we merge them 
        # based on points? Wait, Keva and Sadir are balanced differently.
        # Let's put Sadir first for Adhoc, but really if population=None, Sadir handles the bulk.
        # Actually we just concatenate Keva then Sadir or vice versa. 
        # It's usually targeted. If it's not, let's prefer Sadir for AdHoc, or just return Sadir + Keva.
        return sadir + keva
