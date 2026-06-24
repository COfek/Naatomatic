"""LLM client wrapper — STUB. One place that talks to the model (Claude via
LangChain `langchain-anthropic`). Nodes call this, never the SDK directly, so the
model/params/telemetry live in one spot.

Add to requirements when implementing: `langchain`, `langchain-anthropic`.
"""

from __future__ import annotations

from typing import Any

# Latest capable Claude models (see claude-api reference): opus claude-opus-4-8,
# sonnet claude-sonnet-4-6, haiku claude-haiku-4-5-20251001.
DEFAULT_MODEL = "claude-sonnet-4-6"


class LLMClient:
    def __init__(self, model: str = DEFAULT_MODEL, temperature: float = 0.0) -> None:
        self.model = model
        self.temperature = temperature

    def call_structured_output(self, *, messages: list[dict], schema: Any) -> Any:
        """Call the model and return a validated object of `schema` (pydantic).
        Used by Router (intent) and Presenter."""
        raise NotImplementedError

    def call_with_tools(self, *, messages: list[dict], tools: list[dict],
                        tool_choice: str = "auto") -> Any:
        """Native tool-calling turn: returns the model's chosen tool call(s) or a
        final message. Used by the Worker (ReAct loop)."""
        raise NotImplementedError
