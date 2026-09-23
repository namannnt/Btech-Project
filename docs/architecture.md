# Architecture — NL2SQL 8-Agent System

## Overview

This system converts natural language questions into executable SQL queries using a multi-agent pipeline orchestrated by **LangGraph**. Each agent has a single, well-defined responsibility. Agents communicate through a shared AgentState object that flows through the directed graph.

---

## Agent Pipeline

`mermaid
flowchart TD
    U([User Query]) --> A1

    A1[Agent 1\nIntent Understanding]
    A2[Agent 2\nSchema Retrieval]
    A3[Agent 3\nSQL Generation]
    A4[Agent 4\nValidation]
    A5[Agent 5\nSecurity Check]
    A6[Agent 6\nOptimization]
    A7[Agent 7\nSQL Execution]
    A8[Agent 8\nExplanation]

    RETRY[SQL Generation Retry\nwith error feedback]
    END_FAIL([Pipeline Fail])
    END_OK([Final Response])

    A1 --> A2
    A2 --> A3
    A3 --> A4

    A4 -->|is_valid=True| A5
    A4 -->|is_valid=False\nretries_left| RETRY
    A4 -->|is_valid=False\nno_retries_left| END_FAIL

    RETRY --> A4

    A5 -->|security_passed=True| A6
    A5 -->|security_passed=False| END_FAIL

    A6 --> A7
    A7 --> A8
    A8 --> END_OK
`

---

## Execution Order

Security runs **BEFORE** execution by design. This prevents any unsafe SQL from touching the database.

`
1. Intent Understanding      parse entities, operations, question type
2. Schema Retrieval          RAG (ChromaDB) — retrieve relevant table schemas
3. SQL Generation            generate 3 SQL candidates using LLM
4. Validation                syntax + schema + semantic — pick best valid candidate
   └── RETRY loop            if all candidates fail, retry up to max_retries times
5. Security Check            RBAC + forbidden statement detection + injection heuristics
   └── FAIL fast             if rejected, execution is prevented
6. Optimization              rule-based + LLM-based SQL optimization
7. SQL Execution             safe execution with timeout and row limit
8. Explanation               LLM-generated plain-English answer
`

---

## State Transitions

| Node | Input fields | Output fields |
|------|-------------|---------------|
| intent_understanding | question | intent, intent_confidence |
| schema_retrieval | question, intent | elevant_tables, 	able_schemas, oreign_keys, schema_relevance_scores |
| sql_generation | question, intent, 	able_schemas, oreign_keys | sql_candidates, selected_sql, generation_metadata |
| alidation | sql_candidates, 	able_schemas, intent | is_valid, selected_sql, alidation_result, alidation_errors |
| sql_generation_retry | selected_sql, alidation_errors, etry_count | sql_candidates, selected_sql, etry_count (+1) |
| security_check | selected_sql, user_role | security_passed, security_errors, security_result |
| optimization | selected_sql, 	able_schemas | original_sql, optimized_sql, optimizations_applied |
| execution | optimized_sql, security_passed, is_valid | execution_success, query_results, esult_columns, execution_time_ms |
| explanation | question, optimized_sql, query_results, esult_columns | sql_explanation, esult_summary, insights |

---

## Validation Logic

`python
is_valid = syntax_valid AND schema_valid AND semantic_valid
`

All three dimensions must pass. Semantic validation is a **hard check**:
- If intent requires COUNT but SQL has no COUNT → semantic_valid = False
- If intent requires GROUP BY but SQL has none → semantic_valid = False

Validation evaluates **all candidates**, not just the LLM's selected index.
The highest-scoring valid candidate is promoted to selected_sql.

---

## Security Model

| Role | SELECT | INSERT | UPDATE | DELETE | DDL (DROP/ALTER) |
|------|--------|--------|--------|--------|------------------|
| guest | ✓ (restricted tables) | ✗ | ✗ | ✗ | ✗ |
| user | ✓ | ✗ | ✗ | ✗ | ✗ |
| analyst | ✓ | ✗ | ✗ | ✗ | ✗ |
| admin | ✓ | ✓ | ✓ | ✓ | ✗ |

**DDL statements (DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE) are rejected for ALL roles.**

---

## Retry Loop

`
Retry count starts at 0.
After each failed validation:
  retry_count += 1
  SQL Generation is called again with validation_errors as feedback

Termination conditions:
  - is_valid = True  → proceed to security
  - retry_count >= max_retries  → fail
  - workflow_status != "running"  → fail
`

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | LangGraph (stateful directed graph) |
| LLM (primary) | OpenAI gpt-4o-mini |
| LLM (fallback) | Groq Llama-3.1-70b-versatile |
| Schema RAG | ChromaDB + sentence-transformers |
| SQL Parsing | sqlglot (AST-level) |
| Database | SQLAlchemy (SQLite / PostgreSQL / MySQL) |
| API | FastAPI + Uvicorn |
| Frontend | Streamlit |
