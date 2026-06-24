"""Shared tool contract — every tool in every pillar uses these.

A **tool** is a plain function:

    def tool_name(ctx: ToolContext, *, arg1: str, arg2: int = 0) -> ToolResult[...]:
        ...

- First positional param is always `ctx` (carries the DB session + the acting user).
  It is NOT part of the tool's public schema.
- All inputs the model supplies are **keyword-only** (after `*`) and **type-hinted**
  (the schema is generated from the hints).
- The function returns a `ToolResult` — it does not raise for expected failures
  (missing record, rule violation, permission denied); it returns `ToolResult.err(...)`.
  Only unexpected bugs raise.

This is the single contract the registry, the MCP adapter, and the in-process
executor all rely on. Don't deviate from it.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar, get_args, get_origin, get_type_hints

from sqlalchemy.orm import Session

T = TypeVar("T")


@dataclass(frozen=True)
class ToolResult(Generic[T]):
    """Uniform tool return. `ok=False` carries a human-readable `error`; `suggestions`
    holds 'did-you-mean' candidates (see fuzzy-reference rule, DESIGN §2)."""

    value: T | None = None
    ok: bool = True
    error: str | None = None
    suggestions: list[str] = field(default_factory=list)

    @staticmethod
    def of(value: T) -> "ToolResult[T]":
        return ToolResult(value=value, ok=True)

    @staticmethod
    def err(message: str, suggestions: list[str] | None = None) -> "ToolResult[Any]":
        return ToolResult(value=None, ok=False, error=message, suggestions=suggestions or [])


@dataclass
class ToolContext:
    """Per-call context handed to every tool: the DB session and who is acting.

    `actor_personal_number` / `roles` come from auth (login by personal number).
    Tools use the session to read/write (via repositories) and `roles` to gate
    manager-only actions (`require_role`).
    """

    session: Session
    actor_personal_number: str | None = None
    roles: list[str] = field(default_factory=list)


def require_role(ctx: ToolContext, role: str) -> ToolResult[Any] | None:
    """Return an error ToolResult if the actor lacks `role`, else None.

    Usage:  if (deny := require_role(ctx, "LOGISTICS_OFFICER")): return deny
    """
    if role not in (ctx.roles or []):
        return ToolResult.err(f"This action requires the {role} role.")
    return None


# --------------------------------------------------------------------------- #
# Tool-spec generation (JSON schema from the function signature)
# --------------------------------------------------------------------------- #
def _json_property(annotation: Any) -> dict[str, Any]:
    if annotation in (int,):
        return {"type": "integer"}
    if annotation in (float,):
        return {"type": "number"}
    if annotation in (bool,):
        return {"type": "boolean"}
    origin = get_origin(annotation)
    if origin is Literal:
        values = list(get_args(annotation))
        return {"type": "string", "enum": values}
    if origin is list:
        return {"type": "array", "items": {"type": "string"}}
    return {"type": "string"}


def tool_spec(fn: Callable[..., Any]) -> dict[str, Any]:
    """Build an OpenAI/MCP-style function spec from a tool's signature.
    Skips the leading `ctx` parameter; required = params without defaults."""
    hints = get_type_hints(fn)
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, param in inspect.signature(fn).parameters.items():
        if name == "ctx" or param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
            continue
        props[name] = _json_property(hints.get(name, str))
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "name": fn.__name__,
        "description": (fn.__doc__ or "").strip().split("\n\n")[0],
        "parameters": {"type": "object", "properties": props, "required": required},
    }
