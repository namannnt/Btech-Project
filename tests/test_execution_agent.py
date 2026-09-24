"""Tests for Agent 7: SQL Execution Agent"""

import pytest
from sqlalchemy import create_engine, text
from backend.agents.state import initialize_state
from backend.agents.execution_agent import SQLExecutionAgent


@pytest.fixture
def agent_with_sqlite(tmp_path):
    """
    Return an execution agent connected to a FILE-BASED SQLite database.
    
    Note: in-memory SQLite (sqlite:///:memory:) cannot be shared across connections —
    each new connection sees an empty database. File-based SQLite persists across connections.
    """
    db_path = tmp_path / "test_exec.db"
    db_url = f"sqlite:///{db_path}"
    # Populate schema and data
    setup_engine = create_engine(db_url)
    with setup_engine.connect() as conn:
        conn.execute(text("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT, email TEXT)"))
        conn.execute(text("INSERT INTO customers VALUES (1, 'Alice', 'alice@example.com')"))
        conn.execute(text("INSERT INTO customers VALUES (2, 'Bob', 'bob@example.com')"))
        conn.commit()
    setup_engine.dispose()
    # Connect the agent to the same file
    agent = SQLExecutionAgent()
    agent.connect_to_database(db_url)
    return agent


def _approved_state(sql: str) -> dict:
    state = initialize_state("test")
    state["selected_sql"] = sql
    state["optimized_sql"] = sql
    state["is_valid"] = True
    state["security_passed"] = True
    return state


def test_execute_select_succeeds(agent_with_sqlite):
    result = agent_with_sqlite.execute_query("SELECT * FROM customers")
    assert result["success"] is True
    assert result["row_count"] == 2
    assert "name" in result["columns"] or "customer_id" in result["columns"]


def test_execute_invalid_sql_fails(agent_with_sqlite):
    result = agent_with_sqlite.execute_query("INVALID SQL STATEMENT")
    assert result["success"] is False
    assert result["error_message"] is not None


def test_invoke_approved_state(agent_with_sqlite, monkeypatch):
    monkeypatch.setattr("backend.core.config.get_dynamic_db_url", lambda x: str(agent_with_sqlite.db_engine.url))
    state = _approved_state("SELECT customer_id, name FROM customers")
    result = agent_with_sqlite.invoke(state)
    assert result["execution_success"] is True
    assert result["query_results"] is not None
    assert len(result["query_results"]) == 2


def test_invoke_blocked_without_security(agent_with_sqlite, monkeypatch):
    """Execution MUST be refused when security_passed=False."""
    monkeypatch.setattr("backend.core.config.get_dynamic_db_url", lambda x: str(agent_with_sqlite.db_engine.url))
    state = initialize_state("test")
    state["selected_sql"] = "SELECT * FROM customers"
    state["optimized_sql"] = "SELECT * FROM customers"
    state["is_valid"] = True
    state["security_passed"] = False
    result = agent_with_sqlite.invoke(state)
    assert result["execution_success"] is False
    assert "SECURITY GATE" in result["execution_error"]


def test_invoke_blocked_without_validation(agent_with_sqlite, monkeypatch):
    """Execution MUST be refused when is_valid=False."""
    monkeypatch.setattr("backend.core.config.get_dynamic_db_url", lambda x: str(agent_with_sqlite.db_engine.url))
    state = initialize_state("test")
    state["selected_sql"] = "SELECT * FROM customers"
    state["optimized_sql"] = "SELECT * FROM customers"
    state["is_valid"] = False
    state["security_passed"] = True
    result = agent_with_sqlite.invoke(state)
    assert result["execution_success"] is False


def test_invoke_no_sql(agent_with_sqlite, monkeypatch):
    monkeypatch.setattr("backend.core.config.get_dynamic_db_url", lambda x: str(agent_with_sqlite.db_engine.url))
    state = initialize_state("test")
    state["is_valid"] = True
    state["security_passed"] = True
    state["selected_sql"] = None
    state["optimized_sql"] = None
    result = agent_with_sqlite.invoke(state)
    assert result["execution_success"] is False


def test_execution_time_populated(agent_with_sqlite, monkeypatch):
    monkeypatch.setattr("backend.core.config.get_dynamic_db_url", lambda x: str(agent_with_sqlite.db_engine.url))
    state = _approved_state("SELECT COUNT(*) FROM customers")
    result = agent_with_sqlite.invoke(state)
    assert result["execution_time_ms"] >= 0.0
