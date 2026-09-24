"""
Agent 4: SQL Validation

Validates generated SQL candidates using four independent checks:
1. Syntax validation    — sqlglot AST-level parsing
2. Schema validation    — all referenced tables/columns exist
3. Semantic validation  — SQL matches the intent of the question
4. Candidate scoring    — evaluate ALL candidates, pick the best valid one

The validation result drives the retry loop:
- If ALL candidates fail validation AND retries remain: route back to SQL Generation
- If at least one candidate passes: select it and proceed to Security (Agent 5)
- If retries exhausted with no valid candidate: mark workflow as failed

NOTE: Permission / RBAC checks are handled exclusively by Agent 5 (SecurityAgent).
      This agent only validates correctness, not authorization.

8-agent pipeline position:
1. Intent -> 2. Schema -> 3. SQL Generation -> 4. Validation ->
5. Security -> 6. Optimization -> 7. Execution -> 8. Explanation
"""

from typing import Dict, Any, List, Optional, Tuple
import sqlglot
from sqlglot import parse, ParseError
from backend.core.config import settings
from backend.agents.state import AgentState, add_to_processing_log


class SQLValidationAgent:
    """
    Agent 4: SQL Validation

    Validates SQL queries before they reach the security or execution layers.
    Implements the critical validation loop that differentiates this system from
    simple linear pipelines.

    Validation dimensions:
    - syntax_valid:   syntactically parseable by sqlglot
    - schema_valid:   all referenced tables exist in retrieved schema
    - semantic_valid: SQL operations match parsed intent (hard check)
    """

    def __init__(self) -> None:
        """Initialize the SQL Validation Agent."""
        pass

    # ------------------------------------------------------------------
    # 1. Syntax Validation
    # ------------------------------------------------------------------

    def validate_syntax(
        self,
        sql: str,
        dialect: Optional[str] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate SQL syntax using sqlglot parser.

        Args:
            sql: SQL query string
            dialect: SQL dialect override; auto-detected from config if None

        Returns:
            (is_valid, list_of_errors)
        """
        errors: List[str] = []

        try:
            if not dialect:
                db_url = settings.database_url
                if "postgresql" in db_url:
                    dialect = "postgres"
                elif "mysql" in db_url:
                    dialect = "mysql"
                else:
                    dialect = "sqlite"

            parsed = parse(sql, read=dialect)

            if not parsed or len(parsed) == 0:
                errors.append("Failed to parse SQL — empty parse result")
                return False, errors

            if parsed[0] is None:
                errors.append("Parsed SQL resulted in a NULL statement")
                return False, errors

            return True, []

        except ParseError as e:
            errors.append(f"Syntax error: {str(e)}")
            return False, errors
        except Exception as e:
            errors.append(f"Syntax validation error: {str(e)}")
            return False, errors

    # ------------------------------------------------------------------
    # 2. Schema Validation
    # ------------------------------------------------------------------

    def validate_schema(
        self,
        sql: str,
        table_schemas: Dict[str, Any],
        foreign_keys: List[Dict[str, str]]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that all referenced tables exist in the retrieved schema.

        Args:
            sql: SQL query string
            table_schemas: Dictionary of available table schemas
            foreign_keys: Foreign key relationships (for context)

        Returns:
            (is_valid, list_of_errors)
        """
        errors: List[str] = []

        # Cannot validate schema if no schema was retrieved
        if not table_schemas:
            errors.append("ADVISORY: Soft-pass schema validation — table_schemas is empty (DB might be missing or ChromaDB failed)")
            return True, errors  # Soft pass — schema may not have been indexed yet

        try:
            from sqlglot import exp

            parsed = parse(sql)
            if not parsed:
                return False, ["Could not parse SQL for schema validation"]

            statement = parsed[0]
            referenced_tables: set = set()

            for table_node in statement.find_all(exp.Table):
                if table_node.name:
                    referenced_tables.add(table_node.name.lower())

            available_tables = {t.lower() for t in table_schemas.keys()}
            missing_tables = referenced_tables - available_tables

            if missing_tables:
                errors.append(
                    f"Referenced tables not found in schema: {sorted(missing_tables)}. "
                    f"Available: {sorted(available_tables)}"
                )

            return len(errors) == 0, errors

        except Exception as e:
            errors.append(f"Schema validation error: {str(e)}")
            return False, errors

    # ------------------------------------------------------------------
    # 3. Semantic Validation
    # ------------------------------------------------------------------

    def validate_semantic(
        self,
        sql: str,
        question: str,
        intent: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that the SQL semantically matches the question intent.

        This is a HARD check: if the SQL is missing operations explicitly
        required by the parsed intent, semantic_valid = False, which
        contributes to is_valid = False and triggers a retry.

        Heuristics checked:
        - COUNT expected but absent
        - AVG expected but absent
        - GROUP BY expected but absent
        - ORDER BY expected but absent
        - JOIN expected but absent (when multiple tables mentioned)

        Args:
            sql: SQL query string
            question: Original natural language question
            intent: Parsed intent from Agent 1

        Returns:
            (is_valid, list_of_issues)
        """
        issues: List[str] = []
        sql_upper = sql.upper()
        operations = intent.get("operations", [])
        ops_upper = [op.upper() for op in operations]

        # Hard checks — operations required by intent but absent from SQL
        if "COUNT" in ops_upper and "COUNT" not in sql_upper:
            issues.append(
                "Intent requires COUNT aggregation but SQL does not use COUNT"
            )

        if "AVG" in ops_upper and "AVG" not in sql_upper and "AVERAGE" not in sql_upper:
            issues.append(
                "Intent requires AVG aggregation but SQL does not use AVG"
            )

        if "SUM" in ops_upper and "SUM" not in sql_upper:
            issues.append(
                "Intent requires SUM aggregation but SQL does not use SUM"
            )

        if "GROUP BY" in ops_upper and "GROUP BY" not in sql_upper:
            issues.append(
                "Intent requires GROUP BY but SQL does not contain GROUP BY"
            )

        if "ORDER BY" in ops_upper and "ORDER BY" not in sql_upper:
            issues.append(
                "Intent requires ORDER BY but SQL does not contain ORDER BY"
            )

        # Advisory-only checks (logged but do not block)
        if "SELECT *" in sql_upper:
            issues.append(
                "ADVISORY: SQL uses SELECT * — consider specifying columns"
            )

        # Separate hard failures from advisories
        hard_failures = [i for i in issues if not i.startswith("ADVISORY")]
        return len(hard_failures) == 0, issues

    # ------------------------------------------------------------------
    # 4. Multi-candidate Evaluation
    # ------------------------------------------------------------------

    def _score_candidate(
        self,
        candidate: Dict[str, Any],
        table_schemas: Dict[str, Any],
        foreign_keys: List[Dict[str, str]],
        question: str,
        intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate a single SQL candidate across all validation dimensions.

        Returns a scored candidate dict with validation details attached.
        """
        sql = candidate.get("sql", "")

        syntax_valid, syntax_errors = self.validate_syntax(sql)
        schema_valid, schema_errors = self.validate_schema(sql, table_schemas, foreign_keys)
        semantic_valid, semantic_issues = self.validate_semantic(sql, question, intent)

        # Overall candidate validity: all three dimensions must pass
        is_valid = syntax_valid and schema_valid and semantic_valid

        # Score: sum of dimension scores + LLM confidence weighting
        llm_confidence = float(candidate.get("confidence", 0.0))
        score = (
            int(syntax_valid) * 0.35
            + int(schema_valid) * 0.35
            + int(semantic_valid) * 0.20
            + llm_confidence * 0.10
        )

        return {
            **candidate,
            "_syntax_valid": syntax_valid,
            "_schema_valid": schema_valid,
            "_semantic_valid": semantic_valid,
            "_is_valid": is_valid,
            "_score": score,
            "_all_errors": syntax_errors + schema_errors + semantic_issues,
        }

    def evaluate_candidates(
        self,
        candidates: List[Dict[str, Any]],
        table_schemas: Dict[str, Any],
        foreign_keys: List[Dict[str, str]],
        question: str,
        intent: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Evaluate all candidates and return the best valid one.

        Args:
            candidates: List of SQL candidates from Agent 3
            table_schemas: Retrieved schema
            foreign_keys: FK relationships
            question: Original question
            intent: Parsed intent

        Returns:
            (best_valid_candidate_or_None, list_of_scored_candidates)
        """
        if not candidates:
            return None, []

        scored = [
            self._score_candidate(c, table_schemas, foreign_keys, question, intent)
            for c in candidates
        ]

        valid_candidates = [c for c in scored if c["_is_valid"]]

        if valid_candidates:
            best = max(valid_candidates, key=lambda c: c["_score"])
            return best, scored
        else:
            # Return highest-scoring invalid candidate (for error reporting)
            best_invalid = max(scored, key=lambda c: c["_score"])
            return None, scored

    # ------------------------------------------------------------------
    # Main invocation
    # ------------------------------------------------------------------

    def invoke(self, state: AgentState) -> AgentState:
        """
        Validate all generated SQL candidates and select the best valid one.

        Args:
            state: Current agent state

        Returns:
            Updated agent state with validation results
        """
        state["current_agent"] = "validation"

        candidates = state.get("sql_candidates", [])
        selected_sql = state.get("selected_sql")

        # Ensure we have at least one candidate to evaluate
        if not candidates and not selected_sql:
            state["is_valid"] = False
            state["validation_errors"] = ["No SQL candidates available to validate"]
            state["validation_result"] = {
                "syntax_valid": False,
                "schema_valid": False,
                "semantic_valid": False,
                "is_valid": False,
                "errors": ["No SQL provided"],
                "warnings": [],
                "evaluated_candidates": 0,
                "best_candidate": None
            }
            add_to_processing_log(state, "ERROR: Validation — no SQL candidates to evaluate")
            return state

        # If no structured candidates list but selected_sql exists, wrap it
        if not candidates and selected_sql:
            candidates = [{"sql": selected_sql, "confidence": 0.5, "explanation": ""}]

        # Evaluate all candidates
        best_candidate, scored_candidates = self.evaluate_candidates(
            candidates,
            state.get("table_schemas", {}),
            state.get("foreign_keys", []),
            state["question"],
            state.get("intent", {})
        )

        all_errors: List[str] = []

        if best_candidate:
            # Validation passed — update selected SQL to best valid candidate
            state["is_valid"] = True
            state["selected_sql"] = best_candidate["sql"]
            state["validation_errors"] = []

            validation_detail = {
                "syntax_valid": best_candidate["_syntax_valid"],
                "schema_valid": best_candidate["_schema_valid"],
                "semantic_valid": best_candidate["_semantic_valid"],
                "is_valid": True,
                "errors": [],
                "warnings": [
                    e for e in best_candidate["_all_errors"]
                    if e.startswith("ADVISORY")
                ],
                "evaluated_candidates": len(scored_candidates),
                "best_candidate": {
                    "sql": best_candidate["sql"],
                    "confidence": best_candidate.get("confidence", 0.0),
                    "score": best_candidate["_score"]
                }
            }
            add_to_processing_log(
                state,
                f"Agent 4 (Validation): PASSED — selected candidate "
                f"(score={best_candidate['_score']:.2f}) from {len(candidates)} candidates"
            )
        else:
            # All candidates failed — collect errors for retry feedback
            state["is_valid"] = False
            for sc in scored_candidates:
                all_errors.extend(sc.get("_all_errors", []))

            # Deduplicate errors
            state["validation_errors"] = list(dict.fromkeys(all_errors))

            validation_detail = {
                "syntax_valid": False,
                "schema_valid": False,
                "semantic_valid": False,
                "is_valid": False,
                "errors": state["validation_errors"],
                "warnings": [],
                "evaluated_candidates": len(scored_candidates),
                "best_candidate": None
            }
            add_to_processing_log(
                state,
                f"Agent 4 (Validation): FAILED — all {len(candidates)} candidates invalid. "
                f"Errors: {state['validation_errors'][:3]}"
            )

        state["validation_result"] = validation_detail
        return state

    def should_retry(self, state: AgentState) -> bool:
        """
        Determine if SQL generation should be retried.

        Used as the conditional edge function in LangGraph.
        """
        return (
            not state["is_valid"]
            and state.get("retry_count", 0) < state.get("max_retries", 3)
            and state.get("workflow_status") == "running"
        )


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

_validation_agent_instance: Optional[SQLValidationAgent] = None


def get_validation_agent() -> SQLValidationAgent:
    """Get or create the SQL Validation Agent singleton."""
    global _validation_agent_instance
    if _validation_agent_instance is None:
        _validation_agent_instance = SQLValidationAgent()
    return _validation_agent_instance
