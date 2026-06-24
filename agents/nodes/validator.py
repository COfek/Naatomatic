"""Validator node — STUB. Hard rules are enforced *inside* tools (apply → rules →
commit/rollback), so a rejected action already comes back as ToolResult.ok == False.
This node's job is to surface that cleanly to the Worker (turn a rule rejection /
did-you-mean into a message the Worker relays to the user) — never to silently
re-commit. It is the explicit 'engine decides' gate of the §2 boundary."""

from __future__ import annotations

from agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError  # inspect state["tool_result"]; format ok/err for the Worker
