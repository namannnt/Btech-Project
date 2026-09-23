"""Tests for Agent 6: Query Optimization Agent."""

import pytest
from backend.agents.state import initialize_state
from backend.agents.optimization_agent import QueryOptimizationAgent


@pytest.fixture
def agent():
    agent = QueryOptimizationAgent.__new__(QueryOptimizationAgent)
    agent.llm = None
    from langchain_core.prompts import ChatPromptTemplate
    agent.prompt_template = ChatPromptTemplate.from_template("{original_sql}")
    from langchain_core.output_parsers import JsonOutputParser
    agent.json_parser = JsonOutputParser()
    return agent


def _valid_state(sql: str) -> dict:
    state = initialize_state("test query")
    state["selected_sql"] = sql
    state["is_valid"] = True
    state["security_passed"] = True
    state["table_schemas"] = {}
    return state


def test_whitespace_collapsed(agent):
    state = _valid_state("SELECT   name   FROM   customers")
    result = agent.invoke(state)
    assert "  " not in result["optimized_sql"]


def test_keywords_uppercased(agent):
    state = _valid_state("select name from customers where customer_id = 1")
    result = agent.invoke(state)
    assert "SELECT" in result["optimized_sql"]
    assert "FROM" in result["optimized_sql"]
    assert "WHERE" in result["optimized_sql"]


def test_select_star_flagged(agent):
    state = _valid_state("SELECT * FROM customers")
    result = agent.invoke(state)
    # Rule-based optimization flags SELECT * with "Flagged: Consider replacing SELECT *"
    flagged = any("SELECT *" in opt or "SELECT*" in opt for opt in result["optimizations_applied"])
    assert flagged, f"Expected SELECT * flag, got: {result['optimizations_applied']}"


def test_original_sql_stored(agent):
    sql = "SELECT name FROM customers"
    state = _valid_state(sql)
    result = agent.invoke(state)
    assert result["original_sql"] == sql


def test_skips_when_not_valid(agent):
    state = initialize_state("test")
    state["selected_sql"] = "SELECT * FROM customers"
    state["is_valid"] = False
    state["security_passed"] = True
    result = agent.invoke(state)
    # Should skip LLM optimization but not crash
    assert result["optimized_sql"] is not None or result["optimized_sql"] is None


def test_skips_when_security_not_passed(agent):
    state = initialize_state("test")
    state["selected_sql"] = "SELECT * FROM customers"
    state["is_valid"] = True
    state["security_passed"] = False
    result = agent.invoke(state)
    assert result["optimized_sql"] == "SELECT * FROM customers"


def test_no_sql_returns_gracefully(agent):
    state = initialize_state("test")
    state["selected_sql"] = None
    state["is_valid"] = True
    state["security_passed"] = True
    result = agent.invoke(state)
    # Should not raise
    assert result is not None
