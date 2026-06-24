"""General Knowledge domain tools — STUBS. All READ-ONLY (no MUTATING).
Serves knowledge/ docs + live DB reads. Strictly self-only for personal data.
"""

from __future__ import annotations
from tools.base import ToolContext, ToolOutput
from pathlib import Path

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
def get_branch_structure(ctx: ToolContext, *, filter: str | None = None) -> ToolOutput[dict]:
    """The department->team tree with leaders + contacts (formatted org tree). Shared info."""
    raise NotImplementedError

def get_my_details(ctx: ToolContext) -> ToolOutput[dict]:
    """Comprehensive SELF-ONLY view: details, equipment + history, past/future shifts,
    network, readiness, justice standing, date-blocks. Refuse requests about other users."""
    raise NotImplementedError

def get_shift_readiness(ctx: ToolContext) -> ToolOutput[dict]:
    """Range-qualification status + renewal steps/links (HC-GD-9), for the caller."""
    raise NotImplementedError

def get_resource(ctx: ToolContext, *, name: str) -> ToolOutput[dict]:
    """Serve a file/link (weapon-carry file, SmartBase tests/weapon-form, Kitbag)."""
    raise NotImplementedError


TOOLS = (explain,)  # add the rest back here as each one gets implemented
MUTATING: set[str] = set()  # read-only domain
