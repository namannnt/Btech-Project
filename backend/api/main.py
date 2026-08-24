"""
FastAPI Backend for NL2SQL Multi-Agent System

This module provides the REST API endpoints for the NL2SQL system.
Endpoints:
- POST /api/v1/query - Convert NL to SQL and execute
- GET /api/v1/health - Health check
- GET /api/v1/databases - List available databases
- POST /api/v1/schema/index - Index database schema
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import time
from datetime import datetime

from backend.core.config import settings, get_settings
from backend.models.schemas import (
    NLQueryRequest,
    NLQueryResponse,
    DatabaseInfo,
    HealthCheck,
    IntentUnderstanding,
    SchemaRetrievalResult,
    ValidationResult,
    QueryExecutionResult,
    ExplanationResult
)
from backend.agents.orchestrator import get_orchestrator, nl2sql


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Multi-Agent Natural Language to SQL Conversion System",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware (for frontend access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Helper Functions
# ============================================================================

def convert_state_to_response(state: Dict[str, Any]) -> NLQueryResponse:
    """Convert agent state to API response schema."""
    return NLQueryResponse(
        success=state.get("workflow_status") == "completed",
        question=state.get("question", ""),
        intent=IntentUnderstanding(**state["intent"]) if state.get("intent") else None,
        retrieved_schema=SchemaRetrievalResult(
            relevant_tables=state.get("relevant_tables", []),
            table_schemas=state.get("table_schemas", {}),
            foreign_keys=state.get("foreign_keys", []),
            relevance_scores=state.get("schema_relevance_scores", {})
        ) if state.get("relevant_tables") else None,
        generated_sql=state.get("optimized_sql") or state.get("selected_sql"),
        optimized_sql=state.get("optimized_sql"),
        validation=ValidationResult(
            **state["validation_result"], 
            is_valid=state.get("is_valid", False)
        ) if state.get("validation_result") else ValidationResult(
            is_valid=state.get("is_valid", False),
            error_message=state.get("validation_error")
        ),
        execution_result=QueryExecutionResult(
            success=state.get("execution_success", False),
            columns=state.get("result_columns", []),
            rows=state.get("query_results", []),
            row_count=len(state.get("query_results", [])),
            execution_time_ms=state.get("execution_time_ms", 0.0),
            error_message=state.get("execution_error")
        ) if state.get("query_results") is not None else None,
        explanation=ExplanationResult(
            sql_explanation=state.get("sql_explanation", ""),
            result_summary=state.get("result_summary", ""),
            insights=state.get("insights", [])
        ) if state.get("sql_explanation") else None,
        error_message=state.get("error_message"),
        processing_time_ms=0.0,  # Will be set by endpoint
        timestamp=datetime.utcnow()
    )


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": "Multi-Agent Natural Language to SQL Conversion System",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


@app.get("/api/v1/health", response_model=HealthCheck, tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    
    Returns system status including:
    - LLM configuration status
    - Database connectivity
    - Vector store readiness
    """
    orchestrator = get_orchestrator()
    
    return HealthCheck(
        status="healthy",
        version=settings.app_version,
        llm_configured=settings.use_openai or settings.use_groq,
        database_connected=True,  # Would check actual connection in production
        vector_store_ready=True,  # Would check ChromaDB in production
        timestamp=datetime.utcnow()
    )


@app.post("/api/v1/query", response_model=NLQueryResponse, tags=["Query"])
async def process_query(request: NLQueryRequest):
    """
    Process a natural language query and return SQL + results.
    
    This is the main endpoint that:
    1. Understands intent from the question
    2. Retrieves relevant schema using RAG
    3. Generates SQL candidates
    4. Validates the SQL
    5. Optimizes the query
    6. Executes against database
    7. Generates explanation
    
    **Example Request:**
    ```json
    {
        "question": "Show me all customers who placed orders in 2023",
        "database_id": "chinook",
        "user_role": "user",
        "include_explanation": true
    }
    ```
    """
    start_time = time.time()
    
    try:
        # Process through orchestrator
        final_state = get_orchestrator().process_query(
            question=request.question,
            database_id=request.database_id,
            user_role=request.user_role,
            include_explanation=request.include_explanation,
            max_retries=3
        )
        
        # Convert to response
        response = convert_state_to_response(final_state)
        
        # Set processing time
        response.processing_time_ms = (time.time() - start_time) * 1000
        
        return response
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        return NLQueryResponse(
            success=False,
            question=request.question,
            error_message=str(e),
            processing_time_ms=processing_time,
            timestamp=datetime.utcnow()
        )


@app.get("/api/v1/databases", response_model=List[DatabaseInfo], tags=["Databases"])
async def list_databases():
    """
    List available databases.
    
    Returns information about configured databases including:
    - Database ID and name
    - Type (PostgreSQL, MySQL, SQLite)
    - Available tables
    - Connection status
    """
    # In production, this would read from configuration
    # For now, return example databases
    return [
        DatabaseInfo(
            id="chinook",
            name="Chinook Music Store",
            type="sqlite",
            tables=["Artist", "Album", "Track", "Customer", "Invoice"],
            connection_status="connected"
        ),
        DatabaseInfo(
            id="northwind",
            name="Northwind Traders",
            type="sqlite",
            tables=["Customers", "Orders", "Products", "Employees"],
            connection_status="connected"
        ),
        DatabaseInfo(
            id="sample",
            name="Sample Database",
            type="sqlite",
            tables=[],
            connection_status="pending"
        )
    ]


@app.post("/api/v1/schema/index", tags=["Schema"])
async def index_schema(background_tasks: BackgroundTasks, database_id: str = "sample"):
    """
    Index database schema into vector store for RAG retrieval.
    
    This endpoint:
    1. Connects to the specified database
    2. Introspects schema (tables, columns, relationships)
    3. Embeds schema information
    4. Stores in ChromaDB for semantic search
    
    Runs as background task to avoid blocking.
    """
    async def do_indexing():
        from backend.agents.schema_agent import get_schema_agent
        
        agent = get_schema_agent()
        
        # Get database URL based on ID
        # In production, this would map database_id to actual connection strings
        db_url = settings.database_url
        
        if agent.connect_to_database(db_url):
            schema = agent.introspect_schema()
            agent.index_schema(schema)
            print(f"✓ Indexed schema for {database_id}: {len(schema.get('tables', {}))} tables")
        else:
            print(f"✗ Failed to connect to database: {database_id}")
    
    background_tasks.add_task(do_indexing)
    
    return {
        "status": "indexing_started",
        "database_id": database_id,
        "message": "Schema indexing started as background task"
    }


@app.get("/api/v1/schema/{database_id}", tags=["Schema"])
async def get_schema_info(database_id: str):
    """
    Get schema information for a specific database.
    
    Returns tables, columns, and relationships.
    """
    from backend.agents.schema_agent import get_schema_agent
    
    agent = get_schema_agent()
    db_url = settings.database_url
    
    if agent.connect_to_database(db_url):
        schema = agent.introspect_schema()
        return {
            "database_id": database_id,
            "tables": schema.get("tables", {}),
            "foreign_keys": schema.get("foreign_keys", []),
            "table_count": len(schema.get("tables", {}))
        }
    else:
        raise HTTPException(status_code=503, detail="Could not connect to database")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print("=" * 60)
    print(f"📚 API Docs: http://localhost:8000/docs")
    print(f"🏥 Health Check: http://localhost:8000/api/v1/health")
    print(f"⚙️  Debug Mode: {settings.debug}")
    print("=" * 60)
    
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
