"""
Tests for Agent 5: Security Agent

Tests cover:
- Absolutely forbidden statements (DROP, ALTER, TRUNCATE, GRANT, REVOKE)
- Role-based operation permissions (user cannot DELETE)
- Table-level permissions (guest role restricted tables)
- SQL injection heuristic detection
- Audit record generation
- State mutation (security_passed, security_errors, security_result)
"""

import pytest
from backend.agents.state import initialize_state
from backend.agents.security_agent import SecurityAgent


@pytest.fixture
def agent():
    return SecurityAgent()


# ============================================================================
# Forbidden statements — always rejected regardless of role
# ============================================================================

@pytest.mark.parametrize("dangerous_sql", [
    "DROP TABLE customers",
    "ALTER TABLE customers ADD COLUMN age INTEGER",
    "TRUNCATE TABLE orders",
    "GRANT ALL PRIVILEGES ON customers TO public",
    "REVOKE SELECT ON customers FROM user1",
    "CREATE TABLE new_table (id INTEGER)",
])
def test_forbidden_statements_rejected_for_admin(agent, dangerous_sql):
    """Even admin cannot run DROP, ALTER, TRUNCATE, GRANT, REVOKE, CREATE."""
    passed, violations, warnings, audit = agent.check_sql(dangerous_sql, "admin")
    assert passed is False
    assert len(violations) > 0


# ============================================================================
# Role-based operation permissions
# ============================================================================

def test_user_can_select(agent):
    passed, violations, warnings, audit = agent.check_sql(
        "SELECT customer_id, name FROM customers", "user"
    )
    assert passed is True
    assert violations == []


def test_user_cannot_delete(agent):
    passed, violations, warnings, audit = agent.check_sql(
        "DELETE FROM customers WHERE customer_id = 1", "user"
    )
    assert passed is False
    assert any("DELETE" in v for v in violations)


def test_user_cannot_insert(agent):
    passed, violations, warnings, audit = agent.check_sql(
        "INSERT INTO customers VALUES (99, 'Eve', 'eve@example.com')", "user"
    )
    assert passed is False
    assert any("INSERT" in v for v in violations)


def test_user_cannot_update(agent):
    passed, violations, warnings, audit = agent.check_sql(
        "UPDATE customers SET name='Bob' WHERE customer_id=1", "user"
    )
    assert passed is False
    assert any("UPDATE" in v for v in violations)


def test_analyst_can_select(agent):
    passed, violations, warnings, audit = agent.check_sql(
        "SELECT COUNT(*) FROM orders GROUP BY customer_id", "analyst"
    )
    assert passed is True


def test_admin_can_delete(agent):
    passed, violations, warnings, audit = agent.check_sql(
        "DELETE FROM customers WHERE customer_id = 99", "admin"
    )
    assert passed is True


# ============================================================================
# SQL injection detection
# ============================================================================

def test_injection_union_select_blocked(agent):
    sql = "SELECT name FROM customers UNION SELECT password FROM users"
    passed, violations, warnings, audit = agent.check_sql(sql, "user")
    assert passed is False


def test_injection_semicolon_drop_blocked(agent):
    sql = "SELECT name FROM customers; DROP TABLE customers"
    passed, violations, warnings, audit = agent.check_sql(sql, "admin")
    assert passed is False


# ============================================================================
# Audit record
# ============================================================================

def test_audit_record_has_required_fields(agent):
    _, _, _, audit = agent.check_sql("SELECT * FROM customers", "user")
    assert "timestamp" in audit
    assert "role" in audit
    assert "decision" in audit
    assert "violations" in audit


def test_audit_decision_approved_on_pass(agent):
    _, _, _, audit = agent.check_sql("SELECT name FROM customers", "user")
    assert audit["decision"] == "APPROVED"


def test_audit_decision_rejected_on_fail(agent):
    _, _, _, audit = agent.check_sql("DROP TABLE customers", "admin")
    assert audit["decision"] == "REJECTED"


# ============================================================================
# State invocation
# ============================================================================

def test_invoke_approved_state(agent):
    state = initialize_state("Show me customers", user_role="user")
    state["selected_sql"] = "SELECT customer_id, name FROM customers"
    result = agent.invoke(state)
    assert result["security_passed"] is True
    assert result["security_errors"] == []
    assert result["security_result"] is not None


def test_invoke_rejected_state(agent):
    state = initialize_state("Drop table", user_role="user")
    state["selected_sql"] = "DROP TABLE customers"
    result = agent.invoke(state)
    assert result["security_passed"] is False
    assert len(result["security_errors"]) > 0
    assert result["workflow_status"] == "failed"


def test_invoke_no_sql(agent):
    state = initialize_state("test", user_role="user")
    state["selected_sql"] = None
    result = agent.invoke(state)
    assert result["security_passed"] is False
