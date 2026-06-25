"""LLM client wrapper — the one place that talks to the model. Nodes call this,
never the SDK directly, so the model/params live in one spot.

Using OpenRouter (OpenAI-API-compatible) here, since that's the key in hand. Set
OPENAI_API_KEY (your OpenRouter key) and OPENAI_BASE_URL=https://openrouter.ai/api/v1
in the environment before running.
"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from config.settings import DEFAULT_LLM_MODEL, OPENROUTER_BASE_URL

DEFAULT_MODEL = DEFAULT_LLM_MODEL


def get_llm(model: str = DEFAULT_MODEL, temperature: float = 0.0) -> ChatOpenAI:
    """Return a ChatOpenAI instance routed through OpenRouter."""
    return ChatOpenAI(
        model=model,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
    )


class LLMClient:
    def __init__(self, model: str = DEFAULT_MODEL, temperature: float = 0.0) -> None:
        self.model = model
        self.temperature = temperature
        self._llm = get_llm(model, temperature)

    def call_structured_output(self, *, messages: list[dict], schema: Any) -> Any:
        """Call the model and return a validated object of `schema` (pydantic)."""
        return self._llm.with_structured_output(schema).invoke(messages)

    def call_with_tools(self, *, messages: list[dict], tools: list[dict],
                        tool_choice: str = "auto") -> Any:
        """Native tool-calling turn."""
        return self._llm.bind_tools(tools, tool_choice=tool_choice).invoke(messages)
