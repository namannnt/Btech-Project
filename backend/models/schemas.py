"""Pydantic models for request/response schemas.

All model names and field names are kept consistent with:
- AgentState field names in backend/agents/state.py
- FastAPI response models in backend/api/main.py
- Frontend parsing in frontend/app.py
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class IntentUnderstanding(BaseModel):
    """Agent 1 output: parsed intent from natural language question."""
    entities: List[str] = Field(default_factory=list)
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    operations: List[str] = Field(default_factory=list)
    question_type: str = "unknown"
    confidence: float = 0.0
    ambiguous_terms: List[str] = Field(default_factory=list)
    reasoning: str = ""


class SchemaRetrievalResult(BaseModel):
    """Agent 2 output: relevant schema retrieved via RAG."""
    relevant_tables: List[str] = Field(default_factory=list)
    table_schemas: Dict[str, Any] = Field(default_factory=dict)
    foreign_keys: List[Dict[str, str]] = Field(default_factory=list)
    relevance_scores: Dict[str, float] = Field(default_factory=dict)


class SQLCandidate(BaseModel):
    """A single generated SQL candidate with confidence and explanation."""
    sql: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    explanation: str = ""


class SQLGenerationResult(BaseModel):
    """Agent 3 output: multiple SQL candidates."""
    candidates: List[SQLCandidate] = Field(default_factory=list)
    selected_candidate: Optional[SQLCandidate] = None
    generation_metadata: Dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Agent 4 output: multi-dimension validation result."""
    is_valid: bool = False
    syntax_valid: bool = False
    schema_valid: bool = False
    semantic_valid: bool = False           # Was missing — now required
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    evaluated_candidates: int = 0
    best_candidate: Optional[SQLCandidate] = None

    class Config:
        extra = "ignore"                   # Tolerate unknown fields from state


class SecurityResult(BaseModel):
    """Agent 5 output: security audit record."""
    passed: bool = False
    role: str = "user"
    decision: str = "REJECTED"
    violations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timestamp: str = ""
    sql_preview: str = ""

    class Config:
        extra = "ignore"


class OptimizedSQL(BaseModel):
    """Agent 6 output: optimized SQL with change log."""
    original_sql: str
    optimized_sql: str
    optimizations_applied: List[str] = Field(default_factory=list)
    performance_notes: str = ""


class QueryExecutionResult(BaseModel):
    """Agent 7 output: SQL execution result set."""
    success: bool = False
    columns: List[str] = Field(default_factory=list)
    rows: List[Any] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None
    warning: Optional[str] = None


class ExplanationResult(BaseModel):
    """Agent 8 output: plain-English explanation of SQL and results."""
    sql_explanation: str = ""
    result_summary: str = ""
    insights: List[str] = Field(default_factory=list)


class NLQueryRequest(BaseModel):
    """Request body for POST /api/v1/query."""
    question: str = Field(..., min_length=1, max_length=1000)
    database_id: Optional[str] = None
    user_role: Optional[str] = "user"
    include_explanation: bool = True
    include_sql_only: bool = False


class NLQueryResponse(BaseModel):
    """
    Response body for POST /api/v1/query.

    All 8 agent outputs are included, making the full pipeline transparent.
    Fields are named consistently with AgentState to simplify the mapping.
    """
    success: bool = False
    question: str = ""

    # Agent outputs (all optional — may be absent if pipeline fails early)
    intent: Optional[IntentUnderstanding] = None
    retrieved_schema: Optional[SchemaRetrievalResult] = None
    generated_sql: Optional[str] = None           # = optimized_sql or selected_sql
    sql_parameters: Optional[Dict[str, Any]] = None
    optimized_sql: Optional[str] = None
    validation: Optional[ValidationResult] = None
    security: Optional[SecurityResult] = None      # NEW: security agent output
    execution_result: Optional[QueryExecutionResult] = None
    explanation: Optional[ExplanationResult] = None

    # Pipeline metadata
    retry_count: int = 0
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0
    processing_log: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DatabaseInfo(BaseModel):
    """Information about an available database."""
    id: str
    name: str
    type: str                    # "postgres" | "mysql" | "sqlite"
    tables: List[str] = Field(default_factory=list)
    connection_status: str = "unknown"


class HealthCheck(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "0.1.0"
    llm_configured: bool = False
    database_connected: bool = False
    vector_store_ready: bool = False
    agents_loaded: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
