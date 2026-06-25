"""Network domain tools — STUBS. Implement following tools/logistics_tools.sign_equipment.
Mutating tools: apply -> validate (check_hc_net_1/2) -> commit/rollback -> audit.
"""

from __future__ import annotations

from tools.base import ToolContext, ToolOutput


def resolve_network_ticket(ctx: ToolContext, *, ticket_id: int, port_id: int) -> ToolOutput[dict]:
    """NETWORK_MANAGER: connect the jack to the port, allocate to requester, close ticket
    (re-validate HC-NET-1/2). Did-you-mean on a bad ticket id."""
    raise NotImplementedError

def release_port(ctx: ToolContext, *, port_id: int) -> ToolOutput[dict]:
    """Free a port: CONNECTED -> DISCONNECTED, clear allocated_to, unpatch the jack (+audit)."""
    raise NotImplementedError

def count_free_ports(ctx: ToolContext, *, classification: str | None = None) -> ToolOutput[dict]:
    """Read-only: count of DISCONNECTED ports (optionally by classification)."""
    raise NotImplementedError

def query_infrastructure(ctx: ToolContext, *, switch: str | None = None) -> ToolOutput[list]:
    """Read-only: switches / ports / wall-jacks reporting."""
    raise NotImplementedError


TOOLS = (resolve_network_ticket, release_port, count_free_ports, query_infrastructure)
MUTATING = {resolve_network_ticket.__name__, release_port.__name__}
