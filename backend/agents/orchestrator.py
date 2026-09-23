"""
LangGraph Orchestrator for the NL2SQL 8-Agent System

This module builds and runs the stateful LangGraph workflow that orchestrates
all 8 agents in the correct order:

1. Intent Understanding
2. Schema Retrieval
3. SQL Generation
4. Validation          <- conditional retry loop
5. Security Check      <- early-exit gate if rejected
6. Query Optimization
7. SQL Execution
8. Explanation

The key innovations:
- Conditional retry edge: Validation failure routes back to SQL Generation
- Security gate: Execution is prevented unless security_passed=True
- Retry counting with max_retries limit prevents infinite loops
"""

from typing import Literal
from langgraph.graph import StateGraph, END
from backend.agents.state import AgentState, initialize_state
from backend.agents.intent_agent import get_intent_agent
from backend.agents.schema_agent import get_schema_agent
from backend.agents.sql_generation_agent import get_sql_generation_agent
from backend.agents.validation_agent import get_validation_agent
from backend.agents.security_agent import get_security_agent
from backend.agents.optimization_agent import get_optimization_agent
from backend.agents.execution_agent import get_execution_agent
from backend.agents.explanation_agent import get_explanation_agent


class NL2SQLOrchestrator:
    """
    Main orchestrator that wires all 8 agents into a LangGraph workflow.

    Graph architecture:
    - Each agent is a node that transforms the shared AgentState
    - Conditional edges implement the validation retry loop
    - Security gate prevents execution of unapproved SQL
    """

    def __init__(self) -> None:
        """Initialize all agents and build the LangGraph workflow."""
        # Agent singletons
        self.intent_agent = get_intent_agent()
        self.schema_agent = get_schema_agent()
        self.sql_generation_agent = get_sql_generation_agent()
        self.validation_agent = get_validation_agent()
        self.security_agent = get_security_agent()
        self.optimization_agent = get_optimization_agent()
        self.execution_agent = get_execution_agent()
        self.explanation_agent = get_explanation_agent()

        # Build and compile the graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph state machine.

        Graph flow:
        START -> intent -> schema -> sql_generation -> validation
                                           ^                |
                                           |  (retry)       | (valid)
                              sql_generation_retry <- ------+
                                                            |
                                                        security
                                                            |
                                               (pass) -----+-----> optimization
                                               (fail)              -> execution
                                                   |               -> explanation -> END
                                                  END (fail)
        """
        workflow = StateGraph(AgentState)

        # ----------------------------------------------------------------
        # Nodes — one per agent
        # ----------------------------------------------------------------
        workflow.add_node("intent_understanding", self.intent_agent.invoke)
        workflow.add_node("schema_retrieval", self.schema_agent.invoke)
        workflow.add_node("sql_generation", self.sql_generation_agent.invoke)
        workflow.add_node(
            "sql_generation_retry",
            lambda state: self.sql_generation_agent.retry_generation(
                state, state.get("validation_errors", [])
            )
        )
        workflow.add_node("validation", self.validation_agent.invoke)
        workflow.add_node("security_check", self.security_agent.invoke)
        workflow.add_node("optimization", self.optimization_agent.invoke)
        workflow.add_node("execution", self.execution_agent.invoke)
        workflow.add_node("explanation", self.explanation_agent.invoke)

        # ----------------------------------------------------------------
        # Entry point
        # ----------------------------------------------------------------
        workflow.set_entry_point("intent_understanding")

        # ----------------------------------------------------------------
        # Linear edges (no branching needed)
        # ----------------------------------------------------------------
        workflow.add_edge("intent_understanding", "schema_retrieval")
        workflow.add_edge("schema_retrieval", "sql_generation")
        workflow.add_edge("sql_generation", "validation")

        # After retry, go back to validation (not directly to sql_generation)
        workflow.add_edge("sql_generation_retry", "validation")

        workflow.add_edge("optimization", "execution")
        workflow.add_edge("execution", "explanation")
        workflow.add_edge("explanation", END)

        # ----------------------------------------------------------------
        # Conditional edge: Validation -> retry | security | fail
        # ----------------------------------------------------------------
        workflow.add_conditional_edges(
            source="validation",
            path=self._route_after_validation,
            path_map={
                "retry": "sql_generation_retry",
                "proceed_to_security": "security_check",
                "fail": END,
            }
        )

        # ----------------------------------------------------------------
        # Conditional edge: Security -> optimization | fail
        # ----------------------------------------------------------------
        workflow.add_conditional_edges(
            source="security_check",
            path=self._route_after_security,
            path_map={
                "proceed_to_optimization": "optimization",
                "security_fail": END,
            }
        )

        return workflow.compile()

    # ------------------------------------------------------------------
    # Conditional routing functions
    # ------------------------------------------------------------------

    def _route_after_validation(
        self, state: AgentState
    ) -> Literal["retry", "proceed_to_security", "fail"]:
        """
        Determine next step after validation.

        Logic:
        - is_valid=True -> proceed to security check
        - is_valid=False AND retries remaining -> retry SQL generation
        - is_valid=False AND no retries left -> fail
        """
        is_valid = state.get("is_valid", False)
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        workflow_status = state.get("workflow_status", "running")

        if is_valid and workflow_status == "running":
            return "proceed_to_security"

        if not is_valid and retry_count < max_retries and workflow_status == "running":
            return "retry"

        return "fail"

    def _route_after_security(
        self, state: AgentState
    ) -> Literal["proceed_to_optimization", "security_fail"]:
        """
        Determine next step after security check.

        Logic:
        - security_passed=True -> proceed to optimization
        - security_passed=False -> fail immediately (no retry for security violations)
        """
        if state.get("security_passed", False):
            return "proceed_to_optimization"
        return "security_fail"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_query(
        self,
        question: str,
        database_id: Optional[str] = None,
        user_role: str = "user",
        include_explanation: bool = True,
        max_retries: int = 3
    ) -> AgentState:
        """
        Process a natural language query through the complete 8-agent workflow.

        Args:
            question: Natural language question from user
            database_id: Optional target database identifier
            user_role: User role for security/permission checking
            include_explanation: Whether to generate plain-English explanation
            max_retries: Maximum retry attempts for failed validation

        Returns:
            Final AgentState containing all agent outputs
        """
        initial_state = initialize_state(
            question=question,
            database_id=database_id,
            user_role=user_role,
            include_explanation=include_explanation,
            max_retries=max_retries
        )

        try:
            final_state = self.graph.invoke(initial_state)
            # Mark as completed if not already failed
            if final_state.get("workflow_status") == "running":
                final_state["workflow_status"] = "completed"
            return final_state
        except Exception as e:
            initial_state["error_message"] = str(e)
            initial_state["workflow_status"] = "failed"
            initial_state["processing_log"].append(f"Graph execution error: {e}")
            return initial_state

    def stream_query(self, question: str, **kwargs):
        """
        Stream query processing step-by-step.

        Yields intermediate states for each completed node, useful for
        showing agent-by-agent progress in the frontend.

        Args:
            question: Natural language question
            **kwargs: Additional arguments passed to initialize_state

        Yields:
            Tuple of (node_name, partial_state)
        """
        initial_state = initialize_state(question=question, **kwargs)

        try:
            for output in self.graph.stream(initial_state):
                for node_name, state in output.items():
                    yield node_name, state
        except Exception as e:
            yield "error", {"error_message": str(e)}


# ---------------------------------------------------------------------------
# Type import (Optional needs to be available at runtime)
# ---------------------------------------------------------------------------
from typing import Optional


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

_orchestrator_instance: Optional[NL2SQLOrchestrator] = None


def get_orchestrator() -> NL2SQLOrchestrator:
    """Get or create the orchestrator singleton."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = NL2SQLOrchestrator()
    return _orchestrator_instance


