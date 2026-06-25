"""General Knowledge domain tools — STUBS. All READ-ONLY (no MUTATING).
Serves knowledge/ docs + live DB reads. Strictly self-only for personal data.
"""

from __future__ import annotations
from tools.base import ToolContext, ToolOutput
from pathlib import Path
from models.enums import OrgUnitKind
from services.general_knowledge_repo import GeneralKnowledgeRepo

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


def explain(ctx: ToolContext, *, topic: str) -> ToolOutput[dict]:
    """Return a specific knowledge/ doc by its id (filename without .md), e.g.
    '02-open-closed-networks'. Valid ids and what each covers are listed in the
    system prompt's knowledge index. Says so if the id doesn't exist (no fabrication)."""
    docs = sorted(p for p in KNOWLEDGE_DIR.glob("*.md") if p.stem != "README")
    needle = topic.strip().lower()
    matches = [p for p in docs if p.stem.lower() == needle] or \
              [p for p in docs if needle in p.stem.lower()]
    if not matches:
        return ToolOutput.err(
            f"No knowledge doc with id '{topic}'.",
            suggestions=[p.stem for p in docs],
        )
    doc = matches[0]
    return ToolOutput.of({"doc": doc.stem, "content": doc.read_text(encoding="utf-8")})


def _leader_contact(repo: GeneralKnowledgeRepo, leader_id: int | None) -> dict | None:
    if leader_id is None:
        return None
    leader = repo.get_personnel(leader_id)
    if leader is None:
        return None
    return {"name": leader.full_name, "phone": leader.phone, "email": leader.email}


def _format_unit(repo: GeneralKnowledgeRepo, unit) -> dict:
    out = {
        "name": unit.name,
        "kind": unit.kind.value,
        "leader": _leader_contact(repo, unit.leader_id),
        "contact_note": unit.contact_note,
    }
    if unit.kind == OrgUnitKind.DEPARTMENT:
        out["teams"] = [_format_unit(repo, c) for c in repo.children(unit.id)]
    else:  # TEAM
        out["members"] = [
            {"name": m.full_name, "rank": m.rank.value if m.rank else None}
            for m in repo.team_members(unit.id)
        ]
    return out


def _format_person_placement(repo: GeneralKnowledgeRepo, ctx: ToolContext, person) -> dict:
    team = repo.get_org_unit(person.team_id) if person.team_id else None
    dept = repo.get_org_unit(team.parent_id) if team and team.parent_id else None
    out = {
        "name": person.full_name,
        "rank": person.rank.value if person.rank else None,
        "population": person.population.value,
        "team": team.name if team else None,
        "department": dept.name if dept else None,
        "team_leader": _leader_contact(repo, team.leader_id) if team else None,
    }
    if ctx.actor_personal_number == person.personal_number:
        out["phone"] = person.phone
        out["email"] = person.email
        out["note"] = "This is you — use get_my_details for your full record."
    return out


def get_branch_structure(ctx: ToolContext, *, query: str | None = None) -> ToolOutput[dict]:
    """Org lookup: with no query, the full department->team tree (leaders + contacts).
    With a query, resolves it as a person's name (-> their team/department + team
    leader's contact) or a unit's name (-> its sub-teams or member roster). Shared
    structural info — does not expose another person's private data (self-only
    fields are added when the query matches the caller). Did-you-mean on no match."""
    repo = GeneralKnowledgeRepo(ctx.session)

    if not query:
        return ToolOutput.of({"departments": [_format_unit(repo, d) for d in repo.departments()]})

    people = repo.find_personnel_by_name(query)
    if len(people) == 1:
        return ToolOutput.of(_format_person_placement(repo, ctx, people[0]))
    if len(people) > 1:
        return ToolOutput.err(
            f"Multiple personnel match '{query}'.",
            suggestions=[p.full_name for p in people[:5]],
        )

    units = repo.find_org_unit_by_name(query)
    if len(units) == 1:
        return ToolOutput.of(_format_unit(repo, units[0]))
    if len(units) > 1:
        return ToolOutput.err(
            f"Multiple units match '{query}'.",
            suggestions=[u.name for u in units[:5]],
        )

    return ToolOutput.err(
        f"No person or unit matching '{query}'.",
        suggestions=repo.nearest_names(query),
    )

TOOLS = (explain, get_branch_structure)  # add the rest back here as each one gets implemented
MUTATING: set[str] = set()  # read-only domain
