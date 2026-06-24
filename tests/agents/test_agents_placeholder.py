"""TEMPLATE — every deployed pillar agent ships a file like this in tests/agents/.

It has two parts (see IMPLEMENTATION_GUIDE.md "Testing"):

1. Deterministic tool-call assertions live in tests/tools/ (no model). This file is
   for the SECOND part: natural-language questions fed into the agent itself, so we
   can see the final text answer the agent produces.

Copy this into e.g. tests/agents/test_logistics_agent.py and fill in QUESTIONS +
your pillar's assertions. Keep it skipped (or guard on an API key) so CI without a
model key stays green; run it locally to eyeball answers.

    from services.agent_runtime import AgentRuntime
    from services.auth import authenticate
    from agents.orchestrator import run

    # Natural-language questions that should reach THIS pillar's agent:
    QUESTIONS = [
        "Sign monitor CAT-1023 to person 7",          # action -> assert DB change
        "How many free secret ports are there?",       # info   -> eyeball the answer
    ]

    def run_agent(session, personal_number, message) -> str:
        ctx = authenticate(session, personal_number)
        return run(message, AgentRuntime(ctx=ctx))

    @pytest.mark.parametrize("question", QUESTIONS)
    def test_agent_answers(session, capsys, question):
        answer = run_agent(session, "<a manager's personal number>", question)
        print(f"\nQ: {question}\nA: {answer}")   # pytest -s shows the final answer
        assert answer and "error" not in answer.lower()
"""

import pytest


@pytest.mark.skip(reason="agents/ layer not built yet — template placeholder")
def test_agent_scenario():
    ...
