"""
LangGraph Orchestrator for NL2SQL Multi-Agent System

This module creates the stateful graph that orchestrates all 7 agents:
1. Intent Understanding → 2. Schema Retrieval → 3. SQL Generation → 
4. Validation → [if fails: back to SQL Generation] → 
5. Query Optimization → 6. SQL Execution → 7. Explanation

The key innovation is the conditional edge from Validation back to SQL Generation,
which implements the validation loop that differentiates this from simple pipelines.
"""

from typing import Literal
from langgraph.graph import StateGraph, END
from backend.agents.state import AgentState, initialize_state, should_retry_generation
from backend.agents.intent_agent import get_intent_agent
from backend.agents.schema_agent import get_schema_agent
from backend.agents.sql_generation_agent import get_sql_generation_agent
from backend.agents.validation_agent import get_validation_agent
from backend.agents.other_agents import (
    get_optimization_agent,
    get_execution_agent,
    get_explanation_agent
)


class NL2SQLOrchestrator:
    """
    Main orchestrator that wires all agents into a LangGraph workflow.
    
    This implements the stateful graph architecture where:
    - Each agent is a node that transforms the shared state
    - Conditional edges route based on validation results
    - The graph supports loops (validation failure → retry generation)
    """
    
    def __init__(self):
        """Initialize the orchestrator and build the graph."""
        self.graph = self._build_graph()
        
        # Initialize all agents
        self.intent_agent = get_intent_agent()
        self.schema_agent = get_schema_agent()
        self.sql_generation_agent = get_sql_generation_agent()
        self.validation_agent = get_validation_agent()
        self.optimization_agent = get_optimization_agent()
        self.execution_agent = get_execution_agent()
        self.explanation_agent = get_explanation_agent()
    
    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph state machine with all agents and conditional edges.
        
        Graph structure:
        ```
        START → Intent → Schema → SQL Generation → Validation 
                                              ↓ (if invalid & retries left)
                                          SQL Generation (retry)
                                              ↓ (if valid)
                                        Optimization → Execution → Explanation → END
        ```
        """
        # Create the graph
        workflow = StateGraph(AgentState)
        
        # Add nodes for each agent
        workflow.add_node("intent_understanding", self.intent_agent.invoke)
        workflow.add_node("schema_retrieval", self.schema_agent.invoke)
        workflow.add_node("sql_generation", self.sql_generation_agent.invoke)
        workflow.add_node("validation", self.validation_agent.invoke)
        workflow.add_node("optimization", self.optimization_agent.invoke)
        workflow.add_node("execution", self.execution_agent.invoke)
        workflow.add_node("explanation", self.explanation_agent.invoke)
        
        # Set entry point
        workflow.set_entry_point("intent_understanding")
        
        # Add edges between nodes
        workflow.add_edge("intent_understanding", "schema_retrieval")
        workflow.add_edge("schema_retrieval", "sql_generation")
        
        # CRITICAL: Conditional edge from validation
        # This is what makes it a graph, not just a pipeline
        workflow.add_conditional_edges(
            source="validation",
            path=self._validate_or_retry,
            path_map={
                "retry": "sql_generation",
                "proceed": "optimization",
                "fail": END
            }
        )
        
        # Continue the flow after optimization
        workflow.add_edge("optimization", "execution")
        workflow.add_edge("execution", "explanation")
        workflow.add_edge("explanation", END)
        
        # Compile the graph
        app = workflow.compile()
        
        return app
    
    def _validate_or_retry(self, state: AgentState) -> Literal["retry", "proceed", "fail"]:
        """
        Conditional edge function that determines next step after validation.
        
        This implements the core logic of the validation loop:
        - If validation failed AND retries available → retry SQL generation
        - If validation passed → proceed to optimization
        - If validation failed AND no retries left → fail
        
        Args:
            state: Current agent state
            
        Returns:
            Next step: "retry", "proceed", or "fail"
        """
        is_valid = state.get("is_valid", False)
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        workflow_status = state.get("workflow_status", "running")
        
        # Check if we should retry
        if not is_valid and retry_count < max_retries and workflow_status == "running":
            return "retry"
        
        # Check if we can proceed
        if is_valid and workflow_status == "running":
            return "proceed"
        
        # Otherwise fail
        return "fail"
    
    def process_query(
        self,
        question: str,
        database_id: str = None,
        user_role: str = "user",
        include_explanation: bool = True,
        max_retries: int = 3
    ) -> AgentState:
        """
        Process a natural language query through the entire workflow.
        
        Args:
            question: Natural language question from user
            database_id: Optional database identifier
            user_role: User role for permission checking
            include_explanation: Whether to generate explanation
            max_retries: Maximum retry attempts for failed validation
            
        Returns:
            Final agent state with all results
        """
        # Initialize state
        initial_state = initialize_state(
            question=question,
            database_id=database_id,
            user_role=user_role,
            include_explanation=include_explanation,
            max_retries=max_retries
        )
        
        # Run the graph
        try:
            final_state = self.graph.invoke(initial_state)
            return final_state
        except Exception as e:
            # Handle graph execution errors
            initial_state["error_message"] = str(e)
            initial_state["workflow_status"] = "failed"
            initial_state["processing_log"].append(f"Graph execution error: {e}")
            return initial_state
    
    def stream_query(
        self,
        question: str,
        **kwargs
    ):
        """
        Stream the query processing step-by-step.
        
        This yields intermediate states, useful for showing progress to user.
        
        Args:
            question: Natural language question
            **kwargs: Additional arguments for process_query
            
        Yields:
            Tuple of (node_name, state) for each step
        """
        initial_state = initialize_state(question=question, **kwargs)
        
        try:
            for output in self.graph.stream(initial_state):
                for node_name, state in output.items():
                    yield node_name, state
        except Exception as e:
            yield "error", {"error_message": str(e)}


# Singleton instance
_orchestrator_instance = None


def get_orchestrator() -> NL2SQLOrchestrator:
    """Get or create the orchestrator singleton."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = NL2SQLOrchestrator()
    return _orchestrator_instance


