"""Telemetry — STUB. Per-run tool/LLM metrics for eval + debugging.
Keep telemetry OUT of tool/agent return values (record it here)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolCallMetric:
    tool: str
    ok: bool
    wall_ms: int = 0


@dataclass
class LlmCallMetric:
    model: str
    total_tokens: int = 0
    usd: float = 0.0
    ms: int = 0
