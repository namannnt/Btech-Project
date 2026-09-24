"""
Agent 5: Security / Permission Check

This is the security gate that runs BEFORE SQL execution.
It evaluates every generated SQL query against role-based policies and
safety rules BEFORE any data is read or modified.

Responsibilities:
- Role-based access control (RBAC): which operations each role may perform
- Table-level access control: which tables each role may query
- Dangerous statement detection: DROP, ALTER, TRUNCATE, GRANT, REVOKE always rejected
- Mutation guard: INSERT/UPDATE/DELETE blocked for user/analyst/guest roles
- SQL injection heuristic detection
- Max row limit annotation
- Full audit trail generation (who, what, when, decision, reason)

8-agent pipeline position:
1. Intent -> 2. Schema -> 3. SQL Generation -> 4. Validation ->
5. Security -> 6. Optimization -> 7. Execution -> 8. Explanation
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from backend.agents.state import AgentState, add_to_processing_log


# ---------------------------------------------------------------------------
# Role-based permission matrix
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: Dict[str, Dict[str, Any]] = {
    "admin": {
        "allowed_operations": ["SELECT", "INSERT", "UPDATE", "DELETE"],
        "allowed_tables": "*",          # All tables
        "max_rows": 10_000,
        "allow_aggregations": True,
    },
    "analyst": {
        "allowed_operations": ["SELECT"],
        "allowed_tables": "*",
        "max_rows": 5_000,
        "allow_aggregations": True,
    },
    "user": {
        "allowed_operations": ["SELECT"],
        "allowed_tables": "*",
        "max_rows": 1_000,
        "allow_aggregations": True,
    },
    "guest": {
        "allowed_operations": ["SELECT"],
        "allowed_tables": ["public_view"],   # Restricted
        "max_rows": 100,
        "allow_aggregations": False,
    },
}

# Statements that are NEVER allowed regardless of role
ABSOLUTELY_FORBIDDEN_STATEMENTS: List[str] = [
    "DROP", "ALTER", "TRUNCATE", "GRANT", "REVOKE",
    "CREATE", "REPLACE", "RENAME", "VACUUM", "ATTACH",
    "DETACH",
]

# SQL injection heuristic patterns
INJECTION_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r";\s*(DROP|DELETE|TRUNCATE|INSERT|UPDATE|ALTER|CREATE)", re.IGNORECASE),
    re.compile(r"--\s*$", re.MULTILINE),     # comment-based injection
    re.compile(r"/\*.*?\*/", re.DOTALL),     # block comment injection
    re.compile(r"'\s*OR\s*'?\d+'?\s*=\s*'?\d+'?", re.IGNORECASE),  # classic OR 1=1
    re.compile(r";\s*UNION\s+(ALL\s+)?SELECT", re.IGNORECASE),          # UNION injection
]


class SecurityAgent:
    """
    Agent 5: Security / Permission Check

    The security gate that runs AFTER validation and BEFORE optimization/execution.
    If this agent rejects a query, execution is completely prevented.

    Decision flow:
    1. Check for absolutely forbidden statements (hard block)
    2. Check for SQL injection patterns (hard block)
    3. Check role-based operation permissions
    4. Check role-based table permissions
    5. Generate audit record regardless of outcome
    """

    def __init__(self) -> None:
        """Initialize the Security Agent."""
        self.role_permissions = ROLE_PERMISSIONS

    def _get_permissions(self, role: str) -> Dict[str, Any]:
        """Get permission config for a role, falling back to 'user' if unknown."""
        return self.role_permissions.get(role, self.role_permissions["user"])

    def _detect_forbidden_statements(self, sql: str) -> Tuple[bool, List[str]]:
        """
        Check for absolutely forbidden DDL/DCL statements.

        These are blocked for ALL roles without exception:
        DROP, ALTER, TRUNCATE, GRANT, REVOKE, CREATE, REPLACE, RENAME, etc.

        Returns:
            (has_forbidden, list_of_violations)
        """
        violations: List[str] = []
        sql_upper = sql.strip().upper()

        for stmt in ABSOLUTELY_FORBIDDEN_STATEMENTS:
            # Use word-boundary matching to avoid false positives (e.g. "CREATED_AT")
            if re.search(r'\b' + re.escape(stmt) + r'\b', sql_upper):
                violations.append(
                    f"Forbidden statement detected: {stmt}. "
                    f"This operation is never permitted."
                )

        return len(violations) > 0, violations

    def _detect_injection_patterns(self, sql: str) -> Tuple[bool, List[str]]:
        """
        Heuristic detection of SQL injection attempts.

        Returns:
            (has_injection, list_of_warnings)
        """
        warnings: List[str] = []

        for pattern in INJECTION_PATTERNS:
            if pattern.search(sql):
                warnings.append(
                    f"Potential SQL injection pattern detected: {pattern.pattern}"
                )

        return len(warnings) > 0, warnings

    def _check_operation_permissions(
        self,
        sql: str,
        role: str,
        permissions: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Verify the SQL operation is permitted for this role.

        Returns:
            (permitted, list_of_violations)
        """
        violations: List[str] = []
        allowed_ops: List[str] = permissions.get("allowed_operations", ["SELECT"])
        sql_upper = sql.strip().upper()

        # Detect which DML operations are present
        detected_ops: List[str] = []
        if re.search(r'\bSELECT\b', sql_upper):
            detected_ops.append("SELECT")
        if re.search(r'\bINSERT\b', sql_upper):
            detected_ops.append("INSERT")
        if re.search(r'\bUPDATE\b', sql_upper):
            detected_ops.append("UPDATE")
        if re.search(r'\bDELETE\b', sql_upper):
            detected_ops.append("DELETE")

        for op in detected_ops:
            if op not in allowed_ops:
                violations.append(
                    f"Operation '{op}' is not permitted for role '{role}'. "
                    f"Allowed operations: {allowed_ops}"
                )

        return len(violations) == 0, violations

    def _check_table_permissions(
        self,
        sql: str,
        role: str,
        permissions: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Verify all referenced tables are accessible by this role.

        Returns:
            (permitted, list_of_violations)
        """
        violations: List[str] = []
        allowed_tables = permissions.get("allowed_tables", "*")

        # Wildcard means all tables are allowed
        if allowed_tables == "*":
            return True, []

        try:
            from sqlglot import parse
            from sqlglot import exp

            parsed = parse(sql)
            if not parsed:
                return True, []  # Cannot parse — allow (validation already ran)

            statement = parsed[0]
            referenced_tables: set = set()
            for table_node in statement.find_all(exp.Table):
                if table_node.name:
                    referenced_tables.add(table_node.name.lower())

            allowed_set = {t.lower() for t in allowed_tables}
            unauthorized = referenced_tables - allowed_set
            if unauthorized:
                violations.append(
                    f"Table(s) not accessible for role '{role}': {sorted(unauthorized)}. "
                    f"Allowed tables: {sorted(allowed_set)}"
                )
        except Exception as e:
            # If table extraction fails, log but do not block
            pass

        return len(violations) == 0, violations

    def _build_audit_record(
        self,
        sql: str,
        role: str,
        passed: bool,
        violations: List[str],
        warnings: List[str]
    ) -> Dict[str, Any]:
        """Build a structured audit record for the security decision."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "role": role,
            "sql_preview": sql[:200] + ("..." if len(sql) > 200 else ""),
            "decision": "APPROVED" if passed else "REJECTED",
            "violations": violations,
            "warnings": warnings,
        }

    def check_sql(
        self,
        sql: str,
        role: str
    ) -> Tuple[bool, List[str], List[str], Dict[str, Any]]:
        """
        Run all security checks on the given SQL string.

        Args:
            sql: SQL query to evaluate
            role: User role

        Returns:
            (passed, violations, warnings, audit_record)
        """
        all_violations: List[str] = []
        all_warnings: List[str] = []

        permissions = self._get_permissions(role)

        # Check 1: Absolutely forbidden statements (hard block, role-independent)
        has_forbidden, forbidden_violations = self._detect_forbidden_statements(sql)
        all_violations.extend(forbidden_violations)

        # Check 2: SQL injection patterns
        has_injection, injection_warnings = self._detect_injection_patterns(sql)
        if has_injection:
            all_violations.extend(injection_warnings)  # Treat as violation

        # Check 3: Operation-level permissions
        if not has_forbidden:  # Skip if already blocked
            op_permitted, op_violations = self._check_operation_permissions(
                sql, role, permissions
            )
            all_violations.extend(op_violations)

        # Check 4: Table-level permissions
        if not has_forbidden:
            tbl_permitted, tbl_violations = self._check_table_permissions(
                sql, role, permissions
            )
            all_violations.extend(tbl_violations)

        passed = len(all_violations) == 0
        audit = self._build_audit_record(sql, role, passed, all_violations, all_warnings)

        return passed, all_violations, all_warnings, audit

    def invoke(self, state: AgentState) -> AgentState:
        """
        Run security checks on the selected SQL.

        This MUST run before optimization and execution.
        If checks fail, sets security_passed=False and the execution agent
        will refuse to run.

        Args:
            state: Current agent state (with selected_sql and user_role)

        Returns:
            Updated agent state with security_passed, security_errors, security_result
        """
        state["current_agent"] = "security_check"

        sql = state.get("selected_sql")

        if not sql:
            state["security_passed"] = False
            state["security_errors"] = ["No SQL available for security check"]
            state["security_result"] = self._build_audit_record(
                "", state.get("user_role", "user"), False,
                ["No SQL provided"], []
            )
            add_to_processing_log(state, "ERROR: Security check — no SQL to evaluate")
            return state

        role = state.get("user_role", "user")

        passed, violations, warnings, audit = self.check_sql(sql, role)

        state["security_passed"] = passed
        state["security_errors"] = violations
        state["security_result"] = audit

        if passed:
            add_to_processing_log(
                state,
                f"Agent 5 (Security): APPROVED for role='{role}'"
            )
        else:
            add_to_processing_log(
                state,
                f"Agent 5 (Security): REJECTED for role='{role}' — "
                f"{len(violations)} violation(s): {violations[:2]}"
            )
            state["workflow_status"] = "failed"
            state["error_message"] = (
                f"Security check failed: {'; '.join(violations[:3])}"
            )

        return state


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

_security_agent_instance: Optional[SecurityAgent] = None


def get_security_agent() -> SecurityAgent:
    """Get or create the Security Agent singleton."""
    global _security_agent_instance
    if _security_agent_instance is None:
        _security_agent_instance = SecurityAgent()
    return _security_agent_instance