# Convenience function for simple usage
def nl2sql(query: str, **kwargs) -> dict:
    """
    Simple function to convert natural language to SQL and execute.
    
    Args:
        query: Natural language question
        **kwargs: Additional parameters
        
    Returns:
        Dictionary with SQL, results, and explanation
    """
    orchestrator = get_orchestrator()
    final_state = orchestrator.process_query(query, **kwargs)
    
    return {
        "success": final_state.get("workflow_status") == "completed",
        "question": final_state.get("question"),
        "generated_sql": final_state.get("optimized_sql") or final_state.get("selected_sql"),
        "results": final_state.get("query_results"),
        "columns": final_state.get("result_columns"),
        "explanation": final_state.get("sql_explanation"),
        "result_summary": final_state.get("result_summary"),
        "execution_time_ms": final_state.get("execution_time_ms"),
        "error_message": final_state.get("error_message"),
        "processing_log": final_state.get("processing_log", [])
    }


if __name__ == "__main__":
    # Test the orchestrator
    print("Testing NL2SQL Orchestrator\n" + "=" * 50)
    
    # Note: This requires LLM API keys to be set
    # For testing without API keys, we'll just show the graph structure
    
    orchestrator = get_orchestrator()
    
    print("\n✓ Orchestrator initialized successfully")
    print(f"✓ Graph has {len(orchestrator.graph.nodes)} nodes")
    print("\nGraph structure:")
    print("  START → Intent → Schema → SQL Generation → Validation")
    print("                                    ↑              ↓")
    print("                              (retry if fail)  Optimization")
    print("                                                      ↓")
    print("                                               Execution → Explanation → END")
    
    # Try a simple query if API keys are configured
    import os
    if os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY"):
        print("\n" + "=" * 50)
        print("LLM configured. Testing with a sample query...")
        print("=" * 50)
        
        test_question = "Show me all customers"
        print(f"\nQuestion: {test_question}\n")
        
        result = nl2sql(test_question)
        
        print(f"Success: {result['success']}")
        print(f"Generated SQL: {result.get('generated_sql', 'N/A')}")
        print(f"Results: {len(result.get('results', []))} rows")
        print(f"Explanation: {result.get('explanation', 'N/A')[:200]}...")
        
        if result.get('error_message'):
            print(f"Error: {result['error_message']}")
    else:
        print("\n⚠ No LLM API keys configured.")
        print("Set OPENAI_API_KEY or GROQ_API_KEY in .env to test full functionality.")
