"""Ticket tools — shared across all domains (network, logistics, guard_duty).

These cover the generic ticket lifecycle: create, list, get status. Resolution
tools (resolve_equipment_ticket, resolve_network_ticket) stay in their domain
files because they perform domain-specific actions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from data.services.ticket_repo import TicketRepo
from models.enums import TicketStatus, TicketType
from tools.base import ToolContext, ToolOutput


class CreateTicketArgs(BaseModel):
    ticket_type: Literal["NETWORK_REQUEST", "EQUIPMENT_REQUEST", "GUARD_DUTY_REQUEST"] = Field(
        description="Domain of the ticket."
    )
    description: str | None = Field(
        default=None,
        description="Optional free-text details or justification.",
    )
    payload: dict = Field(
        description=(
            "Domain-specific data for the ticket. Required keys by type:\n"
            "  EQUIPMENT_REQUEST: {\"kind\": \"MONITOR\"|\"COMPUTER\", "
            "\"classification\": \"CIVILIAN\"|\"GLOBAL\"|\"SECRET\"|\"TOP_SECRET\" (computers only)}.\n"
            "  NETWORK_REQUEST: {\"wall_jack_id\": <int>, "
            "\"desired_classification\": \"CIVILIAN\"|\"GLOBAL\"|\"SECRET\"|\"TOP_SECRET\"}.\n"
            "  GUARD_DUTY_REQUEST: {\"shift_id\": <int>|null, \"reason\": <str>, "
            "\"request_type\": \"SWAP_REQUEST\"|\"EXEMPTION\"|\"OTHER\"}."
        )
    )


def create_ticket(ctx: ToolContext, args: CreateTicketArgs) -> ToolOutput[dict]:
    """Open a service ticket on behalf of the authenticated user.

    Any authenticated user may open a ticket. The ticket type determines which
    domain manager will process it. Ask for missing payload fields; never guess.
    """
    if ctx.actor_personal_number is None:
        return ToolOutput.err("No authenticated user — cannot open a ticket.")

    repo = TicketRepo(ctx.session)

    requester = repo.get_personnel_by_personal_number(ctx.actor_personal_number)
    if requester is None:
        return ToolOutput.err(f"No personnel record for personal number {ctx.actor_personal_number}.")

    ticket_type = TicketType(args.ticket_type)
    subject = _build_subject(ticket_type, args.payload)

    ticket = repo.create_ticket(
        type=ticket_type,
        requester_id=requester.id,
        subject=subject,
        description=args.description,
        payload=args.payload,
    )

    repo.audit(
        actor=ctx.actor_personal_number,
        action="create_ticket",
        entity_type="ticket",
        entity_id=str(ticket.id),
        before=None,
        after={"status": TicketStatus.OPEN.value, "type": args.ticket_type,
               "subject": subject, "requester_id": requester.id},
    )
    repo.commit()

    return ToolOutput.of({
        "ticket_id": ticket.id,
        "type": args.ticket_type,
        "status": TicketStatus.OPEN.value,
        "subject": subject,
        "note": "Ticket opened. The relevant manager will review and process it.",
    })


def _build_subject(ticket_type: TicketType, payload: dict) -> str:
    if ticket_type == TicketType.EQUIPMENT_REQUEST:
        kind = payload.get("kind", "equipment")
        classification = payload.get("classification")
        return f"{kind} request" + (f" ({classification})" if classification else "")
    if ticket_type == TicketType.NETWORK_REQUEST:
        classification = payload.get("desired_classification", "")
        return f"Network connection request ({classification})" if classification else "Network connection request"
    if ticket_type == TicketType.GUARD_DUTY_REQUEST:
        request_type = payload.get("request_type", "request")
        shift_id = payload.get("shift_id")
        return f"Guard duty {request_type.lower().replace('_', ' ')}" + (
            f" (shift {shift_id})" if shift_id else ""
        )
    return str(ticket_type.value).replace("_", " ").lower()


class ListMyOpenTicketsArgs(BaseModel):
    ticket_type: Literal["NETWORK_REQUEST", "EQUIPMENT_REQUEST", "GUARD_DUTY_REQUEST"] | None = Field(
        default=None,
        description="Filter by ticket type. Omit to return all open tickets.",
    )


def list_my_open_tickets(ctx: ToolContext, args: ListMyOpenTicketsArgs) -> ToolOutput[list]:
    """List the authenticated user's open tickets, optionally filtered by type."""
    if ctx.actor_personal_number is None:
        return ToolOutput.err("No authenticated user.")

    repo = TicketRepo(ctx.session)

    requester = repo.get_personnel_by_personal_number(ctx.actor_personal_number)
    if requester is None:
        return ToolOutput.err(f"No personnel record for personal number {ctx.actor_personal_number}.")

    ticket_type = TicketType(args.ticket_type) if args.ticket_type else None
    tickets = repo.get_open_tickets_for(requester.id, ticket_type=ticket_type)

    return ToolOutput.of([
        {
            "ticket_id": t.id,
            "type": t.type,
            "subject": t.subject,
            "status": t.status,
            "created_at": str(t.created_at),
            "payload": t.payload,
        }
        for t in tickets
    ])


class GetTicketStatusArgs(BaseModel):
    ticket_id: int = Field(description="ID of the ticket to look up.")


def get_ticket_status(ctx: ToolContext, args: GetTicketStatusArgs) -> ToolOutput[dict]:
    """Read-only: return the current status and details of any ticket by ID."""
    repo = TicketRepo(ctx.session)
    ticket = repo.get_ticket(args.ticket_id)
    if ticket is None:
        return ToolOutput.err(f"No ticket with id {args.ticket_id}.")

    return ToolOutput.of({
        "ticket_id": ticket.id,
        "type": ticket.type,
        "status": ticket.status,
        "subject": ticket.subject,
        "description": ticket.description,
        "payload": ticket.payload,
        "created_at": str(ticket.created_at),
        "resolved_at": str(ticket.resolved_at) if ticket.resolved_at else None,
    })


TOOLS = (create_ticket, list_my_open_tickets, get_ticket_status)
MUTATING = {create_ticket.__name__}
