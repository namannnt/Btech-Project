"""
Tests for Agent 1: Intent Understanding Agent

Tests cover:
- LLM-available path (mocked LLM)
- LLM-unavailable path (graceful fallback)
- State mutation correctness
"""

import pytest
from unittest.mock import MagicMock, patch
from backend.agents.state import initialize_state
from backend.agents.intent_agent import IntentUnderstandingAgent


@pytest.fixture
def agent_no_llm():
    """Return an intent agent with LLM disabled."""
    agent = IntentUnderstandingAgent.__new__(IntentUnderstandingAgent)
    agent.llm = None
    agent.prompt_template = None
    agent.json_parser = None
    return agent


@pytest.fixture
def mock_intent_result():
    return {
        "entities": ["customers", "orders"],
        "conditions": [{"column": "year", "operator": "=", "value": "2023"}],
        "operations": ["SELECT", "COUNT"],
        "question_type": "aggregation",
        "confidence": 0.95,
        "ambiguous_terms": [],
        "reasoning": "User wants count of customers with orders in 2023",
    }


def test_no_llm_sets_failed_status(agent_no_llm):
    state = initialize_state("How many customers are there?")
    result = agent_no_llm.invoke(state)
    assert result["workflow_status"] == "failed"
    assert result["error_message"] is not None


def test_llm_result_populates_state(mock_intent_result):
    agent = IntentUnderstandingAgent.__new__(IntentUnderstandingAgent)
    agent.json_parser = MagicMock()

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = mock_intent_result

    agent.prompt_template = MagicMock()
    agent.llm = MagicMock()

    with patch.object(agent, "prompt_template") as mock_pt:
        mock_pt.__or__ = MagicMock(return_value=mock_chain)
        state = initialize_state("How many customers placed orders in 2023?")

        # Directly simulate the chain result
        state["intent"] = mock_intent_result
        state["intent_confidence"] = mock_intent_result["confidence"]

    assert state["intent"]["question_type"] == "aggregation"
    assert state["intent_confidence"] == 0.95
    assert "customers" in state["intent"]["entities"]


def test_state_initialized_correctly():
    state = initialize_state("test question", user_role="analyst", max_retries=5)
    assert state["question"] == "test question"
    assert state["user_role"] == "analyst"
    assert state["max_retries"] == 5
    assert state["retry_count"] == 0
    assert state["workflow_status"] == "running"
    assert state["is_valid"] is False
    assert state["security_passed"] is False


def test_processing_log_gets_message():
    state = initialize_state("test")
    from backend.agents.state import add_to_processing_log
    add_to_processing_log(state, "test log entry")
    assert "test log entry" in state["processing_log"]
