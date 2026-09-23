"""
Database Service

Provides a reusable, centralized database connection pool and execution
utilities consumed by SQLExecutionAgent and SchemaRetrievalAgent.

This service owns:
- Engine creation with dialect-appropriate timeout settings
- Schema introspection
- Safe SQL execution with row limiting and timeout
"""

import time
import threading
from typing import Any, Dict, List, Optional
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from backend.core.config import settings


class DatabaseService:
    """
    Centralized database service for connection management and safe SQL execution.
    """

    def __init__(self) -> None:
        self._engine: Optional[Engine] = None

    @property
    def engine(self) -> Optional[Engine]:
        return self._engine

    def connect(self, db_url: Optional[str] = None) -> bool:
        """
        Create (or re-use) a SQLAlchemy engine for the given URL.

        Returns:
            True if connection was established successfully.
        """
        url = db_url or settings.database_url
        try:
            if "postgresql" in url:
                self._engine = create_engine(
                    url,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    connect_args={
                        "options": f"-c statement_timeout={settings.max_query_timeout * 1000}"
                    },
                )
            elif "mysql" in url:
                self._engine = create_engine(
                    url,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    connect_args={"read_timeout": settings.max_query_timeout},
                )
            else:
                self._engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
            return True
        except Exception:
            return False

    def introspect(self) -> Dict[str, Any]:
        """
        Introspect the connected database and return its full schema.

        Returns:
            {"tables": {table_name: {"columns": [...]}}, "foreign_keys": [...]}
        """
        if not self._engine:
            return {"tables": {}, "foreign_keys": []}

        result: Dict[str, Any] = {"tables": {}, "foreign_keys": []}
        inspector = inspect(self._engine)

        for table_name in inspector.get_table_names():
            columns = [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "primary_key": col.get("primary_key", False),
                }
                for col in inspector.get_columns(table_name)
            ]
            result["tables"][table_name] = {
                "columns": columns,
                "column_count": len(columns),
            }
            for fk in inspector.get_foreign_keys(table_name):
                result["foreign_keys"].append({
                    "table": table_name,
                    "column": fk["constrained_columns"][0],
                    "referenced_table": fk["referred_table"],
                    "referenced_column": fk["referred_columns"][0],
                })

        return result

    def execute(self, sql: str) -> Dict[str, Any]:
        """
        Execute a SQL query safely with timeout and row-limit enforcement.

        Returns:
            {"success", "columns", "rows", "row_count", "execution_time_ms",
             "error_message", "warning"}
        """
        result: Dict[str, Any] = {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "execution_time_ms": 0.0,
            "error_message": None,
            "warning": None,
        }

        if not self._engine and not self.connect():
            result["error_message"] = "No database connection"
            return result

        try:
            start = time.time()
            url_str = str(self._engine.url)  # type: ignore[union-attr]

            with self._engine.connect() as conn:  # type: ignore[union-attr]
                if "sqlite" in url_str:
                    exec_data: Dict[str, Any] = {"data": None, "error": None}

                    def _run() -> None:
                        try:
                            exec_data["data"] = conn.execute(text(sql))
                        except Exception as exc:
                            exec_data["error"] = exc

                    t = threading.Thread(target=_run, daemon=True)
                    t.start()
                    t.join(timeout=settings.max_query_timeout)

                    if t.is_alive():
                        result["error_message"] = (
                            f"Query exceeded timeout of {settings.max_query_timeout}s"
                        )
                        return result

                    if exec_data["error"]:
                        raise exec_data["error"]

                    db_result = exec_data["data"]
                else:
                    db_result = conn.execute(text(sql))

                result["columns"] = list(db_result.keys())
                all_rows = db_result.fetchall()
                limited = all_rows[: settings.max_rows_returned]
                result["rows"] = [list(r) for r in limited]
                result["row_count"] = len(result["rows"])

                if len(all_rows) > settings.max_rows_returned:
                    result["warning"] = (
                        f"Truncated to {settings.max_rows_returned} rows "
                        f"(total: {len(all_rows)})"
                    )

            result["execution_time_ms"] = (time.time() - start) * 1000
            result["success"] = True

        except Exception as e:
            result["error_message"] = str(e)

        return result


# Singleton
_db_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Return the global DatabaseService instance."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service