def nl2sql(query: str, **kwargs) -> dict:
    """
    Convenience function: convert natural language to SQL and execute.

    Args:
        query: Natural language question
        **kwargs: Additional parameters (user_role, database_id, etc.)

    Returns:
        Dictionary with all pipeline results
    """
    orchestrator = get_orchestrator()
    final_state = orchestrator.process_query(query, **kwargs)

    return {
        "success": final_state.get("workflow_status") == "completed",
        "question": final_state.get("question"),
        "selected_sql": final_state.get("selected_sql"),
        "generated_sql": final_state.get("optimized_sql") or final_state.get("selected_sql"),
        "optimized_sql": final_state.get("optimized_sql"),
        "results": final_state.get("query_results"),
        "columns": final_state.get("result_columns"),
        "sql_explanation": final_state.get("sql_explanation"),
        "result_summary": final_state.get("result_summary"),
        "insights": final_state.get("insights"),
        "validation_result": final_state.get("validation_result"),
        "security_result": final_state.get("security_result"),
        "security_passed": final_state.get("security_passed"),
        "execution_time_ms": final_state.get("execution_time_ms"),
        "retry_count": final_state.get("retry_count"),
        "error_message": final_state.get("error_message"),
        "processing_log": final_state.get("processing_log", []),
    }
