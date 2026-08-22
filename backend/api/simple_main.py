from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
import sys
import os

# Add parent directory to path to import agents
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.core.config import settings

app = FastAPI(title="NL2SQL Multi-Agent API", description="API for NL2SQL System")

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    answer: str
    sql: Optional[str] = None
    results: List[Dict[str, Any]] = []
    explanation: Optional[str] = None

@app.get("/")
def read_root():
    return {
        "name": "NL2SQL Multi-Agent System",
        "version": "0.1.0",
        "description": "Multi-Agent Natural Language to SQL Conversion System",
        "docs": "/docs",
        "health": "/api/v1/health"
    }

@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "message": "Backend is running"}

@app.post("/api/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Main endpoint: Receives NL question, runs through LangGraph agents, returns result."""
    user_question = request.question
    
    # --- MOCK LOGIC FOR DEMO (Replace with actual LangGraph call) ---
    # In real implementation: state = await orchestrator.run({"input": user_question})
    
    mock_sql = f"SELECT * FROM employees WHERE department = 'IT'; -- Generated for: {user_question}"
    mock_data = [
        {"id": 2, "name": "Bob", "department": "IT", "salary": 70000},
        {"id": 3, "name": "Charlie", "department": "IT", "salary": 75000}
    ]
    mock_explanation = f"The system identified intent to filter employees. Retrieved schema for 'employees'. Generated SQL and validated syntax using sqlglot. Executed safely with row limit {settings.max_rows_returned}."
    
    return QueryResponse(
        answer=f"Found {len(mock_data)} employees matching your criteria.",
        sql=mock_sql,
        results=mock_data,
        explanation=mock_explanation
    )

if __name__ == "__main__":
    uvicorn.run("backend.api.simple_main:app", host="0.0.0.0", port=8000, reload=True)