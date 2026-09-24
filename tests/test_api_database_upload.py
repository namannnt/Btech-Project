import pytest
from fastapi.testclient import TestClient
import os
import sqlite3
import tempfile
from backend.api.main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT)')
    conn.execute('CREATE TABLE salaries (employee_id INTEGER, amount REAL)')
    conn.execute("INSERT INTO employees VALUES (1, 'Alice')")
    conn.execute("INSERT INTO salaries VALUES (1, 95000.0)")
    conn.commit()
    conn.close()
    
    yield path
    
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture
def invalid_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    with os.fdopen(fd, 'w') as f:
        f.write("This is not a sqlite database")
    
    yield path
    
    if os.path.exists(path):
        os.remove(path)

def test_database_upload_valid(client, temp_db):
    with open(temp_db, "rb") as f:
        response = client.post(
            "/api/v1/database/upload",
            files={"file": ("test_upload.db", f, "application/octet-stream")}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "connected"
    assert data["filename"] == "test_upload.db"
    assert "database_id" in data
    assert "employees" in data["tables"]
    assert "salaries" in data["tables"]
    
    # Store database_id for next test
    return data["database_id"]

def test_database_upload_invalid(client, invalid_db):
    with open(invalid_db, "rb") as f:
        response = client.post(
            "/api/v1/database/upload",
            files={"file": ("invalid.db", f, "application/octet-stream")}
        )
    
    assert response.status_code == 400
    assert "Invalid SQLite database" in response.json()["detail"] or "Could not connect" in response.json()["detail"]

def test_query_uses_uploaded_db(client, temp_db):
    # Upload db
    with open(temp_db, "rb") as f:
        upload_resp = client.post(
            "/api/v1/database/upload",
            files={"file": ("test_upload.db", f, "application/octet-stream")}
        )
    database_id = upload_resp.json()["database_id"]
    
    # Query against uploaded db
    response = client.post(
        "/api/v1/query",
        json={
            "question": "Show me employee salaries.",
            "database_id": database_id
        }
    )
    
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True, data
    # The generated SQL should reference salaries
    sql = (data["generated_sql"] or "").lower()
    assert "salaries" in sql or "employee" in sql

def test_query_default_db_still_works(client):
    # Query without database_id should still work for sample.db
    response = client.post(
        "/api/v1/query",
        json={
            "question": "Show me the top 5 customers by spending.",
            "database_id": None
        }
    )
    
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True, data
    sql = (data["generated_sql"] or "").lower()
    assert "customers" in sql
