# Agent Contracts — NL2SQL 8-Agent System

This document specifies the formal input/output contract for each agent.

---

## Agent 1: Intent Understanding

**File**: ackend/agents/intent_agent.py
**Class**: IntentUnderstandingAgent

### Responsibility
Parse the natural language question into a structured intent representation.
Identifies entities, conditions, SQL operations, question type, and ambiguous terms.

### Input State Fields
| Field | Type | Description |
|-------|------|-------------|
| question | str | Original NL question |

### Output State Fields
| Field | Type | Description |
|-------|------|-------------|
| intent | Dict | Parsed intent: entities, conditions, operations, question_type, confidence |
| intent_confidence | float | Confidence score 0.0–1.0 |

### Failure Behavior
- If LLM not configured: workflow_status = "failed", error_message set
- If LLM raises exception: intent set with confidence=0.0, pipeline continues

### Retry Behavior
Not applicable (no retry for intent agent).

---

## Agent 2: Schema Retrieval

**File**: ackend/agents/schema_agent.py
**Class**: SchemaRetrievalAgent

### Responsibility
Retrieve relevant database schema information using RAG (ChromaDB).
Reduces LLM context to only the tables/columns relevant to the question.

### Input State Fields
| Field | Type | Description |
|-------|------|-------------|
| question | str | Original NL question |
| intent | Dict | Parsed intent (used to enhance search query) |

### Output State Fields
| Field | Type | Description |
|-------|------|-------------|
| elevant_tables | List[str] | Table names ranked by relevance |
| 	able_schemas | Dict | Schema details for each relevant table |
| oreign_keys | List[Dict] | FK relationships between relevant tables |
| schema_relevance_scores | Dict | Cosine similarity scores per table |

### Failure Behavior
- If ChromaDB not available: returns empty lists, pipeline continues without schema
- If DB not connected: logs warning, returns empty schema

### Retry Behavior
Not applicable.

---

## Agent 3: SQL Generation

**File**: ackend/agents/sql_generation_agent.py
**Class**: SQLGenerationAgent

### Responsibility
Generate 3 SQL candidate queries from the intent and schema using LLM.
Multiple candidates increase the probability that at least one passes validation.

### Input State Fields
| Field | Type | Description |
|-------|------|-------------|
| question | str | Original NL question |
| intent | Dict | Parsed intent |
| elevant_tables | List[str] | Tables to use |
| 	able_schemas | Dict | Column definitions |
| oreign_keys | List[Dict] | FK relationships |

### Output State Fields
| Field | Type | Description |
|-------|------|-------------|
| sql_candidates | List[Dict] | 2–3 candidates with sql, confidence, explanation |
| selected_sql | str | LLM's suggested best candidate |
| generation_metadata | Dict | num_candidates, dialect, selected_index |

### Failure Behavior
- If LLM not configured: workflow_status = "failed"
- If LLM raises exception: sql_candidates = [], selected_sql = None

### Retry Behavior
- Called again via etry_generation(state, errors) when validation fails
- etry_count is incremented BEFORE the LLM call in etry_generation
- Error messages from validation are supplied as context in the retry prompt

---

## Agent 4: Validation

**File**: ackend/agents/validation_agent.py
**Class**: SQLValidationAgent

### Responsibility
Validate all SQL candidates across three dimensions:
1. **Syntax** — parseable by sqlglot AST parser
2. **Schema** — all referenced tables exist in retrieved schema
3. **Semantic** — SQL operations match parsed intent (hard check)

Selects the highest-scoring valid candidate.

### Input State Fields
| Field | Type | Description |
|-------|------|-------------|
| sql_candidates | List[Dict] | Candidates from Agent 3 |
| selected_sql | str | LLM-suggested candidate |
| 	able_schemas | Dict | Retrieved schema |
| oreign_keys | List[Dict] | FK relationships |
| intent | Dict | Parsed intent (for semantic check) |
| question | str | Original question |

### Output State Fields
| Field | Type | Description |
|-------|------|-------------|
| is_valid | bool | True iff syntax AND schema AND semantic all pass |
| selected_sql | str | Best valid candidate (updated) |
| alidation_result | Dict | Per-dimension results + candidate scores |
| alidation_errors | List[str] | Errors for retry feedback |

### Validity Formula
`
is_valid = syntax_valid AND schema_valid AND semantic_valid
`

