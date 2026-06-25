"""Router node. Classifies the user's intent into a domain, then seeds the Worker's
transcript with a system prompt scoped to that domain (DESIGN §2)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from agents.state import GraphState

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"

_DOMAIN_DESCRIPTIONS = {
    "general_knowledge": (
        "questions about branch procedures, eligibility, system mechanics, "
        "the knowledge base, or a person's own details"
    ),
    "network": (
        "questions about network connections, wall jacks, classified/open networks, "
        "port status, or connectivity issues"
    ),
    "logistics": (
        "questions about equipment (computers, monitors), sign-out/return, "
        "inventory status, or logistics tickets"
    ),
    "guard_duty": (
        "questions about guard duty shifts, the Justice Table, date-block "
        "constraints, or the support roster"
    ),
    "adhoc": (
        "sudden one-off missions such as ceremonies, memorials, or volunteering "
        "that don't fit any other domain"
    ),
    "tickets": (
        "requests to open a service ticket, check ticket status, or list own tickets "
        "(equipment, network, or guard duty)"
    ),
}

ROUTER_PROMPT = (
    "You classify the user's message into exactly one Naatomatic domain.\n\n"
    + "\n".join(f"- {d}: {desc}" for d, desc in _DOMAIN_DESCRIPTIONS.items())
    + "\n\nRespond with the single most relevant domain name."
)


class _DomainChoice(BaseModel):
    domain: Literal["general_knowledge", "network", "logistics", "guard_duty", "adhoc", "tickets"]


def _system_prompt_for(domain: str) -> str:
    config = importlib.import_module(f"agents.domains.{domain}.config")
    prompt = config.PROMPT
    if domain == "general_knowledge":
        index_path = KNOWLEDGE_DIR / "README.md"
        if index_path.exists():
            prompt = prompt + "\n\n" + index_path.read_text(encoding="utf-8")
    return prompt


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
        SystemMessage(content=_system_prompt_for(choice.domain)),
        HumanMessage(content=state["user_message"]),
    ]
    return state