"""Generic ticket repository — shared across all domains.

Tools that create or query tickets use this repo; domain-specific repos (logistics,
network) handle the domain side of resolution but call TicketRepo for ticket lookup.
"""

from __future__ import annotations

from sqlalchemy import select

from data.services.base import Repository
from models import tables as t
from models.enums import TicketStatus, TicketType


class TicketRepo(Repository):
    def get_personnel_by_personal_number(self, personal_number: str) -> t.Personnel | None:
        return self.session.scalar(
            select(t.Personnel).where(t.Personnel.personal_number == personal_number)
        )

    def create_ticket(self, *, type: TicketType, requester_id: int, subject: str,
                      description: str | None = None, payload: dict | None = None) -> t.Ticket:
        ticket = t.Ticket(
            type=type,
            requester_id=requester_id,
            subject=subject,
            description=description,
            payload=payload,
        )
        self.session.add(ticket)
        self.session.flush()
        return ticket

    def get_open_tickets_for(self, personnel_id: int,
                             ticket_type: TicketType | None = None) -> list[t.Ticket]:
        stmt = select(t.Ticket).where(
            t.Ticket.requester_id == personnel_id,
            t.Ticket.status == TicketStatus.OPEN.value,
        )
        if ticket_type is not None:
            stmt = stmt.where(t.Ticket.type == ticket_type.value)
        return list(self.session.scalars(stmt).all())

    def get_ticket(self, ticket_id: int) -> t.Ticket | None:
        return self.session.get(t.Ticket, ticket_id)
