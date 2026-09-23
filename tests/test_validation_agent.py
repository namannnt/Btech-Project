"""
Tests for Agent 4: SQL Validation Agent

Tests cover:
- Syntax validation (valid/invalid SQL)
- Schema validation (table existence)
- Semantic validation (operation matching)
- Multi-candidate evaluation and selection
- is_valid formula: syntax AND schema AND semantic
"""

import pytest
from backend.agents.state import initialize_state
from backend.agents.validation_agent import SQLValidationAgent


@pytest.fixture
def agent():
    return SQLValidationAgent()


@pytest.fixture
def sample_schema():
    return {
        "customers": {
            "columns": [
                {"name": "customer_id", "type": "INTEGER"},
                {"name": "name", "type": "TEXT"},
                {"name": "email", "type": "TEXT"},
            ]
        },
        "orders": {
            "columns": [
                {"name": "order_id", "type": "INTEGER"},
                {"name": "customer_id", "type": "INTEGER"},
                {"name": "total", "type": "REAL"},
            ]
        }
    }


# ============================================================================
# Syntax Validation
# ============================================================================

def test_valid_syntax(agent):
    valid, errors = agent.validate_syntax("SELECT customer_id, name FROM customers WHERE customer_id = 1")
    assert valid is True
    assert errors == []


def test_invalid_syntax(agent):
    valid, errors = agent.validate_syntax("SELEC name FRM customers")
    assert valid is False
    assert len(errors) > 0


def test_empty_sql_syntax(agent):
    valid, errors = agent.validate_syntax("")
    assert valid is False


# ============================================================================
# Schema Validation
# ============================================================================

def test_valid_table_reference(agent, sample_schema):
    sql = "SELECT name FROM customers"
    valid, errors = agent.validate_schema(sql, sample_schema, [])
    assert valid is True


def test_nonexistent_table_rejected(agent, sample_schema):
    sql = "SELECT * FROM nonexistent_table"
    valid, errors = agent.validate_schema(sql, sample_schema, [])
    assert valid is False
    assert any("nonexistent_table" in e for e in errors)


def test_empty_schema_passes_soft(agent):
    """When no schema is available, schema validation soft-passes."""
    valid, errors = agent.validate_schema("SELECT * FROM customers", {}, [])
    assert valid is True


# ============================================================================
# Semantic Validation
# ============================================================================

def test_semantic_passes_when_operations_match(agent):
    sql = "SELECT COUNT(*) FROM customers"
    intent = {"operations": ["COUNT", "SELECT"]}
    valid, issues = agent.validate_semantic(sql, "How many customers?", intent)
    assert valid is True


def test_semantic_fails_when_count_missing(agent):
    sql = "SELECT name FROM customers"
    intent = {"operations": ["COUNT"]}
    valid, issues = agent.validate_semantic(sql, "How many customers?", intent)
    assert valid is False
    assert any("COUNT" in i for i in issues)


def test_semantic_fails_when_group_by_missing(agent):
    sql = "SELECT name FROM customers"
    intent = {"operations": ["GROUP BY", "SELECT"]}
    valid, issues = agent.validate_semantic(sql, "Group customers", intent)
    assert valid is False


# ============================================================================
# is_valid correctness: must include semantic_valid
# ============================================================================

def test_is_valid_requires_all_three_dimensions(agent, sample_schema):
    """
    A syntactically and schema-valid SQL that semantically mismatches intent
    must result in is_valid=False.
    """
    state = initialize_state("How many customers?")
    state["selected_sql"] = "SELECT name FROM customers"  # Missing COUNT
    state["sql_candidates"] = [
        {"sql": "SELECT name FROM customers", "confidence": 0.9, "explanation": "simple select"}
    ]
    state["table_schemas"] = sample_schema
    state["foreign_keys"] = []
    state["intent"] = {"operations": ["COUNT"]}

    result = agent.invoke(state)
    assert result["is_valid"] is False


def test_is_valid_true_when_all_pass(agent, sample_schema):
    """A fully correct SQL should pass all three validation dimensions."""
    state = initialize_state("Show me customers")
    state["selected_sql"] = "SELECT customer_id, name FROM customers"
    state["sql_candidates"] = [
        {"sql": "SELECT customer_id, name FROM customers", "confidence": 0.95, "explanation": ""}
    ]
    state["table_schemas"] = sample_schema
    state["foreign_keys"] = []
    state["intent"] = {"operations": ["SELECT"]}

    result = agent.invoke(state)
    assert result["is_valid"] is True
    assert result["validation_result"]["syntax_valid"] is True
    assert result["validation_result"]["schema_valid"] is True
    assert result["validation_result"]["semantic_valid"] is True


# ============================================================================
# Multi-candidate evaluation
# ============================================================================

def test_best_candidate_selected(agent, sample_schema):
    """Validation should pick the highest-scoring valid candidate."""
    state = initialize_state("Show me customer names")
    state["sql_candidates"] = [
        {"sql": "SELEC name FRM customers", "confidence": 0.9, "explanation": "broken"},
        {"sql": "SELECT customer_id, name FROM customers", "confidence": 0.85, "explanation": "ok"},
    ]
    state["selected_sql"] = "SELEC name FRM customers"
    state["table_schemas"] = sample_schema
    state["foreign_keys"] = []
    state["intent"] = {"operations": ["SELECT"]}

    result = agent.invoke(state)
    assert result["is_valid"] is True
    assert "SELECT customer_id, name FROM customers" in result["selected_sql"]


def test_all_candidates_fail_triggers_retry_condition(agent, sample_schema):
    """When all candidates fail, should_retry returns True (if retries left)."""
    state = initialize_state("test")
    state["sql_candidates"] = [
        {"sql": "INVALID SQL XYZ", "confidence": 0.5, "explanation": ""},
    ]
    state["selected_sql"] = "INVALID SQL XYZ"
    state["table_schemas"] = sample_schema
    state["foreign_keys"] = []
    state["intent"] = {"operations": ["SELECT"]}
    state["retry_count"] = 0
    state["max_retries"] = 3

    result = agent.invoke(state)
    assert result["is_valid"] is False
    assert agent.should_retry(result) is True


def test_no_sql_fails_validation(agent):
    state = initialize_state("test")
    state["selected_sql"] = None
    state["sql_candidates"] = []
    result = agent.invoke(state)
    assert result["is_valid"] is False
    assert result["validation_errors"]
