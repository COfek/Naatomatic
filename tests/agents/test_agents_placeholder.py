"""Placeholder for agent-scenario tests (full graph in the loop).

Pattern (once agents/ exists): give the agent a natural-language task, run the graph
against the `session` fixture, then assert the intended outcome:
  - action tasks: the DB changed correctly (e.g., a port got allocated)
  - info tasks: the answer is correct (e.g., "how many free secret ports?" -> N)

Example shape:
    def test_agent_connects_walljack_to_free_port(session):
        result = run_agent(session, "connect wall-jack WJ-007 to a free secret port")
        # assert the wall jack now maps to an occupied SECRET port
"""

import pytest


@pytest.mark.skip(reason="agents/ layer not built yet — template placeholder")
def test_agent_scenario():
    ...
