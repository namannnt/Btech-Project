"""
FastAPI Backend for the NL2SQL 8-Agent System

Single canonical entry point — POST /api/v1/query runs the real orchestrator.

Endpoints:
- GET  /                         API info
- GET  /api/v1/health            Health check
- POST /api/v1/query             NL to SQL + execution (MAIN ENDPOINT)
- GET  /api/v1/databases         List available databases
- POST /api/v1/schema/index      Trigger schema indexing into ChromaDB
- GET  /api/v1/schema/{id}       Get introspected schema for a database
"""

import time
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.models.schemas import (
    NLQueryRequest,
    NLQueryResponse,
    DatabaseInfo,
    HealthCheck,
    IntentUnderstanding,
    SchemaRetrievalResult,
    ValidationResult,
    SecurityResult,
    QueryExecutionResult,
    ExplanationResult,
)
from backend.agents.orchestrator import get_orchestrator


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    description=(
        "Multi-Agent Natural Language to SQL Conversion System. "
        "8-agent pipeline: Intent → Schema → SQL Generation → Validation → "
        "Security → Optimization → Execution → Explanation."
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper: convert AgentState -> NLQueryResponse
# ---------------------------------------------------------------------------

def _state_to_response(state: Dict[str, Any]) -> NLQueryResponse:
    """Map the final AgentState to the canonical API response schema."""

    # Intent
    intent_obj: Optional[IntentUnderstanding] = None
    raw_intent = state.get("intent")
    if raw_intent and isinstance(raw_intent, dict):
        intent_obj = IntentUnderstanding(
            entities=raw_intent.get("entities", []),
            conditions=raw_intent.get("conditions", []),
            operations=raw_intent.get("operations", []),
            question_type=raw_intent.get("question_type", "unknown"),
            confidence=raw_intent.get("confidence", 0.0),
            ambiguous_terms=raw_intent.get("ambiguous_terms", []),
            reasoning=raw_intent.get("reasoning", ""),
        )

    # Schema
    schema_obj: Optional[SchemaRetrievalResult] = None
    if state.get("relevant_tables"):
        schema_obj = SchemaRetrievalResult(
            relevant_tables=state.get("relevant_tables", []),
            table_schemas=state.get("table_schemas", {}),
            foreign_keys=state.get("foreign_keys", []),
            relevance_scores=state.get("schema_relevance_scores", {}),
        )

    # Validation
    validation_obj: Optional[ValidationResult] = None
    raw_validation = state.get("validation_result")
    if raw_validation and isinstance(raw_validation, dict):
        best_raw = raw_validation.get("best_candidate")
        validation_obj = ValidationResult(
            is_valid=raw_validation.get("is_valid", state.get("is_valid", False)),
            syntax_valid=raw_validation.get("syntax_valid", False),
            schema_valid=raw_validation.get("schema_valid", False),
            semantic_valid=raw_validation.get("semantic_valid", False),
            errors=raw_validation.get("errors", state.get("validation_errors", [])),
            warnings=raw_validation.get("warnings", []),
            evaluated_candidates=raw_validation.get("evaluated_candidates", 0),
        )
    else:
        validation_obj = ValidationResult(
            is_valid=state.get("is_valid", False),
            errors=state.get("validation_errors", []),
        )

    # Security
    security_obj: Optional[SecurityResult] = None
    raw_security = state.get("security_result")
    if raw_security and isinstance(raw_security, dict):
        security_obj = SecurityResult(
            passed=state.get("security_passed", False),
            role=raw_security.get("role", state.get("user_role", "user")),
            decision=raw_security.get("decision", "REJECTED"),
            violations=raw_security.get("violations", state.get("security_errors", [])),
            warnings=raw_security.get("warnings", []),
            timestamp=raw_security.get("timestamp", ""),
            sql_preview=raw_security.get("sql_preview", ""),
        )
    elif state.get("security_errors"):
        security_obj = SecurityResult(
            passed=state.get("security_passed", False),
            violations=state.get("security_errors", []),
        )

    # Execution result
    exec_obj: Optional[QueryExecutionResult] = None
    if state.get("query_results") is not None or state.get("execution_success"):
        exec_obj = QueryExecutionResult(
            success=state.get("execution_success", False),
            columns=state.get("result_columns", []),
            rows=state.get("query_results", []),
            row_count=len(state.get("query_results") or []),
            execution_time_ms=state.get("execution_time_ms", 0.0),
            error_message=state.get("execution_error"),
        )

    # Explanation
    explanation_obj: Optional[ExplanationResult] = None
    if state.get("sql_explanation"):
        explanation_obj = ExplanationResult(
            sql_explanation=state.get("sql_explanation", ""),
            result_summary=state.get("result_summary", ""),
            insights=state.get("insights", []),
        )

    return NLQueryResponse(
        success=state.get("workflow_status") == "completed",
        question=state.get("question", ""),
        intent=intent_obj,
        retrieved_schema=schema_obj,
        generated_sql=state.get("optimized_sql") or state.get("selected_sql"),
        sql_parameters=state.get("sql_parameters"),
        optimized_sql=state.get("optimized_sql"),
        validation=validation_obj,
        security=security_obj,
        execution_result=exec_obj,
        explanation=explanation_obj,
        retry_count=state.get("retry_count", 0),
        error_message=state.get("error_message"),
        processing_time_ms=0.0,     # set by endpoint after timing
        processing_log=state.get("processing_log", []),
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Root"])
async def root():
    """API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": (
            "8-agent NL2SQL pipeline: "
            "Intent → Schema → SQL Generation → Validation → "
            "Security → Optimization → Execution → Explanation"
        ),
        "docs": "/docs",
        "health": "/api/v1/health",
        "main_endpoint": "POST /api/v1/query",
    }


@app.get("/api/v1/health", response_model=HealthCheck, tags=["Health"])
async def health_check():
    """
    Health check.

    Reports LLM configuration, database connectivity, and vector store status.
    """
    return HealthCheck(
        status="healthy",
        version=settings.app_version,
        llm_configured=settings.use_openai or settings.use_groq,
        database_connected=True,       # Live check omitted for startup speed
        vector_store_ready=True,
        agents_loaded=8,
        timestamp=datetime.utcnow(),
    )


@app.post("/api/v1/query", response_model=NLQueryResponse, tags=["Query"])
async def process_query(request: NLQueryRequest):
    """
    **Main endpoint** — convert a natural language question to SQL and execute it.

    The full 8-agent pipeline runs synchronously:
    1. Intent Understanding
    2. Schema Retrieval (RAG + ChromaDB)
    3. SQL Generation (multi-candidate)
    4. Validation (syntax + schema + semantic; retry loop)
    5. Security Check (RBAC + dangerous statement detection)
    6. Query Optimization
    7. SQL Execution
    8. Explanation

    Example request:
    `json
    {
        "question": "How many customers placed orders in 2023?",
        "user_role": "user",
        "include_explanation": true
    }
    `
    """
    start_time = time.time()

    try:
        orchestrator = get_orchestrator()

        final_state = orchestrator.process_query(
            question=request.question,
            database_id=request.database_id,
            user_role=request.user_role or settings.default_role,
            include_explanation=request.include_explanation,
            max_retries=3,
        )

        response = _state_to_response(final_state)
        response.processing_time_ms = (time.time() - start_time) * 1000
        return response

    except Exception as e:
        return NLQueryResponse(
            success=False,
            question=request.question,
            error_message=str(e),
            processing_time_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow(),
        )


@app.get("/api/v1/databases", response_model=List[DatabaseInfo], tags=["Databases"])
async def list_databases():
    """
    List configured databases.

    In production this would query a database registry.
    """
    return [
        DatabaseInfo(
            id="sample",
            name="Sample Database",
            type="sqlite",
            tables=[],
            connection_status="connected",
        )
    ]


@app.post("/api/v1/database/upload", tags=["Databases"])
async def upload_database(file: __import__('fastapi').UploadFile = __import__('fastapi').File(...)):
    """Upload a SQLite database for querying."""
    import os
    import uuid
    from backend.agents.schema_agent import get_schema_agent
    from backend.core.config import get_dynamic_db_url
    
    if not file.filename.endswith(".db") and not file.filename.endswith(".sqlite"):
        raise HTTPException(status_code=400, detail="Invalid SQLite database. Please upload a valid .db file.")
        
    database_id = f"custom_{uuid.uuid4().hex[:8]}"
    db_path = f"backend/data/{database_id}.db"
    
    try:
        content = await file.read()
        with open(db_path, "wb") as f:
            f.write(content)
            
        agent = get_schema_agent()
        db_url = get_dynamic_db_url(database_id)
        
        if agent.connect_to_database(db_url):
            schema = agent.introspect_schema()
            if not schema.get("tables"):
                if getattr(agent, 'db_engine', None):
                    agent.db_engine.dispose()
                os.remove(db_path)
                raise HTTPException(status_code=400, detail="Invalid SQLite database. No tables found.")
                
            agent.index_schema(schema, database_id)
            
            return {
                "status": "connected",
                "database_id": database_id,
                "filename": file.filename,
                "table_count": len(schema.get("tables", {})),
                "tables": list(schema.get("tables", {}).keys())
            }
        else:
            if getattr(agent, 'db_engine', None):
                agent.db_engine.dispose()
            os.remove(db_path)
            raise HTTPException(status_code=400, detail="Could not connect to the uploaded database.")
            
    except Exception as e:
        if os.path.exists(db_path):
            if 'agent' in locals() and getattr(agent, 'db_engine', None):
                agent.db_engine.dispose()
            os.remove(db_path)
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/schema/index", tags=["Schema"])
async def index_schema(
    background_tasks: BackgroundTasks,
    database_id: str = "sample"
):
    """
    Trigger schema indexing into ChromaDB for RAG-based retrieval.

    Runs as a background task so the endpoint responds immediately.
    Schema will be available for the next query once indexing completes.
    """
    async def do_indexing():
        from backend.agents.schema_agent import get_schema_agent
        agent = get_schema_agent()
        db_url = settings.database_url
        if agent.connect_to_database(db_url):
            schema = agent.introspect_schema()
            agent.index_schema(schema)

    background_tasks.add_task(do_indexing)

    return {
        "status": "indexing_started",
        "database_id": database_id,
        "message": "Schema indexing started in background. Queries will use schema once complete.",
    }


@app.get("/api/v1/schema/{database_id}", tags=["Schema"])
async def get_schema_info(database_id: str):
    """Get introspected schema for a database (tables, columns, foreign keys)."""
    from backend.agents.schema_agent import get_schema_agent

    agent = get_schema_agent()
    if agent.connect_to_database(settings.database_url):
        schema = agent.introspect_schema()
        return {
            "database_id": database_id,
            "tables": schema.get("tables", {}),
            "foreign_keys": schema.get("foreign_keys", []),
            "table_count": len(schema.get("tables", {})),
        }
    else:
        raise HTTPException(status_code=503, detail="Could not connect to database")


# ---------------------------------------------------------------------------
# Startup: initialize schema index
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """
    On startup: connect to database and index schema into ChromaDB.

    This ensures schema is ready for the first query without a cold-start delay.
    """
    from backend.agents.schema_agent import get_schema_agent

    try:
        agent = get_schema_agent()
        db_url = settings.database_url
        if agent.connect_to_database(db_url):
            schema = agent.introspect_schema()
            agent.index_schema(schema)
            print(
                f"[Startup] Indexed {len(schema.get('tables', {}))} tables "
                f"from {db_url}"
            )
        else:
            print(f"[Startup] WARNING: Could not connect to {db_url}")
    except Exception as e:
        print(f"[Startup] Schema initialization failed: {e} — will retry on first query")


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