### Failure Behavior
- All candidates fail → is_valid = False, errors collected for retry
- No candidates → is_valid = False, immediate error

### Retry Behavior
The orchestrator checks is_valid and etry_count < max_retries.
If retry is triggered, validation_errors are passed back to Agent 3.

---

## Agent 5: Security Check

**File**: ackend/agents/security_agent.py
**Class**: SecurityAgent

### Responsibility
Enforce security policies BEFORE execution:
- Reject absolutely forbidden statements (DROP, ALTER, TRUNCATE, GRANT, REVOKE, CREATE)
- Enforce RBAC: user/analyst/guest may only SELECT
- Detect SQL injection heuristics
- Generate a full audit record

### Input State Fields
| Field | Type | Description |
|-------|------|-------------|
| selected_sql | str | The SQL to evaluate |
| user_role | str | Requesting user's role |

### Output State Fields
| Field | Type | Description |
|-------|------|-------------|
| security_passed | bool | True iff all checks pass |
| security_errors | List[str] | Violation descriptions |
| security_result | Dict | Full audit record (timestamp, role, decision, sql_preview) |

### Failure Behavior
- On violation: security_passed = False, workflow_status = "failed", error_message set
- Execution agent checks security_passed and will refuse to run if False

### Retry Behavior
Security violations are NOT retried. The pipeline fails immediately.

---

## Agent 6: Optimization

**File**: ackend/agents/optimization_agent.py
**Class**: QueryOptimizationAgent

### Responsibility
Improve SQL performance without changing semantic meaning:
- Normalize whitespace and keyword casing (rule-based)
- Flag SELECT * for review
- LLM-based: subquery rewriting, predicate pushdown, index suggestions

### Precondition
Only runs if is_valid=True AND security_passed=True.

### Input State Fields
| Field | Type | Description |
|-------|------|-------------|
| selected_sql | str | Validated SQL |
| 	able_schemas | Dict | For LLM optimization context |
| is_valid | bool | Must be True |
| security_passed | bool | Must be True |

### Output State Fields
| Field | Type | Description |
|-------|------|-------------|
| original_sql | str | SQL before optimization |
| optimized_sql | str | SQL after optimization |
| optimizations_applied | List[str] | Applied optimization descriptions |

### Failure Behavior
- If optimization fails: original SQL is kept, pipeline continues

---

## Agent 7: SQL Execution

**File**: ackend/agents/execution_agent.py
**Class**: SQLExecutionAgent

### Responsibility
Execute the optimized SQL against the database safely.
WILL REFUSE to execute if security_passed=False or is_valid=False.

### Input State Fields
| Field | Type | Description |
|-------|------|-------------|
| optimized_sql | str | SQL to execute (falls back to selected_sql) |
| security_passed | bool | MUST be True to proceed |
| is_valid | bool | MUST be True to proceed |

### Output State Fields
| Field | Type | Description |
|-------|------|-------------|
| execution_success | bool | True if query ran without error |
| query_results | List | Result rows |
| esult_columns | List[str] | Column names |
| execution_time_ms | float | Wall-clock time in milliseconds |
| execution_error | str | Error message if failed |

### Safety Guarantees
- Row limit: MAX_ROWS_RETURNED (default 1000)
- Timeout: MAX_QUERY_TIMEOUT seconds (default 30)
- Refuses if security_passed=False
- Uses SQLAlchemy's public API (not cursor.description)

### Failure Behavior
- Execution errors update execution_success=False and execution_error
- Timeout results in a descriptive error message
- Pipeline continues to Explanation even on execution failure

---

## Agent 8: Explanation

**File**: ackend/agents/explanation_agent.py
**Class**: ExplanationAgent

### Responsibility
Generate a plain-English explanation of the SQL and its results.
Falls back to a template-based explanation if LLM is unavailable.

### Input State Fields
| Field | Type | Description |
|-------|------|-------------|
| question | str | Original NL question |
| optimized_sql | str | Final SQL that was executed |
| query_results | List | Result rows |
| esult_columns | List[str] | Column names |
| include_explanation | bool | If False, skip generation |

### Output State Fields
| Field | Type | Description |
|-------|------|-------------|
| sql_explanation | str | Plain-English description of what SQL does |
| esult_summary | str | What the results mean for the original question |
| insights | List[str] | Key patterns/insights from the data |

### Failure Behavior
- If LLM fails: falls back to template-based explanation
- Never crashes the pipeline
