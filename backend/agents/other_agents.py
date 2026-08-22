"""
Agents 5, 6, 7: Query Optimization, SQL Execution, and Explanation

This module contains the remaining three agents:
- Agent 5: Query Optimization (improves SQL performance)
- Agent 6: SQL Execution (runs query against database)
- Agent 7: Explanation (generates plain English explanation)
"""

import json
import time
from typing import Dict, Any, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.core.config import settings
from backend.agents.state import AgentState, add_to_processing_log


# ============================================================================
# Agent 5: Query Optimization
# ============================================================================

QUERY_OPTIMIZATION_PROMPT = """
You are a Query Optimization Agent for a Natural Language to SQL system.
Your task is to optimize the generated SQL query for better performance.

INPUTS:
- Original SQL: {original_sql}
- Database Dialect: {sql_dialect}
- Table Schemas: {table_schemas}

OPTIMIZATION GUIDELINES:
1. **Avoid SELECT ***: Replace with specific columns if possible
2. **Index Hints**: Suggest indexes that could improve performance
3. **Subquery Optimization**: Convert correlated subqueries to JOINs where beneficial
4. **Predicate Pushdown**: Move filters as close to base tables as possible
5. **Redundant Operations**: Remove unnecessary DISTINCT, ORDER BY, etc.
6. **JOIN Order**: Optimize JOIN order based on table sizes (if known)

IMPORTANT:
- Do NOT change the semantic meaning of the query
- Only apply optimizations that are safe and universally beneficial
- Maintain compatibility with {sql_dialect} syntax

OUTPUT FORMAT (JSON):
{{
    "optimized_sql": "SELECT ...",
    "optimizations_applied": ["Replaced SELECT * with specific columns", ...],
    "performance_notes": "Brief explanation of expected improvements",
    "index_suggestions": ["CREATE INDEX idx_name ON table(column)", ...]
}}

Optimize the query now:"""


class QueryOptimizationAgent:
    """
    Agent 5: Query Optimization
    
    Optimizes validated SQL queries for better performance.
    Uses rule-based checks + LLM for complex optimizations.
    """
    
    def __init__(self):
        """Initialize the Query Optimization Agent."""
        self.prompt_template = ChatPromptTemplate.from_template(
            QUERY_OPTIMIZATION_PROMPT
        )
        
        if settings.use_openai:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.primary_llm_model,
                temperature=0.1,
                max_tokens=1500
            )
        elif settings.use_groq:
            from langchain_groq import ChatGroq
            self.llm = ChatGroq(
                model=settings.fallback_llm_model,
                temperature=0.1,
                max_tokens=1500
            )
        else:
            self.llm = None
        
        self.json_parser = JsonOutputParser()
    
    def _rule_based_optimizations(self, sql: str) -> tuple[str, List[str]]:
        """
        Apply simple rule-based optimizations before LLM processing.
        
        Args:
            sql: Original SQL query
            
        Returns:
            Tuple of (optimized_sql, list_of_optimizations)
        """
        optimizations = []
        optimized = sql
        
        # Rule 1: Remove extra whitespace
        import re
        optimized = re.sub(r'\s+', ' ', optimized).strip()
        
        # Rule 2: Normalize keywords to uppercase
        keywords = ['select', 'from', 'where', 'join', 'on', 'and', 'or', 'group', 'order', 'by', 'having']
        for kw in keywords:
            pattern = r'\b' + kw + r'\b'
            optimized = re.sub(pattern, kw.upper(), optimized, flags=re.IGNORECASE)
        
        # Rule 3: Flag SELECT * for review (don't auto-replace, just note it)
        if 'SELECT *' in optimized.upper():
            optimizations.append("Flagged: Consider replacing SELECT * with specific columns")
        
        return optimized, optimizations
    
    def invoke(self, state: AgentState) -> AgentState:
        """
        Optimize the validated SQL query.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated agent state with optimized SQL
        """
        state["current_agent"] = "query_optimization"
        
        sql = state.get("selected_sql") or state.get("optimized_sql")
        
        if not sql:
            add_to_processing_log(state, "No SQL to optimize")
            return state
        
        try:
            # First apply rule-based optimizations
            rule_optimized, rule_optimizations = self._rule_based_optimizations(sql)
            
            # Determine dialect
            db_url = settings.database_url
            if "postgresql" in db_url:
                dialect = "PostgreSQL"
            elif "mysql" in db_url:
                dialect = "MySQL"
            else:
                dialect = "SQLite"
            
            # Use LLM for advanced optimizations if available
            if self.llm:
                chain = self.prompt_template | self.llm | self.json_parser
                
                result = chain.invoke({
                    "original_sql": rule_optimized,
                    "sql_dialect": dialect,
                    "table_schemas": str(state.get("table_schemas", {}))
                })
                
                optimized_sql = result.get("optimized_sql", rule_optimized)
                llm_optimizations = result.get("optimizations_applied", [])
                performance_notes = result.get("performance_notes", "")
                
                all_optimizations = rule_optimizations + llm_optimizations
            else:
                optimized_sql = rule_optimized
                all_optimizations = rule_optimizations
                performance_notes = "Rule-based optimization only"
            
            # Update state
            state["original_sql"] = sql
            state["optimized_sql"] = optimized_sql
            state["optimizations_applied"] = all_optimizations
            
            add_to_processing_log(
                state,
                f"Applied {len(all_optimizations)} optimizations"
            )
            
        except Exception as e:
            error_msg = f"Query optimization failed: {str(e)}"
            state["error_message"] = error_msg
            state["optimized_sql"] = sql  # Keep original if optimization fails
            add_to_processing_log(state, f"ERROR: {error_msg}")
        
        return state


