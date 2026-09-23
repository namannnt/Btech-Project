"""Tests for Agent 8: Explanation Agent"""

import pytest
from backend.agents.state import initialize_state
from backend.agents.explanation_agent import ExplanationAgent


@pytest.fixture
def agent_no_llm():
    agent = ExplanationAgent.__new__(ExplanationAgent)
    agent.llm = None
    from langchain_core.prompts import ChatPromptTemplate
    agent.prompt_template = ChatPromptTemplate.from_template("{question}")
    from langchain_core.output_parsers import JsonOutputParser
    agent.json_parser = JsonOutputParser()
    return agent


def _state_with_results(sql: str, rows=None, cols=None) -> dict:
    state = initialize_state("Show me all customers")
    state["selected_sql"] = sql
    state["optimized_sql"] = sql
    state["query_results"] = rows or [[1, "Alice"], [2, "Bob"]]
    state["result_columns"] = cols or ["customer_id", "name"]
    state["include_explanation"] = True
    return state


def test_no_llm_generates_fallback(agent_no_llm):
    state = _state_with_results("SELECT customer_id, name FROM customers")
    result = agent_no_llm.invoke(state)
    assert result["sql_explanation"] != ""
    assert "SELECT" in result["sql_explanation"] or "SQL" in result["sql_explanation"]


def test_result_summary_populated_no_llm(agent_no_llm):
    state = _state_with_results("SELECT * FROM customers")
    result = agent_no_llm.invoke(state)
    assert result["result_summary"] != ""


def test_skip_when_include_explanation_false(agent_no_llm):
    state = _state_with_results("SELECT * FROM customers")
    state["include_explanation"] = False
    # Should return without modifying explanation fields
    state["sql_explanation"] = None
    result = agent_no_llm.invoke(state)
    assert result["sql_explanation"] is None


def test_no_sql_skips_gracefully(agent_no_llm):
    state = initialize_state("test")
    state["selected_sql"] = None
    state["optimized_sql"] = None
    result = agent_no_llm.invoke(state)
    assert result is not None  # Should not raise


def test_empty_results_handled(agent_no_llm):
    state = _state_with_results("SELECT * FROM customers", rows=[], cols=[])
    result = agent_no_llm.invoke(state)
    assert "No results" in result["result_summary"] or result["result_summary"] != ""


def test_summarize_results_with_data(agent_no_llm):
    summary = agent_no_llm._summarize_results(
        [[1, "Alice"], [2, "Bob"]], ["id", "name"]
    )
    assert "2" in summary  # row count
    assert "id" in summary or "name" in summary
