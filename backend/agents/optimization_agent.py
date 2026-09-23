"""
Agent 6: Query Optimization

Optimizes the validated and security-approved SQL query for better performance.
Key features:
- Rule-based optimizations (whitespace, keyword normalization)
- LLM-based advanced optimizations (subquery rewriting, predicate pushdown)
- Only runs AFTER validation has passed AND security has been approved

8-agent pipeline position:
1. Intent -> 2. Schema -> 3. SQL Generation -> 4. Validation ->
5. Security -> 6. Optimization -> 7. Execution -> 8. Explanation
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.core.config import settings
from backend.agents.state import AgentState, add_to_processing_log


QUERY_OPTIMIZATION_PROMPT = """
You are a Query Optimization Agent for a Natural Language to SQL system.
Your task is to optimize the generated SQL query for better performance.

INPUTS:
- Original SQL: {original_sql}
- Database Dialect: {sql_dialect}
- Table Schemas: {table_schemas}

OPTIMIZATION GUIDELINES:
1. **Avoid SELECT ***: Replace with specific columns if possible
2. **Subquery Optimization**: Convert correlated subqueries to JOINs where beneficial
3. **Predicate Pushdown**: Move filters as close to base tables as possible
4. **Redundant Operations**: Remove unnecessary DISTINCT, ORDER BY where unneeded
5. **JOIN Order**: Optimize JOIN order based on table sizes (if known)

IMPORTANT:
- Do NOT change the semantic meaning of the query
- Only apply optimizations that are safe and universally beneficial
- Maintain compatibility with {sql_dialect} syntax

OUTPUT FORMAT (JSON):
{{
    "optimized_sql": "SELECT ...",
    "optimizations_applied": ["description1", ...],
    "performance_notes": "Brief explanation of expected improvements",
    "index_suggestions": ["CREATE INDEX idx_name ON table(column)", ...]
}}

Optimize the query now:"""


class QueryOptimizationAgent:
    """
    Agent 6: Query Optimization

    Optimizes validated and security-approved SQL queries for better performance.
    Uses rule-based checks first, then LLM for complex optimizations.

    PRECONDITION: Only invoked after is_valid=True AND security_passed=True.
    """

    def __init__(self) -> None:
        """Initialize the Query Optimization Agent."""
        self.prompt_template = ChatPromptTemplate.from_template(QUERY_OPTIMIZATION_PROMPT)

        if settings.use_groq:
            from langchain_groq import ChatGroq
            self.llm = ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.fallback_llm_model,
                temperature=0.1,
                max_tokens=1500
            )
        elif settings.use_openai:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                api_key=settings.openai_api_key,
                model=settings.primary_llm_model,
                temperature=0.1,
                max_tokens=1500
            )
        else:
            self.llm = None

        self.json_parser = JsonOutputParser()

    def _detect_dialect(self) -> str:
        """Detect SQL dialect from configured database URL."""
        db_url = settings.database_url
        if "postgresql" in db_url:
            return "PostgreSQL"
        elif "mysql" in db_url:
            return "MySQL"
        return "SQLite"

    def _rule_based_optimizations(self, sql: str) -> Tuple[str, List[str]]:
        """
        Apply simple rule-based optimizations before LLM processing.

        Returns:
            Tuple of (optimized_sql, list_of_optimization_descriptions)
        """
        optimizations: List[str] = []
        optimized = sql

        # Rule 1: Collapse extra whitespace
        cleaned = re.sub(r'\s+', ' ', optimized).strip()
        if cleaned != optimized:
            optimized = cleaned
            optimizations.append("Collapsed redundant whitespace")

        # Rule 2: Normalize SQL keywords to uppercase
        keywords = [
            'select', 'from', 'where', 'join', 'inner', 'left', 'right', 'outer',
            'on', 'and', 'or', 'not', 'in', 'is', 'null', 'group', 'order', 'by',
            'having', 'limit', 'offset', 'distinct', 'union', 'all', 'as',
            'case', 'when', 'then', 'else', 'end', 'count', 'sum', 'avg', 'max', 'min'
        ]
        for kw in keywords:
            pattern = r'\b' + kw + r'\b'
            new_sql = re.sub(pattern, kw.upper(), optimized, flags=re.IGNORECASE)
            if new_sql != optimized:
                optimized = new_sql

        # Rule 3: Flag SELECT * for LLM review (do not auto-replace)
        if re.search(r'\bSELECT\s+\*', optimized, re.IGNORECASE):
            optimizations.append("Flagged: Consider replacing SELECT * with specific columns")

        return optimized, optimizations

    def invoke(self, state: AgentState) -> AgentState:
        """
        Optimize the validated and security-approved SQL query.

        Args:
            state: Current agent state with is_valid=True and security_passed=True

        Returns:
            Updated agent state with optimized SQL
        """
        state["current_agent"] = "query_optimization"

        # Guard: only optimize if validation AND security passed
        if not state.get("is_valid", False):
            add_to_processing_log(state, "ERROR: Optimization skipped — SQL not validated")
            state["optimized_sql"] = state.get("selected_sql")
            return state

        if not state.get("security_passed", False):
            add_to_processing_log(state, "ERROR: Optimization skipped — security check not passed")
            state["optimized_sql"] = state.get("selected_sql")
            return state

        sql = state.get("selected_sql")
        if not sql:
            add_to_processing_log(state, "No SQL available to optimize")
            return state

        try:
            # Step 1: Rule-based optimizations
            rule_optimized, rule_optimizations = self._rule_based_optimizations(sql)
            dialect = self._detect_dialect()

            # Step 2: LLM-based advanced optimizations (if LLM configured)
            if self.llm:
                chain = self.prompt_template | self.llm | self.json_parser
                result = chain.invoke({
                    "original_sql": rule_optimized,
                    "sql_dialect": dialect,
                    "table_schemas": str(state.get("table_schemas", {}))
                })
                optimized_sql = result.get("optimized_sql", rule_optimized)
                llm_optimizations = result.get("optimizations_applied", [])
                all_optimizations = rule_optimizations + llm_optimizations
            else:
                optimized_sql = rule_optimized
                all_optimizations = rule_optimizations

            state["original_sql"] = sql
            state["optimized_sql"] = optimized_sql
            state["optimizations_applied"] = all_optimizations

            add_to_processing_log(
                state,
                f"Agent 6 (Optimization): Applied {len(all_optimizations)} optimization(s)"
            )

        except Exception as e:
            # Do NOT crash the pipeline on optimization failure — keep original SQL
            add_to_processing_log(state, f"WARNING: Optimization failed ({e}) — keeping original SQL")
            state["original_sql"] = sql
            state["optimized_sql"] = sql
            state["optimizations_applied"] = []

        return state


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

_optimization_agent_instance: Optional[QueryOptimizationAgent] = None


def get_optimization_agent() -> QueryOptimizationAgent:
    """Get or create the Query Optimization Agent singleton."""
    global _optimization_agent_instance
    if _optimization_agent_instance is None:
        _optimization_agent_instance = QueryOptimizationAgent()
    return _optimization_agent_instance