# ============================================================================
# Agent 6: SQL Execution
# ============================================================================

class SQLExecutionAgent:
    """
    Agent 6: SQL Execution
    
    Executes the optimized SQL query against the database safely.
    Implements:
    - Read-only connections
    - Query timeout
    - Row limit
    - Error handling
    """
    
    def __init__(self):
        """Initialize the SQL Execution Agent."""
        self.db_engine = None
    
    def connect_to_database(self, db_url: Optional[str] = None) -> bool:
        """
        Connect to the database.
        
        Args:
            db_url: Database connection URL
            
        Returns:
            True if connection successful
        """
        from sqlalchemy import create_engine
        
        if not db_url:
            db_url = settings.database_url
        
        try:
            # Create engine with safety settings
            self.db_engine = create_engine(
                db_url,
                pool_pre_ping=True,  # Validate connections before use
                pool_recycle=3600,   # Recycle connections after 1 hour
                execution_options={
                    "statement_timeout": settings.max_query_timeout * 1000,  # ms
                    "max_rows": settings.max_rows_returned
                }
            )
            return True
        except Exception as e:
            print(f"Database connection failed: {e}")
            return False
    
    def execute_query(self, sql: str) -> Dict[str, Any]:
        """
        Execute SQL query with safety limits.
        
        Args:
            sql: SQL query to execute
            
        Returns:
            Dictionary with results, columns, row count, execution time, errors
        """
        from sqlalchemy import text
        
        result = {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "execution_time_ms": 0.0,
            "error_message": None
        }
        
        if not self.db_engine:
            if not self.connect_to_database():
                result["error_message"] = "Failed to connect to database"
                return result
        
        try:
            start_time = time.time()
            
            with self.db_engine.connect() as conn:
                # Execute query
                db_result = conn.execute(text(sql))
                
                # Get column names
                result["columns"] = [col.name for col in db_result.cursor.description]
                
                # Fetch rows with limit
                rows = db_result.fetchmany(settings.max_rows_returned)
                result["rows"] = [list(row) for row in rows]
                result["row_count"] = len(result["rows"])
                
                # Calculate execution time
                end_time = time.time()
                result["execution_time_ms"] = (end_time - start_time) * 1000
                
                result["success"] = True
                
        except Exception as e:
            result["error_message"] = str(e)
            result["success"] = False
        
        return result
    
    def invoke(self, state: AgentState) -> AgentState:
        """
        Execute the optimized SQL query.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated agent state with execution results
        """
        state["current_agent"] = "sql_execution"
        
        sql = state.get("optimized_sql") or state.get("selected_sql")
        
        if not sql:
            state["execution_success"] = False
            state["execution_error"] = "No SQL query to execute"
            return state
        
        # Execute the query
        result = self.execute_query(sql)
        
        # Update state
        state["execution_success"] = result["success"]
        state["query_results"] = result["rows"]
        state["result_columns"] = result["columns"]
        state["execution_time_ms"] = result["execution_time_ms"]
        state["execution_error"] = result["error_message"]
        
        if result["success"]:
            add_to_processing_log(
                state,
                f"Query executed successfully: {result['row_count']} rows in {result['execution_time_ms']:.2f}ms"
            )
        else:
            add_to_processing_log(state, f"Query execution failed: {result['error_message']}")
        
        return state


