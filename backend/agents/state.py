"""
LangGraph State definition for the NL2SQL Multi-Agent System.

This defines the shared state object that flows through all agents in the graph.
Each agent reads from and writes to this state, enabling conditional routing and loops.
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    Shared state object passed between all agents in the LangGraph workflow.
    
    This implements the stateful graph architecture mentioned in our methodology:
    - Each agent is a node that transforms this state
    - Conditional edges route based on state values (e.g., validation failures loop back)
    - State persists across the entire workflow execution
    """
    
    # Input
    question: str  # Original natural language question
    
    # Agent 1: Intent Understanding Output
    intent: Optional[Dict[str, Any]]  # Parsed entities, conditions, operations
    intent_confidence: float  # Confidence score from intent agent
    
    # Agent 2: Schema Retrieval Output
    relevant_tables: List[str]  # Tables identified as relevant
    table_schemas: Dict[str, Any]  # Schema information for relevant tables
    foreign_keys: List[Dict[str, str]]  # Relationships between tables
    schema_relevance_scores: Dict[str, float]  # Relevance scores for each table
    
    # Agent 3: SQL Generation Output
    sql_candidates: List[Dict[str, Any]]  # Multiple candidate SQL queries
    selected_sql: Optional[str]  # Best candidate selected
    generation_metadata: Dict[str, Any]  # Metadata about generation process
    
    # Agent 4: Validation Output
    validation_result: Optional[Dict[str, Any]]  # Validation details
    is_valid: bool  # Overall validation status
    validation_errors: List[str]  # List of validation errors
    retry_count: int  # Number of retry attempts for SQL generation
    
    # Agent 5: Query Optimization Output
    original_sql: Optional[str]  # SQL before optimization
    optimized_sql: Optional[str]  # SQL after optimization
    optimizations_applied: List[str]  # List of optimizations performed
    
    # Agent 6: SQL Execution Output
    execution_success: bool  # Whether execution succeeded
    query_results: Optional[List[Any]]  # Result rows from database
    result_columns: List[str]  # Column names from result
    execution_time_ms: float  # Query execution time
    execution_error: Optional[str]  # Error message if execution failed
    
    # Agent 7: Explanation Output
    sql_explanation: Optional[str]  # Plain English explanation of SQL
    result_summary: Optional[str]  # Summary of query results
    insights: List[str]  # Key insights from the results
    
    # Orchestration & Control
    current_agent: str  # Name of current agent being executed
    workflow_status: str  # Overall workflow status (running, completed, failed)
    error_message: Optional[str]  # Global error message
    processing_log: List[str]  # Log of processing steps for debugging
    
    # Context & Configuration
    database_id: Optional[str]  # Target database identifier
    user_role: str  # User role for permission checking
    include_explanation: bool  # Whether to generate explanation
    max_retries: int  # Maximum retry attempts for failed validation


# Helper functions for state management
def initialize_state(question: str, **kwargs) -> AgentState:
    """Initialize a new AgentState with the given question and optional parameters."""
    return AgentState(
        question=question,
        intent=None,
        intent_confidence=0.0,
        relevant_tables=[],
        table_schemas={},
        foreign_keys=[],
        schema_relevance_scores={},
        sql_candidates=[],
        selected_sql=None,
        generation_metadata={},
        validation_result=None,
        is_valid=False,
        validation_errors=[],
        retry_count=0,
        original_sql=None,
        optimized_sql=None,
        optimizations_applied=[],
        execution_success=False,
        query_results=None,
        result_columns=[],
        execution_time_ms=0.0,
        execution_error=None,
        sql_explanation=None,
        result_summary=None,
        insights=[],
        current_agent="initialization",
        workflow_status="running",
        error_message=None,
        processing_log=[f"Initialized with question: {question}"],
        database_id=kwargs.get("database_id"),
        user_role=kwargs.get("user_role", "user"),
        include_explanation=kwargs.get("include_explanation", True),
        max_retries=kwargs.get("max_retries", 3)
    )


def add_to_processing_log(state: AgentState, message: str) -> AgentState:
    """Add a message to the processing log."""
    state["processing_log"].append(message)
    return state


def mark_workflow_complete(state: AgentState, success: bool = True) -> AgentState:
    """Mark the workflow as complete with success/failure status."""
    state["workflow_status"] = "completed" if success else "failed"
    return state


def should_retry_generation(state: AgentState) -> bool:
    """Determine if SQL generation should be retried based on validation failure."""
    return (
        not state["is_valid"] 
        and state["retry_count"] < state["max_retries"]
        and state["workflow_status"] == "running"
    )
