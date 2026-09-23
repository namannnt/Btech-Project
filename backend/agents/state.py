"""
LangGraph State definition for the NL2SQL Multi-Agent System.

Defines the shared AgentState TypedDict that flows through all 8 agents in the graph.
Each agent reads from and writes to this state, enabling conditional routing and loops.

8-agent pipeline:
1. Intent Understanding
2. Schema Retrieval
3. SQL Generation
4. Validation          <- retry loop targets here
5. Security Check      <- execution gate
6. Query Optimization
7. SQL Execution
8. Explanation
"""

from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict):
    """
    Shared state object passed between all 8 agents in the LangGraph workflow.

    Each agent is a node that transforms this state.
    Conditional edges route based on state values (e.g., validation failures loop back,
    security failures terminate early).
    """

    # -------------------------------------------------------------------------
    # Input
    # -------------------------------------------------------------------------
    question: str                          # Original natural language question

    # -------------------------------------------------------------------------
    # Agent 1: Intent Understanding output
    # -------------------------------------------------------------------------
    intent: Optional[Dict[str, Any]]       # Parsed entities, conditions, operations
    intent_confidence: float               # Confidence score from intent agent

    # -------------------------------------------------------------------------
    # Agent 2: Schema Retrieval output
    # -------------------------------------------------------------------------
    relevant_tables: List[str]             # Tables identified as relevant
    table_schemas: Dict[str, Any]          # Schema information for relevant tables
    foreign_keys: List[Dict[str, str]]     # Relationships between tables
    schema_relevance_scores: Dict[str, float]  # Per-table relevance scores

    # -------------------------------------------------------------------------
    # Agent 3: SQL Generation output
    # -------------------------------------------------------------------------
    sql_candidates: List[Dict[str, Any]]   # Multiple candidate SQL queries
    selected_sql: Optional[str]            # Best validated candidate
    generation_metadata: Dict[str, Any]    # Metadata about the generation step

    # -------------------------------------------------------------------------
    # Agent 4: Validation output
    # -------------------------------------------------------------------------
    validation_result: Optional[Dict[str, Any]]  # Per-dimension validation details
    is_valid: bool                         # Overall validation status
    validation_errors: List[str]           # List of validation error messages
    retry_count: int                       # Number of SQL generation retry attempts

    # -------------------------------------------------------------------------
    # Agent 5: Security / Permission Check output
    # -------------------------------------------------------------------------
    security_result: Optional[Dict[str, Any]]  # Full security audit record
    security_passed: bool                  # Whether security check was approved
    security_errors: List[str]             # Security violation messages

    # -------------------------------------------------------------------------
    # Agent 6: Query Optimization output
    # -------------------------------------------------------------------------
    original_sql: Optional[str]            # SQL before optimization
    optimized_sql: Optional[str]           # SQL after optimization
    optimizations_applied: List[str]       # List of optimizations performed

    # -------------------------------------------------------------------------
    # Agent 7: SQL Execution output
    # -------------------------------------------------------------------------
    execution_success: bool                # Whether execution succeeded
    query_results: Optional[List[Any]]     # Result rows from database
    result_columns: List[str]              # Column names from result set
    execution_time_ms: float               # Query execution time in milliseconds
    execution_error: Optional[str]         # Error message if execution failed

    # -------------------------------------------------------------------------
    # Agent 8: Explanation output
    # -------------------------------------------------------------------------
    sql_explanation: Optional[str]         # Plain English explanation of the SQL
    result_summary: Optional[str]          # Summary of query results
    insights: List[str]                    # Key insights extracted from the results

    # -------------------------------------------------------------------------
    # Orchestration & Control
    # -------------------------------------------------------------------------
    current_agent: str                     # Name of the currently-executing agent
    workflow_status: str                   # "running" | "completed" | "failed"
    error_message: Optional[str]           # Global error message (if any)
    processing_log: List[str]              # Ordered log of all processing steps

    # -------------------------------------------------------------------------
    # Context & Configuration
    # -------------------------------------------------------------------------
    database_id: Optional[str]             # Target database identifier
    user_role: str                         # User role for permission checking
    include_explanation: bool              # Whether to generate explanation
    max_retries: int                       # Maximum retry attempts for validation failure


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def initialize_state(question: str, **kwargs: Any) -> AgentState:
    """
    Initialize a fresh AgentState for a new query.

    Args:
        question: The natural language question to process
        **kwargs: Optional overrides for database_id, user_role,
                  include_explanation, max_retries

    Returns:
        A fully initialized AgentState ready for the first agent
    """
    return AgentState(
        # Input
        question=question,
        # Agent 1
        intent=None,
        intent_confidence=0.0,
        # Agent 2
        relevant_tables=[],
        table_schemas={},
        foreign_keys=[],
        schema_relevance_scores={},
        # Agent 3
        sql_candidates=[],
        selected_sql=None,
        generation_metadata={},
        # Agent 4
        validation_result=None,
        is_valid=False,
        validation_errors=[],
        retry_count=0,
        # Agent 5
        security_result=None,
        security_passed=False,
        security_errors=[],
        # Agent 6
        original_sql=None,
        optimized_sql=None,
        optimizations_applied=[],
        # Agent 7
        execution_success=False,
        query_results=None,
        result_columns=[],
        execution_time_ms=0.0,
        execution_error=None,
        # Agent 8
        sql_explanation=None,
        result_summary=None,
        insights=[],
        # Orchestration
        current_agent="initialization",
        workflow_status="running",
        error_message=None,
        processing_log=[f"Initialized pipeline for question: {question[:100]}"],
        # Configuration
        database_id=kwargs.get("database_id"),
        user_role=kwargs.get("user_role", "user"),
        include_explanation=kwargs.get("include_explanation", True),
        max_retries=kwargs.get("max_retries", 3),
    )


def add_to_processing_log(state: AgentState, message: str) -> AgentState:
    """Append a message to the processing log."""
    state["processing_log"].append(message)
    return state


def mark_workflow_complete(state: AgentState, success: bool = True) -> AgentState:
    """Mark the workflow as complete (success or failure)."""
    state["workflow_status"] = "completed" if success else "failed"
    return state


def should_retry_generation(state: AgentState) -> bool:
    """
    Determine whether SQL generation should be retried.

    Returns True when:
    - Validation failed
    - Retry attempts remaining
    - Workflow still running
    """
    return (
        not state["is_valid"]
        and state["retry_count"] < state["max_retries"]
        and state["workflow_status"] == "running"
    )
