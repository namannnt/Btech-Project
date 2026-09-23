"""
Tests for the FastAPI API endpoint.

Tests cover:
- POST /api/v1/query response schema
- GET /api/v1/health
- GET /
- Response field presence and types
- Mocked orchestrator (no LLM needed)
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

from backend.api.main import app, _state_to_response
from backend.agents.state import initialize_state


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================================
# Root and Health endpoints
# ============================================================================

def test_root_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data


def test_health_check_returns_200(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "agents_loaded" in data
    assert data["agents_loaded"] == 8


# ============================================================================
# POST /api/v1/query — mocked orchestrator
# ============================================================================

def _make_completed_state(question: str) -> dict:
    state = initialize_state(question, user_role="user")
    state["workflow_status"] = "completed"
    state["is_valid"] = True
    state["security_passed"] = True
    state["selected_sql"] = "SELECT COUNT(*) FROM customers"
    state["optimized_sql"] = "SELECT COUNT(*) FROM customers"
    state["query_results"] = [[5]]
    state["result_columns"] = ["count"]
    state["execution_success"] = True
    state["execution_time_ms"] = 12.5
    state["sql_explanation"] = "Counts all customers"
    state["result_summary"] = "There are 5 customers"
    state["insights"] = ["Small customer base"]
    state["retry_count"] = 0
    state["validation_result"] = {
        "syntax_valid": True, "schema_valid": True, "semantic_valid": True,
        "is_valid": True, "errors": [], "warnings": [], "evaluated_candidates": 1
    }
    state["security_result"] = {
        "timestamp": datetime.utcnow().isoformat(),
        "role": "user", "decision": "APPROVED",
        "violations": [], "warnings": [], "sql_preview": "SELECT..."
    }
    return state


def test_query_endpoint_returns_200(client):
    completed_state = _make_completed_state("How many customers?")
    with patch("backend.api.main.get_orchestrator") as mock_orch_getter:
        mock_orch = MagicMock()
        mock_orch.process_query.return_value = completed_state
        mock_orch_getter.return_value = mock_orch

        response = client.post(
            "/api/v1/query",
            json={"question": "How many customers?", "user_role": "user"}
        )
        assert response.status_code == 200


def test_query_response_has_required_fields(client):
    completed_state = _make_completed_state("How many customers?")
    with patch("backend.api.main.get_orchestrator") as mock_orch_getter:
        mock_orch = MagicMock()
        mock_orch.process_query.return_value = completed_state
        mock_orch_getter.return_value = mock_orch

        response = client.post(
            "/api/v1/query",
            json={"question": "How many customers?"}
        )
        data = response.json()

        assert "success" in data
        assert "question" in data
        assert "processing_time_ms" in data
        assert "timestamp" in data


def test_query_response_success_true(client):
    completed_state = _make_completed_state("How many customers?")
    with patch("backend.api.main.get_orchestrator") as mock_orch_getter:
        mock_orch = MagicMock()
        mock_orch.process_query.return_value = completed_state
        mock_orch_getter.return_value = mock_orch

        response = client.post(
            "/api/v1/query",
            json={"question": "How many customers?"}
        )
        data = response.json()
        assert data["success"] is True


def test_query_missing_question_returns_422(client):
    response = client.post("/api/v1/query", json={})
    assert response.status_code == 422


def test_query_empty_question_returns_422(client):
    response = client.post("/api/v1/query", json={"question": ""})
    assert response.status_code == 422


# ============================================================================
# State-to-response conversion
# ============================================================================

def test_state_to_response_maps_correctly():
    state = _make_completed_state("test")
    response = _state_to_response(state)
    assert response.success is True
    assert response.generated_sql == "SELECT COUNT(*) FROM customers"
    assert response.security is not None
    assert response.execution_result is not None
    assert response.explanation is not None
