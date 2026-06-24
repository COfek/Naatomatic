"""LLM client wrapper — the one place that talks to the model. Nodes call this,
never the SDK directly, so the model/params live in one spot.

Using OpenRouter (OpenAI-API-compatible) here, since that's the key in hand. Set
OPENAI_API_KEY (your OpenRouter key) and OPENAI_BASE_URL=https://openrouter.ai/api/v1
in the environment before running.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_MODEL = "openai/gpt-4o-mini"


class LLMClient:
    def __init__(self, model: str = DEFAULT_MODEL, temperature: float = 0.0) -> None:
        self.model = model
        self.temperature = temperature
        self._chat = None  # built lazily so importing this module needs no API key

    def _client(self):
        if self._chat is None:
            from langchain_openai import ChatOpenAI
            self._chat = ChatOpenAI(
                model=self.model,
                temperature=self.temperature,
                base_url=os.environ.get("OPENAI_BASE_URL"),
            )
        return self._chat

    def call_structured_output(self, *, messages: list, schema: Any) -> Any:
        """Call the model and return a validated instance of `schema` (a pydantic
        model). Used by the Router to classify intent."""
        return self._client().with_structured_output(schema).invoke(messages)

    def call_with_tools(self, *, messages: list, tools: list[dict],
                        tool_choice: str = "auto") -> Any:
        """Native tool-calling turn: returns the model's response message — either
        a tool call (`.tool_calls`) or a final answer (`.content`). Used by the
        Worker (ReAct loop)."""
        chat = self._client()
        if tools:
            formatted = [{"type": "function", "function": spec} for spec in tools]
            chat = chat.bind_tools(formatted, tool_choice=tool_choice)
        return chat.invoke(messages)