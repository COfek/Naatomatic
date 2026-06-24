from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from agents.orchestrator import run
from services.agent_runtime import AgentRuntime
from services.auth import authenticate


def test_orchestrator_run_success(session):
    """Test that agents.orchestrator.run successfully invokes the graph and returns the answer."""
    # Obtain a valid ToolContext using the seeded session
    ctx = authenticate(session, "1234567")
    assert ctx is not None

    runtime = AgentRuntime(ctx=ctx)
    messages = [{"role": "user", "content": "Hi"}]

    # Mock the graph compilation and execution
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "final_answer": "Hi! How can I help you?",
        "turn": 1,
    }

    with patch("agents.orchestrator.build_graph", return_value=mock_graph) as mock_build_graph:
        answer = run(messages, runtime)

        # Assert build_graph was called
        mock_build_graph.assert_called_once()
        # Assert invoke was called with the expected structure
        mock_graph.invoke.assert_called_once_with({
            "runtime": runtime,
            "user_message": "Hi",
            "conversation_history": messages,
            "messages": [],
            "tool_to_call": None,
            "final_answer": None,
            "turn": 0,
        })
        # Assert the final answer returned is correct
        assert answer == "Hi! How can I help you?"


def test_orchestrator_run_exception(session):
    """Test that agents.orchestrator.run gracefully catches exceptions from the graph and returns an error string."""
    ctx = authenticate(session, "1234567")
    assert ctx is not None

    runtime = AgentRuntime(ctx=ctx)
    messages = [{"role": "user", "content": "Hi"}]

    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = ValueError("Something went wrong in the graph execution")

    with patch("agents.orchestrator.build_graph", return_value=mock_graph):
        answer = run(messages, runtime)
        assert "graph error" in answer
        assert "ValueError" in answer
        assert "Something went wrong in the graph execution" in answer
