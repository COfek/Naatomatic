"""General Knowledge pillar tools — STUBS. All READ-ONLY (no MUTATING).
Serves knowledge/ docs + live DB reads. Strictly self-only for personal data.
"""

from __future__ import annotations

from tools.base import ToolContext, ToolOutput


def explain(ctx: ToolContext, *, topic: str) -> ToolOutput[dict]:
    """Retrieve + return a knowledge/ doc or a system mechanic. Says so if unknown
    (no fabrication)."""
    raise NotImplementedError

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


TOOLS = (explain, get_branch_structure, get_my_details, get_shift_readiness, get_resource)
MUTATING: set[str] = set()  # read-only pillar
