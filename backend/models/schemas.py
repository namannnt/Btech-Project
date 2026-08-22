"""Pydantic models for request/response schemas."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class IntentUnderstanding(BaseModel):
    """Schema for intent understanding output."""
    entities: List[str] = Field(default_factory=list)
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    operations: List[str] = Field(default_factory=list)
    question_type: str = "unknown"
    confidence: float = 0.0


class SchemaRetrievalResult(BaseModel):
    """Schema for schema retrieval output."""
    relevant_tables: List[str] = Field(default_factory=list)
    table_schemas: Dict[str, Any] = Field(default_factory=dict)
    foreign_keys: List[Dict[str, str]] = Field(default_factory=list)
    relevance_scores: Dict[str, float] = Field(default_factory=dict)


class SQLCandidate(BaseModel):
    """Schema for a single SQL candidate."""
    sql: str
    confidence: float = 0.0
    explanation: str = ""


class SQLGenerationResult(BaseModel):
    """Schema for SQL generation output."""
    candidates: List[SQLCandidate] = Field(default_factory=list)
    selected_candidate: Optional[SQLCandidate] = None
    generation_metadata: Dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Schema for validation output."""
    is_valid: bool = False
    syntax_valid: bool = False
    permission_valid: bool = False
    schema_valid: bool = False
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    best_candidate: Optional[SQLCandidate] = None


class OptimizedSQL(BaseModel):
    """Schema for query optimization output."""
    original_sql: str
    optimized_sql: str
    optimizations_applied: List[str] = Field(default_factory=list)
    performance_notes: str = ""


class QueryExecutionResult(BaseModel):
    """Schema for query execution output."""
    success: bool = False
    columns: List[str] = Field(default_factory=list)
    rows: List[Any] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None


class ExplanationResult(BaseModel):
    """Schema for explanation output."""
    sql_explanation: str = ""
    result_summary: str = ""
    insights: List[str] = Field(default_factory=list)


class NLQueryRequest(BaseModel):
    """Request schema for natural language to SQL conversion."""
    question: str = Field(..., min_length=1, max_length=1000)
    database_id: Optional[str] = None
    user_role: Optional[str] = "user"
    include_explanation: bool = True
    include_sql_only: bool = False


class NLQueryResponse(BaseModel):
    """Response schema for natural language to SQL conversion."""
    success: bool = False
    question: str = ""
    intent: Optional[IntentUnderstanding] = None
    retrieved_schema: Optional[SchemaRetrievalResult] = None
    generated_sql: Optional[str] = None
    optimized_sql: Optional[str] = None
    validation: Optional[ValidationResult] = None
    execution_result: Optional[QueryExecutionResult] = None
    explanation: Optional[ExplanationResult] = None
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DatabaseInfo(BaseModel):
    """Schema for database information."""
    id: str
    name: str
    type: str  # postgres, mysql, sqlite
    tables: List[str] = Field(default_factory=list)
    connection_status: str = "unknown"


class HealthCheck(BaseModel):
    """Schema for health check response."""
    status: str = "healthy"
    version: str = "0.1.0"
    llm_configured: bool = False
    database_connected: bool = False
    vector_store_ready: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
