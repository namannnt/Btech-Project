"""
Tests for Agent 3: SQL Generation Agent

Tests cover:
- No-LLM path (graceful failure)
- Schema context formatting
- Foreign key formatting
- Retry generation increments retry_count
"""

import pytest
from unittest.mock import MagicMock
from backend.agents.state import initialize_state
from backend.agents.sql_generation_agent import SQLGenerationAgent


@pytest.fixture
def agent_no_llm():
    agent = SQLGenerationAgent.__new__(SQLGenerationAgent)
    agent.llm = None
    agent.prompt_template = None
    agent.json_parser = None
    return agent


@pytest.fixture
def sample_state():
    state = initialize_state("Show me all customers", database_id="test")
    state["intent"] = {
        "entities": ["customers"],
        "conditions": [],
        "operations": ["SELECT"],
        "question_type": "factual",
    }
    state["relevant_tables"] = ["customers"]
    state["table_schemas"] = {
        "customers": {
            "columns": [
                {"name": "customer_id", "type": "INTEGER"},
                {"name": "name", "type": "TEXT"},
            ]
        }
    }
    state["foreign_keys"] = []
    return state


def test_no_llm_sets_failed_status(agent_no_llm, sample_state):
    result = agent_no_llm.invoke(sample_state)
    assert result["workflow_status"] == "failed"
    assert result["error_message"] is not None


def test_format_schema_context(sample_state):
    agent = SQLGenerationAgent.__new__(SQLGenerationAgent)
    agent.llm = None
    context = agent._format_schema_context(sample_state)
    assert "customers" in context
    assert "customer_id" in context


def test_format_foreign_keys_empty():
    agent = SQLGenerationAgent.__new__(SQLGenerationAgent)
    agent.llm = None
    result = agent._format_foreign_keys([])
    assert "No foreign key" in result


def test_format_foreign_keys_populated():
    agent = SQLGenerationAgent.__new__(SQLGenerationAgent)
    agent.llm = None
    fks = [{"table": "orders", "column": "customer_id",
             "referenced_table": "customers", "referenced_column": "customer_id"}]
    result = agent._format_foreign_keys(fks)
    assert "orders.customer_id" in result
    assert "customers.customer_id" in result


def test_retry_generation_increments_count(agent_no_llm, sample_state):
    sample_state["retry_count"] = 0
    result = agent_no_llm.retry_generation(sample_state, ["Syntax error in SELECT"])
    assert result["retry_count"] == 1


def test_retry_generation_increments_from_nonzero(agent_no_llm, sample_state):
    sample_state["retry_count"] = 2
    result = agent_no_llm.retry_generation(sample_state, ["Schema error"])
    assert result["retry_count"] == 3

def test_ungrounded_schema_short_circuits_pipeline(sample_state):
    agent = SQLGenerationAgent.__new__(SQLGenerationAgent)
    agent.prompt_template = MagicMock()
    agent.llm = MagicMock()
    agent.json_parser = MagicMock()
    
    # Mock chain to return empty candidates and a reasoning
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = {
        "candidates": [],
        "reasoning": "Requested entity 'employees' not found in schema."
    }
    
    # Setup chain property manually
    agent.prompt_template.__or__ = MagicMock(return_value=MagicMock(__or__=MagicMock(return_value=mock_chain)))
    
    result = agent.invoke(sample_state)
    assert result["workflow_status"] == "failed"
    assert result["error_message"] == "Requested entity 'employees' not found in schema."
    assert result["sql_candidates"] == []
    assert result["selected_sql"] is None
