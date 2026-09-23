"""SQL utility helpers for the NL2SQL pipeline."""

import re
from typing import Optional
from backend.core.config import settings


def detect_dialect() -> str:
    """
    Detect the SQL dialect from the configured database URL.

    Returns:
        One of: 'sqlite', 'postgres', 'mysql'
    """
    url = settings.database_url.lower()
    if "postgresql" in url or "postgres" in url:
        return "postgres"
    if "mysql" in url:
        return "mysql"
    return "sqlite"


def detect_dialect_display() -> str:
    """Return display-friendly dialect name (e.g. 'PostgreSQL')."""
    mapping = {"postgres": "PostgreSQL", "mysql": "MySQL", "sqlite": "SQLite"}
    return mapping.get(detect_dialect(), "SQLite")


def is_select_only(sql: str) -> bool:
    """Return True if the SQL contains only SELECT (no DML/DDL)."""
    sql_stripped = sql.strip().upper()
    # Starts with SELECT and contains none of the dangerous keywords as top-level statements
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE"]
    if not sql_stripped.startswith("SELECT"):
        return False
    for kw in dangerous:
        if re.search(r'\b' + kw + r'\b', sql_stripped):
            return False
    return True


def normalize_sql(sql: str) -> str:
    """
    Normalize SQL for comparison: collapse whitespace and uppercase keywords.
    """
    normalized = re.sub(r'\s+', ' ', sql).strip()
    return normalized


def truncate_sql_for_display(sql: str, max_len: int = 200) -> str:
    """Truncate SQL for safe display in logs/responses."""
    if len(sql) <= max_len:
        return sql
    return sql[:max_len] + "..."
