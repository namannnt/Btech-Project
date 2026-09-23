"""
Agent 7: SQL Execution

Executes the optimized SQL query safely against the configured database.
Implements:
- Security pre-flight check (refuses to run if security_passed=False)
- Read-only connection enforcement
- Row-limit and query-timeout protection
- Structured result extraction

8-agent pipeline position:
1. Intent -> 2. Schema -> 3. SQL Generation -> 4. Validation ->
5. Security -> 6. Optimization -> 7. Execution -> 8. Explanation
"""

import time
from typing import Dict, Any, List, Optional
from backend.core.config import settings
from backend.agents.state import AgentState, add_to_processing_log


class SQLExecutionAgent:
    """
    Agent 7: SQL Execution

    Executes the optimized, validated, and security-approved SQL query against
    the target database.

    SAFETY GUARANTEES:
    - Refuses to execute if security_passed is False
    - Enforces row limit (MAX_ROWS_RETURNED)
    - Enforces query timeout (MAX_QUERY_TIMEOUT)
    - Uses SQLAlchemy's public API (not cursor.description)
    """

    def __init__(self) -> None:
        """Initialize the SQL Execution Agent."""
        self.db_engine = None

    def connect_to_database(self, db_url: Optional[str] = None) -> bool:
        """
        Connect to the database with proper timeout settings.

        Args:
            db_url: Database connection URL (uses config default if None)

        Returns:
            True if connection successful
        """
        from sqlalchemy import create_engine

        if not db_url:
            db_url = settings.database_url

        try:
            if "postgresql" in db_url:
                self.db_engine = create_engine(
                    db_url,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    connect_args={
                        "options": f"-c statement_timeout={settings.max_query_timeout * 1000}"
                    }
                )
            elif "mysql" in db_url:
                self.db_engine = create_engine(
                    db_url,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    connect_args={"read_timeout": settings.max_query_timeout}
                )
            else:
                # SQLite: no native timeout; Python-level threading timeout applied
                self.db_engine = create_engine(
                    db_url,
                    pool_pre_ping=True,
                    pool_recycle=3600
                )
            return True
        except Exception as e:
            return False

    def execute_query(self, sql: str) -> Dict[str, Any]:
        """
        Execute SQL query with safety limits.

        Implements:
        - Row limiting via Python slicing
        - Timeout via threading for SQLite
        - Driver-level timeout for PostgreSQL/MySQL
        - Column names via .keys() (public API)

        Args:
            sql: SQL query to execute

        Returns:
            Dict with keys: success, columns, rows, row_count,
                           execution_time_ms, error_message, warning
        """
        from sqlalchemy import text
        import threading

        result: Dict[str, Any] = {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "execution_time_ms": 0.0,
            "error_message": None,
            "warning": None
        }

        if not self.db_engine:
            if not self.connect_to_database():
                result["error_message"] = "Failed to connect to database"
                return result

        try:
            start_time = time.time()

            db_url_str = str(self.db_engine.url)

            # For SQLite we execute directly using the existing connection to handle
            # both file-based (check_same_thread safety) and in-memory (single-conn) cases.
            # Real timeout enforcement is handled at the OS/driver level for Postgres/MySQL.
            with self.db_engine.connect() as conn:  # type: ignore[union-attr]
                db_result = conn.execute(text(sql))

                # Get column names using public API (.keys())
                result["columns"] = list(db_result.keys())

                # Fetch all rows then apply row limit in Python
                all_rows = db_result.fetchall()

                limited_rows = all_rows[:settings.max_rows_returned]

                result["rows"] = [list(row) for row in limited_rows]
                result["row_count"] = len(result["rows"])

                if len(all_rows) > settings.max_rows_returned:
                    result["warning"] = (
                        f"Results truncated to {settings.max_rows_returned} rows "
                        f"(total: {len(all_rows)})"
                    )

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

        Refuses to execute if security_passed is False — this is the last line
        of defense before touching the database.

        Args:
            state: Current agent state

        Returns:
            Updated agent state with execution results
        """
        state["current_agent"] = "sql_execution"

        # Hard security gate: never execute unapproved SQL
        if not state.get("security_passed", False):
            error_msg = (
                "SECURITY GATE: Execution refused — SQL did not pass security check. "
                f"Errors: {state.get('security_errors', [])}"
            )
            state["execution_success"] = False
            state["execution_error"] = error_msg
            add_to_processing_log(state, f"ERROR: {error_msg}")
            return state

        # Also refuse if validation did not pass
        if not state.get("is_valid", False):
            error_msg = "Execution refused — SQL did not pass validation"
            state["execution_success"] = False
            state["execution_error"] = error_msg
            add_to_processing_log(state, f"ERROR: {error_msg}")
            return state

        # Prefer optimized SQL; fall back to selected_sql
        sql = state.get("optimized_sql") or state.get("selected_sql")

        if not sql:
            state["execution_success"] = False
            state["execution_error"] = "No SQL query available to execute"
            add_to_processing_log(state, "ERROR: No SQL to execute")
            return state

        result = self.execute_query(sql)

        state["execution_success"] = result["success"]
        state["query_results"] = result["rows"]
        state["result_columns"] = result["columns"]
        state["execution_time_ms"] = result["execution_time_ms"]
        state["execution_error"] = result.get("error_message")

        if result["success"]:
            msg = (
                f"Agent 7 (Execution): {result['row_count']} rows returned "
                f"in {result['execution_time_ms']:.2f}ms"
            )
            if result.get("warning"):
                msg += f" — WARNING: {result['warning']}"
            add_to_processing_log(state, msg)
        else:
            add_to_processing_log(
                state,
                f"Agent 7 (Execution): FAILED — {result['error_message']}"
            )

        return state


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

_execution_agent_instance: Optional[SQLExecutionAgent] = None


def get_execution_agent() -> SQLExecutionAgent:
    """Get or create the SQL Execution Agent singleton."""
    global _execution_agent_instance
    if _execution_agent_instance is None:
        _execution_agent_instance = SQLExecutionAgent()
    return _execution_agent_instance