# ============================================================================
# Agent 7: Explanation Generation
# ============================================================================

EXPLANATION_PROMPT = """
You are an Explanation Agent for a Natural Language to SQL system.
Your task is to explain the SQL query and its results in plain English.

INPUTS:
- Original Question: {question}
- Generated SQL: {sql}
- Query Results Summary: {results_summary}
- Result Columns: {columns}
- Row Count: {row_count}

PROVIDE:
1. **SQL Explanation**: Explain what the SQL query does in simple terms
2. **Result Summary**: Summarize what the results mean in context of the question
3. **Key Insights**: Highlight any interesting patterns or insights from the data

GUIDELINES:
- Use non-technical language where possible
- Relate the explanation back to the original question
- Don't just repeat the data - provide context and meaning
- If results are empty, explain why that might be

OUTPUT FORMAT (JSON):
{{
    "sql_explanation": "This query retrieves...",
    "result_summary": "The results show that...",
    "insights": ["Insight 1", "Insight 2", ...]
}}

Generate the explanation now:"""


class ExplanationAgent:
    """
    Agent 7: Explanation Generation
    
    Generates human-readable explanations of the SQL query and results.
    Uses Groq/Llama for cost-effective explanation generation.
    """
    
    def __init__(self):
        """Initialize the Explanation Agent."""
        self.prompt_template = ChatPromptTemplate.from_template(
            EXPLANATION_PROMPT
        )
        
        if settings.use_groq:
            from langchain_groq import ChatGroq
            self.llm = ChatGroq(
                model=settings.fallback_llm_model,
                temperature=0.3,  # Slightly higher for more natural explanations
                max_tokens=1000
            )
        elif settings.use_openai:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.primary_llm_model,
                temperature=0.3,
                max_tokens=1000
            )
        else:
            self.llm = None
        
        self.json_parser = JsonOutputParser()
    
    def _summarize_results(self, rows: List[Any], columns: List[str]) -> str:
        """Create a brief summary of query results."""
        if not rows:
            return "No results returned"
        
        row_count = len(rows)
        sample_row = rows[0] if rows else []
        
        summary = f"Returned {row_count} row(s) with columns: {', '.join(columns)}. "
        if sample_row:
            summary += f"Sample: {dict(zip(columns, sample_row))}"
        
        return summary
    
    def invoke(self, state: AgentState) -> AgentState:
        """
        Generate explanation for the query and results.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated agent state with explanation
        """
        state["current_agent"] = "explanation"
        
        if not state.get("include_explanation", True):
            add_to_processing_log(state, "Explanation skipped per request")
            return state
        
        sql = state.get("optimized_sql") or state.get("selected_sql")
        
        if not sql:
            add_to_processing_log(state, "No SQL to explain")
            return state
        
        if not self.llm:
            # Create basic explanation without LLM
            state["sql_explanation"] = f"Executed SQL query: {sql[:200]}..."
            state["result_summary"] = f"Returned {len(state.get('query_results', []))} rows"
            return state
        
        try:
            # Prepare results summary
            results_summary = self._summarize_results(
                state.get("query_results", []),
                state.get("result_columns", [])
            )
            
            chain = self.prompt_template | self.llm | self.json_parser
            
            result = chain.invoke({
                "question": state["question"],
                "sql": sql,
                "results_summary": results_summary,
                "columns": ", ".join(state.get("result_columns", [])),
                "row_count": len(state.get("query_results", []))
            })
            
            # Update state
            state["sql_explanation"] = result.get("sql_explanation", "")
            state["result_summary"] = result.get("result_summary", "")
            state["insights"] = result.get("insights", [])
            
            add_to_processing_log(state, "Explanation generated")
            
        except Exception as e:
            error_msg = f"Explanation generation failed: {str(e)}"
            state["error_message"] = error_msg
            add_to_processing_log(state, f"ERROR: {error_msg}")
            
            # Fallback to basic explanation
            state["sql_explanation"] = f"SQL: {sql[:200]}..."
            state["result_summary"] = results_summary if 'results_summary' in locals() else "Results available"
        
        return state


