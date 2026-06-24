"""Router node. Classifies the user's intent into a domain, then seeds the Worker's
transcript with a system prompt scoped to that domain (DESIGN §2).

Only `general_knowledge` has real tools today — widen the Literal below as
network/logistics/guard_duty/adhoc get built."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from agents.state import GraphState

from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"

class _DomainChoice(BaseModel):
    domain: Literal["general_knowledge"]

def _knowledge_index() -> str:
    return (KNOWLEDGE_DIR / "README.md").read_text(encoding="utf-8")

ROUTER_PROMPT = (
    "You classify a user's message into the Naatomatic domain that should handle it. "
    "Only 'general_knowledge' exists right now. Pick it."
)

WORKER_SYSTEM_PROMPT = (
    "You are the Naatomatic {domain} assistant. Answer ONLY using information "
    "returned by your tools — never use your own general knowledge about networks, "
    "procedures, or policies, even if you think you know the answer. To look "
    "something up, call `explain` with the exact doc id (filename without .md, e.g. "
    "'02-open-closed-networks') — pick the doc whose 'Covers' column below matches "
    "the user's question. If a tool returns an error or no match, tell the user that "
    "plainly and relay any suggested ids instead of guessing. Never invent a value "
    "the user didn't give you — ask a follow-up question instead. Reply in the same "
    "language the user wrote in (Hebrew or English).\n\n"
    "{knowledge_index}"
)


def run(state: GraphState) -> GraphState:
    runtime = state["runtime"]
    choice: _DomainChoice = runtime.llm.call_structured_output(
        messages=[
            SystemMessage(content=ROUTER_PROMPT),
            HumanMessage(content=state["user_message"]),
        ],
        schema=_DomainChoice,
    )
    state["domain"] = choice.domain
    state["messages"] = [
        SystemMessage(content=WORKER_SYSTEM_PROMPT.format(
            domain=choice.domain, knowledge_index=_knowledge_index(),
        )),
        HumanMessage(content=state["user_message"]),
    ]
    return state