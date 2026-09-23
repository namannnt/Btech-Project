"""
Tests for Agent 2: Schema Retrieval Agent

Tests cover:
- Database introspection with in-memory SQLite
- Schema indexing (with ChromaDB mocked)
- Retrieval when ChromaDB unavailable (empty fallback)
"""

import pytest
from sqlalchemy import create_engine, text
from backend.agents.state import initialize_state
from backend.agents.schema_agent import SchemaRetrievalAgent


@pytest.fixture
def in_memory_engine():
    """Create an in-memory SQLite database with sample tables."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(customer_id),
                total REAL,
                order_date TEXT
            )
        """))
        conn.execute(text("INSERT INTO customers VALUES (1, 'Alice', 'alice@example.com')"))
        conn.execute(text("INSERT INTO orders VALUES (1, 1, 99.99, '2023-01-01')"))
        conn.commit()
    return engine


@pytest.fixture
def agent_with_db(in_memory_engine):
    """Schema agent connected to in-memory SQLite."""
    agent = SchemaRetrievalAgent()
    agent.db_engine = in_memory_engine
    from sqlalchemy import inspect
    agent.inspector = inspect(in_memory_engine)
    agent._initialized = False  # ChromaDB not initialized
    return agent


def test_introspect_finds_tables(agent_with_db):
    schema = agent_with_db.introspect_schema()
    assert "customers" in schema["tables"]
    assert "orders" in schema["tables"]


def test_introspect_finds_columns(agent_with_db):
    schema = agent_with_db.introspect_schema()
    customers_cols = [c["name"] for c in schema["tables"]["customers"]["columns"]]
    assert "customer_id" in customers_cols
    assert "name" in customers_cols
    assert "email" in customers_cols


def test_introspect_no_engine():
    agent = SchemaRetrievalAgent()
    schema = agent.introspect_schema()
    assert schema == {}


def test_retrieve_without_chromadb_returns_empty():
    """When ChromaDB is not initialized, retrieve returns empty dicts."""
    agent = SchemaRetrievalAgent()
    agent._initialized = False
    result = agent.retrieve_relevant_schema("test query", top_k=3)
    assert result["relevant_tables"] == []
    assert result["table_schemas"] == {}
    assert result["foreign_keys"] == []


def test_invoke_sets_relevant_tables():
    """Test invoke updates state even with empty results."""
    agent = SchemaRetrievalAgent()
    agent._initialized = False
    state = initialize_state("Show me all customers")
    result_state = agent.invoke(state)
    # Should not crash; should set empty defaults
    assert isinstance(result_state["relevant_tables"], list)
    assert isinstance(result_state["table_schemas"], dict)
    assert isinstance(result_state["foreign_keys"], list)