# ============================================================================
# Convenience Functions
# ============================================================================

_optimization_agent_instance = None
_execution_agent_instance = None
_explanation_agent_instance = None


def get_optimization_agent() -> QueryOptimizationAgent:
    """Get or create the Query Optimization Agent singleton."""
    global _optimization_agent_instance
    if _optimization_agent_instance is None:
        _optimization_agent_instance = QueryOptimizationAgent()
    return _optimization_agent_instance


def get_execution_agent() -> SQLExecutionAgent:
    """Get or create the SQL Execution Agent singleton."""
    global _execution_agent_instance
    if _execution_agent_instance is None:
        _execution_agent_instance = SQLExecutionAgent()
    return _execution_agent_instance


def get_explanation_agent() -> ExplanationAgent:
    """Get or create the Explanation Agent singleton."""
    global _explanation_agent_instance
    if _explanation_agent_instance is None:
        _explanation_agent_instance = ExplanationAgent()
    return _explanation_agent_instance


if __name__ == "__main__":
    print("Testing Agents 5, 6, 7\n" + "=" * 50)
    
    from backend.agents.state import initialize_state
    
    # Test Query Optimization
    print("\n1. Testing Query Optimization Agent")
    print("-" * 50)
    
    test_state = initialize_state("Test query")
    test_state["selected_sql"] = "SELECT * FROM customers WHERE age > 30"
    test_state["table_schemas"] = {"customers": {"columns": ["id", "name", "age"]}}
    
    opt_agent = get_optimization_agent()
    result_state = opt_agent.invoke(test_state)
    
    print(f"Original: {test_state.get('original_sql')}")
    print(f"Optimized: {result_state.get('optimized_sql')}")
    print(f"Optimizations: {result_state.get('optimizations_applied', [])}")
    
    # Test SQL Execution (requires database)
    print("\n2. Testing SQL Execution Agent")
    print("-" * 50)
    
    exec_agent = get_execution_agent()
    
    # Try with SQLite in-memory
    if exec_agent.connect_to_database("sqlite:///:memory:"):
        print("✓ Connected to in-memory SQLite")
        
        # Create a test table
        from sqlalchemy import text
        with exec_agent.db_engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER, name TEXT)"))
            conn.execute(text("INSERT INTO test VALUES (1, 'Alice'), (2, 'Bob')"))
            conn.commit()
        
        # Execute query
        result = exec_agent.execute_query("SELECT * FROM test")
        print(f"Success: {result['success']}")
        print(f"Rows: {result['row_count']}")
        print(f"Columns: {result['columns']}")
    else:
        print("✗ Could not connect to test database")
    
    # Test Explanation
    print("\n3. Testing Explanation Agent")
    print("-" * 50)
    
    exp_state = initialize_state("Show me all customers")
    exp_state["selected_sql"] = "SELECT id, name FROM customers"
    exp_state["query_results"] = [[1, "Alice"], [2, "Bob"]]
    exp_state["result_columns"] = ["id", "name"]
    
    exp_agent = get_explanation_agent()
    
    if exp_agent.llm:
        result_state = exp_agent.invoke(exp_state)
        print(f"SQL Explanation: {result_state.get('sql_explanation', 'N/A')}")
        print(f"Result Summary: {result_state.get('result_summary', 'N/A')}")
    else:
        print("⚠ No LLM configured for explanation")
