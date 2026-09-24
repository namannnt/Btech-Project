# Multi-Agent NL2SQL — QA Test Report

**Date:** 2026-09-24  
**Tester:** Automated QA / Antigravity  
**Project:** Btech-Project — Multi-Agent Natural Language to SQL System  
**Repository:** namannnt/Btech-Project

---

## 1. Executive Summary

**Overall System State: PARTIALLY WORKING**

The system is architecturally sound, starts successfully, and demonstrates correct security blocking of destructive queries. All 88 automated unit/integration tests pass. However, the system **cannot produce correct end-to-end results** in its current state due to two critical, compounding failures:

1. **CRITICAL: Both SQLite database files are empty (0 bytes)** — there are no tables, no data.  
2. **CRITICAL: Agent 1 (Intent Understanding) fails on every query** — a bug in the ChatPromptTemplate variable escaping causes the intent pipeline to crash on every call.

Because the database is empty, all SQL execution attempts fail with `no such table: <tablename>`. Because the Intent Agent fails, Agent 2 (Schema Retrieval) always returns zero tables, which means the SQL generation LLM has no schema context and is forced to hallucinate table names.

Despite these failures, the LLM continues to generate SQL from the question text alone, the validation/security/optimization pipeline runs, and security correctly blocks destructive queries. The architecture and agent wiring are correct.

---

## 2. Environment

| Property | Value |
|----------|-------|
| Python Version | 3.14.0 |
| OS | Windows 10 |
| LLM Provider | Groq |
| Model (Intent, SQL Gen, Optimization) | `openai/gpt-oss-120b` (FALLBACK_LLM_MODEL in .env) |
| Model (Explanation) | `openai/gpt-oss-20b` (EXPLANATION_LLM_MODEL in .env) |
| Database | SQLite — `sqlite:///./backend/data/sample.db` |
| Embedding Model | `sentence-transformers/all-MiniLM-L6-v2` (384-dim) |
| ChromaDB | Initialized successfully |
| OpenAI API Key | NOT SET (empty string in .env) |
| Groq API Key | SET (valid key present — REDACTED) |

> [!CAUTION]
> All API keys are REDACTED in this report. GROQ_API_KEY=***REDACTED***

---

## 3. Application Startup

| Property | Value |
|----------|-------|
| Startup Command | `python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000` |
| Alternative | `python main.py` |
| Port | 8000 |
| Startup Result | **SUCCESS** |
| Startup Time | ~5 seconds (embedding model loads during startup) |

**Health Check Response (`GET /api/v1/health`):**
```json
{
  "status": "healthy",
  "llm_configured": true,
  "database_connected": true,
  "agents_loaded": 8
}
```

Note: `database_connected: true` is misleading — the DB file opens but has 0 tables.

**Startup Warnings (non-fatal):**

1. `UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.`
2. `DeprecationWarning: HuggingFaceEmbeddings deprecated in LangChain 0.2.2`
3. `DeprecationWarning: langchain-community is being sunset`
4. `DeprecationWarning: on_event is deprecated, use lifespan event handlers`
5. `[Startup] Indexed 0 tables from sqlite:///./backend/data/sample.db` — **CRITICAL: database is empty**

---

## 4. Database Schema

**CRITICAL FINDING: Both database files exist but are 0 bytes (completely empty).**

| Path | Exists | Size | Tables |
|------|--------|------|--------|
| `backend/data/sample.db` | YES | **0 bytes** | **NONE** |
| `data/sample.db` | YES | **0 bytes** | **NONE** |

Tables assumed by LLM (hallucinated from question text):

| Table | Actually Exists |
|-------|-----------------|
| `customers` | NO |
| `orders` | NO |
| `order_items` | NO |
| `products` | NO |
| `transactions` | NO |
| `sales` | NO |

**No seed/migration script exists in the repository. The `.db` files were committed as empty placeholder files.**

---

## 5. Query Test Results (End-to-End)

| ID | Natural Language Query | Generated SQL (abbreviated) | Result | Classification |
|----|------------------------|-----------------------------|--------|----------------|
| T01 | Show me the total number of records in each table. | `SELECT 'table1' AS table_name, COUNT(*) ... UNION ALL ...` | Security blocked (UNION ALL false positive) | **FAIL** |
| T02 | Show me all customers from India. | `SELECT customer_id, name, country FROM customers WHERE country = 'India'` | Exec: `no such table: customers` | **PARTIAL** |
| T03 | Show me the top 5 customers by total spending. | `SELECT c.customer_id, c.name, SUM(oi.qty * oi.price) FROM customers ... LIMIT 5` | Exec: `no such table: customers` | **PARTIAL** |
| T04 | Show me the 10 highest value transactions. | `SELECT * FROM transactions ORDER BY amount DESC LIMIT 10` | Exec: `no such table: transactions` | **PARTIAL** |
| T05 | Show me the names of customers and the orders they placed. | `SELECT c.name, o.order_id, o.order_date FROM customers INNER JOIN orders ...` | Exec: `no such table: customers` | **PARTIAL** |
| T06 | Show me total sales by month. | `SELECT DATE_TRUNC('month', sale_date) AS month, SUM(amount) FROM sales ...` | Exec: `no such table: sales` + PostgreSQL function in SQLite | **PARTIAL** |
| T07 | Show me customers who spent more than 5000 and placed at least 3 orders. | `SELECT c.id, c.name FROM customers c JOIN (SELECT ... HAVING SUM > 5000 AND COUNT >= 3) ...` | Exec: `no such table: customers` | **PARTIAL** |
| T08 | Which products have been purchased by customers from India? | `SELECT p.product_name FROM products p WHERE EXISTS (... JOIN customers c WHERE c.country = 'India')` | Exec: `no such table: products` | **PARTIAL** |
| T09 | Show me the best customers. | `SELECT customer_id, customer_name, total_spent FROM customers ORDER BY total_spent DESC LIMIT 10` | Exec: `no such table: customers` | **PARTIAL** |
| T10 | Show me information about employees that does not exist in the database. | `SELECT NULL AS employee_info LIMIT 0` | Success — 0 rows, graceful no-op | **PASS** |
| T11 | Delete all customers. | `DELETE FROM customers;` | Security blocked — DELETE not permitted for 'user' | **BLOCKED_CORRECTLY** |
| T12 | Update every customer's balance to 0. | `UPDATE customers SET balance = 0;` | Security blocked — UPDATE not permitted for 'user' | **BLOCKED_CORRECTLY** |

**Results: 1 PASS / 8 PARTIAL (SQL correct, execution fails on empty DB) / 1 FAIL (false positive) / 2 BLOCKED_CORRECTLY**

---

## 6. Agent-by-Agent Pipeline Analysis

| Test | A1 Intent | A2 Schema | A3 SQL Gen | A4 Validation | A5 Security | A6 Optimization | A7 Execution | A8 Explanation |
|------|-----------|-----------|------------|---------------|-------------|-----------------|--------------|----------------|
| T01 | **ERROR** | 0 tables | PASS | PASS | **REJECTED** (FP) | SKIPPED | SKIPPED | SKIPPED |
| T02 | **ERROR** | 0 tables | PASS | PASS | APPROVED | PASS | **FAIL** (no table) | PASS |
| T03 | **ERROR** | 0 tables | FAIL→**RETRY**→PASS | PASS | APPROVED | PASS | **FAIL** (no table) | PASS |
| T04 | **ERROR** | 0 tables | FAIL→**RETRY**→PASS | PASS | APPROVED | PASS | **FAIL** (no table) | PASS |
| T05 | **ERROR** | 0 tables | PASS | PASS | APPROVED | PASS | **FAIL** (no table) | PASS |
| T06 | **ERROR** | 0 tables | FAIL→**RETRY**→PASS | PASS | APPROVED | PASS | **FAIL** (no table) | PASS |
| T07 | **ERROR** | 0 tables | PASS | PASS | APPROVED | PASS | **FAIL** (no table) | PASS |
| T08 | **ERROR** | 0 tables | PASS | PASS | APPROVED | PASS | **FAIL** (no table) | PASS |
| T09 | **ERROR** | 0 tables | FAIL→**RETRY**→PASS | PASS | APPROVED | PASS | **FAIL** (no table) | PASS |
| T10 | **ERROR** | 0 tables | PASS | PASS | APPROVED | PASS | **PASS** | PASS |
| T11 | **ERROR** | 0 tables | PASS | PASS | **REJECTED** | SKIPPED | SKIPPED | SKIPPED |
| T12 | **ERROR** | 0 tables | PASS | PASS | **REJECTED** | SKIPPED | SKIPPED | SKIPPED |

**Key findings:**
- Agent 1 (Intent): 100% failure rate — prompt template bug (BUG-002)
- Agent 2 (Schema): Always returns 0 tables — consequence of empty database (BUG-001)
- Agent 3 (SQL Gen): Mostly succeeds — generates plausible SQL without schema context
- Agent 4 (Validation): Soft-passes all — table_schemas is empty so schema check is bypassed (BUG-006)
- Agent 5 (Security): Correctly blocks T11/T12; false positive on T01 UNION ALL (BUG-003)
- Agent 6 (Optimization): Applies 2-6 optimizations per query — working correctly
- Agent 7 (Execution): Fails on all non-trivial queries — tables don't exist (BUG-001)
- Agent 8 (Explanation): Generates explanations even on failure — graceful degradation
- **Retry loop CONFIRMED WORKING** — T03, T04, T06, T09 show retry_count=1

---

## 7. Security Testing

### Destructive Query Blocking

| Query | SQL Generated | Blocked Before DB | Violation |
|-------|---------------|------------------|-----------|
| "Delete all customers" | `DELETE FROM customers;` | **YES** | Operation 'DELETE' not permitted for role 'user' |
| "Update every customer's balance to 0" | `UPDATE customers SET balance = 0;` | **YES** | Operation 'UPDATE' not permitted for role 'user' |

> [!IMPORTANT]
> Destructive SQL was generated by the LLM but correctly blocked by the Security Agent **before any database interaction**. The empty database was never touched.

### Role-Based Access Control (Unit Tests)

| Role | SELECT | INSERT | UPDATE | DELETE | DDL |
|------|--------|--------|--------|--------|-----|
| user | ALLOWED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| analyst | ALLOWED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| admin | ALLOWED | ALLOWED | ALLOWED | ALLOWED | BLOCKED |
| guest | RESTRICTED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |

### Injection Detection

| Pattern | Tested Via | Result | Assessment |
|---------|------------|--------|------------|
| `UNION ALL SELECT` | T01 (legitimate aggregation) | BLOCKED | **FALSE POSITIVE** — overly broad regex |
| `; DROP TABLE` | Unit test | BLOCKED | Correct |
| `-- comment` | Unit test | BLOCKED | Correct |
| `OR 1=1` | Unit test | BLOCKED | Correct |
| Stacked semicolons | Unit test | BLOCKED | Correct |

---

## 8. Retry / Error Recovery

**Retry loop confirmed working.** T03, T04, T06, T09 all triggered retries.

**T03 Full Pipeline Trace (retry example):**
```
processing_log:
  1. Initialized pipeline for: "Show me the top 5 customers by total spending."
  2. ERROR: Intent understanding failed: missing variables {"column"}
  3. Retrieved 0 relevant tables:
  4. No SQL generated            <- Generation returned nothing usable
  5. ERROR: Validation — no SQL candidates to evaluate
  6. Retry #1: Generated 1 new candidates  <- Retry loop fires
  7. Agent 4 (Validation): PASSED — selected candidate (score=0.90) from 1 candidates
  8. Agent 5 (Security): APPROVED for role='user'
  9. Agent 6 (Optimization): Applied 5 optimization(s)
 10. Agent 7 (Execution): FAILED — (sqlite3.OperationalError) no such table: customers
 11. Agent 8 (Explanation): Explanation generated
```

Retry loop correctly: detects no valid candidates, calls retry_generation with error context, increments retry_count, routes through validation, proceeds to security when SQL is found.

---

## 9. SQL Correctness Analysis

| Test | Syntax | Tables Guessed | Columns Guessed | Dialect | Intent Captured |
|------|--------|----------------|-----------------|---------|-----------------|
| T01 | VALID | Poor (table1/table2/table3 — generic) | N/A | Correct | Partial |
| T02 | VALID | Plausible (customers) | Plausible | Correct | YES |
| T03 | VALID | Plausible (customers, orders, order_items) | Plausible | Correct | YES |
| T04 | VALID | Plausible (transactions) | Plausible | Correct | YES |
| T05 | VALID | Plausible (customers, orders) | Plausible | Correct | YES |
| T06 | VALID | Plausible (sales) | Plausible | **WRONG** — `DATE_TRUNC` is PostgreSQL | YES |
| T07 | VALID | Plausible (customers, orders) | Plausible | Correct | YES — complex HAVING |
| T08 | VALID | Plausible (products, order_items, orders, customers) | Plausible | Correct | YES — EXISTS subquery |
| T09 | VALID | Plausible (customers) | Plausible | Correct | Reasonable — interpreted as top spenders |
| T10 | VALID | None — graceful no-op | N/A | Correct | YES |

**SQL quality is surprisingly high given zero schema context.** The LLM generates correct syntax, semantically appropriate JOINs/aggregations, and reasonable column name guesses for most queries.

---

## 10. Performance

| Test | Response Time | DB Exec | Notes |
|------|---------------|---------|-------|
| T01 | 7.93s | N/A (blocked) | Security fast path |
| T02 | 5.71s | ~3ms (error) | |
| T03 | 7.41s | ~1ms (error) | 1 retry |
| T04 | 6.74s | ~1ms (error) | 1 retry |
| T05 | 21.93s | ~1ms (error) | Complex JOIN |
| T06 | 25.07s | ~1ms (error) | 1 retry + complex |
| T07 | 23.88s | ~1ms (error) | Subquery + HAVING |
| T08 | 19.89s | ~1ms (error) | EXISTS + 3-way JOIN |
| T09 | 13.83s | ~1ms (error) | 1 retry |
| T10 | 18.97s | 0.27ms | Only successful execution |
| T11 | 6.88s | N/A (blocked) | Security fast path |
| T12 | 7.58s | N/A (blocked) | Security fast path |

**Average: ~13.7s** | **Bottleneck: Groq LLM API** (3 calls/query: intent + SQL gen + explanation) | **DB exec when table exists: 0.27ms**

---

## 11. Automated Test Suite

**Command:** `python -m pytest tests/ -v --tb=short`

| Metric | Value |
|--------|-------|
| Total | 88 |
| **Passed** | **88** |
| Failed | 0 |
| Duration | 60.14s |

| File | Tests | Status |
|------|-------|--------|
| test_api.py | 8 | ALL PASS |
| test_api_integration.py | 1 | PASS |
| test_direct_orchestrator.py | 1 | PASS |
| test_execution_agent.py | 7 | ALL PASS |
| test_explanation_agent.py | 6 | ALL PASS |
| test_intent_agent.py | 4 | ALL PASS |
| test_optimization_agent.py | 7 | ALL PASS |
| test_orchestrator.py | 9 | ALL PASS |
| test_schema_agent.py | 5 | ALL PASS |
| test_security_agent.py | 17 | ALL PASS |
| test_sql_generation_agent.py | 6 | ALL PASS |
| test_validation_agent.py | 11 | ALL PASS |

39 deprecation warnings (non-fatal). See BUG-008.

---

## 12. Architecture Compliance

| Requirement | Implemented | Working |
|-------------|-------------|---------|
| 8 separate agent modules | YES | YES |
| LangGraph StateGraph orchestration | YES | YES |
| Agent 1: Intent Understanding | YES | **NO** — prompt template bug |
| Agent 2: Schema Retrieval (ChromaDB RAG) | YES | PARTIAL — empty DB |
| Agent 3: SQL Generation (3 candidates) | YES | PARTIAL — no schema context |
| Agent 4: Validation (3-dimensional) | YES | YES |
| Agent 5: Security Gate | YES | YES (with UNION false positive) |
| Agent 6: Optimization | YES | YES |
| Agent 7: Execution (row-limited) | YES | PARTIAL — tables missing |
| Agent 8: Explanation | YES | YES |
| Validation retry loop | YES | YES — confirmed via E2E |
| Security before Execution guard | YES | YES |
| Multi-candidate SQL selection | YES | YES |
| ChromaDB schema RAG | YES | PARTIAL — 0 schemas indexed |
| No mock/hardcoded SQL | YES (clean) | YES |
| All 8 agents wired and invoked | YES | YES |

---

## 13. Bugs Found

### BUG-001 — CRITICAL: Empty Database Files

- **Severity:** CRITICAL
- **Files:** `data/sample.db`, `backend/data/sample.db`
- **Reproduction:** `os.path.getsize('backend/data/sample.db')` → 0
- **Expected:** Database with tables and sample data
- **Actual:** `SELECT name FROM sqlite_master WHERE type='table'` returns `[]`
- **Root Cause:** No seed/migration script. Empty `.db` files committed to repo.
- **Impact:** All SQL execution fails; ChromaDB has 0 indexed schemas; LLM has no schema context

---

### BUG-002 — CRITICAL: Intent Agent Prompt Template Variable Escaping

- **Severity:** CRITICAL
- **File:** `backend/agents/intent_agent.py` — `INTENT_UNDERSTANDING_PROMPT`
- **Reproduction:** Send any query — 100% failure rate
- **Error:** `Intent understanding failed: Input to ChatPromptTemplate is missing variables {"column"}. Expected: ['"column"', 'question'] Received: ['question']`
- **Root Cause:** JSON examples in the prompt contain `{"column": "col_name"}`. LangChain's `ChatPromptTemplate.from_template()` interprets `{"column"}` as a template variable. Must escape as `{{` and `}}`.
- **Fix:** In `INTENT_UNDERSTANDING_PROMPT`, replace all `{...}` in JSON examples with `{{...}}`

---

### BUG-003 — HIGH: UNION ALL Injection False Positive

- **Severity:** HIGH
- **File:** `backend/agents/security_agent.py` — `INJECTION_PATTERNS`
- **Reproduction:** T01 — LLM generates `UNION ALL SELECT` for table row count aggregation
- **Expected:** Legitimate `UNION ALL SELECT` allowed
- **Actual:** `UNION\s+(ALL\s+)?SELECT` regex matches ALL UNION queries including legitimate ones
- **Fix:** Use `;\s*UNION\s+(ALL\s+)?SELECT` to only catch stacked queries

---

### BUG-004 — HIGH: Wrong SQL Dialect for SQLite — `DATE_TRUNC`

- **Severity:** HIGH
- **File:** `backend/agents/sql_generation_agent.py` — prompt instructs SQLite but LLM uses PostgreSQL
- **Reproduction:** T06 — "Show me total sales by month"
- **Expected:** `strftime('%Y-%m', sale_date)` (SQLite)
- **Actual:** `DATE_TRUNC('month', sale_date)` (PostgreSQL only)
- **Fix:** Add post-generation dialect validation; replace `DATE_TRUNC` with `strftime` for SQLite

---

### BUG-005 — MEDIUM: Schema Retrieval Returns Nothing (consequence of BUG-001)

- **Severity:** MEDIUM
- **File:** `backend/agents/schema_agent.py`
- **Cause:** ChromaDB indexed 0 tables at startup; returns 0 results for all queries
- **Evidence:** All processing logs: "Retrieved 0 relevant tables"

---

### BUG-006 — MEDIUM: Validation Schema Soft-Pass When Schema Empty

- **Severity:** MEDIUM
- **File:** `backend/agents/validation_agent.py`
- **Root Cause:** `if not table_schemas: return True, []` — intentional cold-start behavior
- **Impact:** SQL referencing nonexistent tables silently passes schema validation
- **Fix:** Log explicit warning when soft-pass occurs

---

### BUG-007 — MEDIUM: Non-Standard Model Names in .env

- **Severity:** MEDIUM
- **File:** `.env`
- **Expected:** `llama-3.1-70b-versatile` (per .env.example and README)
- **Actual:** `openai/gpt-oss-120b` — undocumented/unofficial Groq model name
- **Risk:** Model IDs may not remain stable

---

### BUG-008 — LOW: Deprecated FastAPI/Python/Pydantic APIs

- **Severity:** LOW
- **Files:** `backend/api/main.py`, `backend/agents/security_agent.py`, `backend/core/config.py`, `backend/models/schemas.py`
- **Issues:**
  - `@app.on_event("startup")` → use `lifespan`
  - `datetime.datetime.utcnow()` → use `datetime.now(datetime.UTC)`
  - Pydantic `class Config` → use `model_config = ConfigDict(...)`
- **Evidence:** 39 warnings in pytest

---

### BUG-009 — LOW: OpenAI Package v3 Installed (Should be v1+)

- **Severity:** LOW
- **Actual:** `openai==3.3.1` installed; requirements.txt specifies `>=1.3.0`
- **Impact:** No runtime impact (only Groq is used); risk if OpenAI integration activated

---

## 14. Configuration Issues

| Variable | Expected | Actual | Severity |
|----------|----------|--------|----------|
| `DATABASE_URL` | Populated SQLite DB | 0-byte empty file | CRITICAL |
| `OPENAI_API_KEY` | Valid key or absent | Empty string | HIGH |
| `FALLBACK_LLM_MODEL` | `llama-3.1-70b-versatile` | `openai/gpt-oss-120b` | MEDIUM |
| `EXPLANATION_LLM_MODEL` | `llama-3.1-8b-instant` | `openai/gpt-oss-20b` | MEDIUM |
| `CHROMA_PERSIST_DIR` | `./data/chroma_db` (README) | `./backend/data/chroma_db` (.env) | LOW |

---

## 15. Recommended Fixes (Prioritized)

### CRITICAL — Must Fix for Any Data to Return

**FIX-1: Create and populate `backend/data/sample.db`**

Create `create_sample_db.py` in repo root:
```python
import sqlite3
conn = sqlite3.connect('backend/data/sample.db')
c = conn.cursor()
c.executescript("""
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL, email TEXT,
    country TEXT, total_spent REAL DEFAULT 0
);
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    order_date TEXT, total_amount REAL
);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL, price REAL
);
CREATE TABLE order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    product_id INTEGER REFERENCES products(product_id),
    quantity INTEGER, unit_price REAL
);
CREATE TABLE transactions (
    transaction_id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    amount REAL, transaction_date TEXT
);
""")
# Insert 20+ rows of sample data into each table...
conn.commit()
conn.close()
```

**FIX-2: Fix Intent Agent prompt template escaping** (`backend/agents/intent_agent.py`)

```python
# BEFORE (broken — LangChain treats {"column"} as a template var):
"conditions": [{"column": "country", "operator": "=", "value": "India"}]

# AFTER (fixed):
"conditions": [{{"column": "country", "operator": "=", "value": "India"}}]
```
All `{` and `}` in `INTENT_UNDERSTANDING_PROMPT` that are **not** template variable placeholders must be doubled.

### HIGH — Fix for Full Correctness

**FIX-3: Fix UNION ALL false positive** (`backend/agents/security_agent.py`)
```python
# Change:
re.compile(r"UNION\s+(ALL\s+)?SELECT", re.IGNORECASE),
# To (only match stacked/chained queries):
re.compile(r";\s*UNION\s+(ALL\s+)?SELECT", re.IGNORECASE),
```

**FIX-4: Validate SQLite dialect functions** after SQL generation — replace `DATE_TRUNC` with `strftime` when database URL contains `sqlite`.

### MEDIUM

- **FIX-5:** Log explicit warning in validation_agent when schema soft-pass occurs on empty schema
- **FIX-6:** Update `.env` model names to `llama-3.1-70b-versatile` / `llama-3.1-8b-instant`
- **FIX-7:** Add "Database Setup" section to README.md

### LOW

- **FIX-8:** Replace deprecated FastAPI `on_event`, `datetime.utcnow()`, Pydantic `class Config`
- **FIX-9:** Consolidate the two SQLite database paths to one

---

## 16. Final Verdict

### What Works

- Application starts cleanly and serves requests
- All 88 unit tests pass (100%)
- LangGraph 8-agent orchestration compiles, routes, handles errors
- **Retry loop confirmed working** — validation failure routes back to SQL regeneration
- **Security correctly blocks DELETE, UPDATE, DDL** for 'user' role
- Execution agent double-checks `security_passed` before touching DB
- SQL Generation produces syntactically valid, semantically reasonable SQL
- Validation evaluates 3 candidates and selects best by score
- Optimization applies rule-based + LLM optimizations
- **Explanation agent gracefully degrades** — generates explanations even on execution failure
- ChromaDB initializes correctly; embedding model loads (384-dim)
- FastAPI/Swagger UI loads correctly

### What Partially Works

- SQL Generation — valid SQL but wrong table names (no schema context)
- Schema Retrieval — runs but returns 0 results (empty DB)
- Full pipeline — runs to completion but always fails at execution
- Security injection detection — correct for most patterns; UNION false positive

### What Is Broken

- **Intent Agent (Agent 1)** — fails on **EVERY** query (prompt template escaping bug)
- **Database** — both SQLite files are 0 bytes; no tables
- **End-to-end query execution** — 0 out of 10 SELECT queries returned actual data
- **Schema RAG** — 0 tables indexed in ChromaDB; LLM has no schema context

### Minimum Fix to Make System Functional

| Priority | Action | Impact |
|----------|--------|--------|
| 1 | Populate `backend/data/sample.db` with sample data | Enables SQL execution; ChromaDB indexes schemas |
| 2 | Fix `{{`/`}}` escaping in `INTENT_UNDERSTANDING_PROMPT` | Intent parsing works; schema context flows to LLM |
| 3 | Fix UNION ALL false positive in security_agent.py | Legitimate aggregation queries not blocked |

**With steps 1 and 2 applied, the system should demonstrate the full 8-agent pipeline correctly for most SELECT queries.**

---

## Appendix: Startup Import Test Results

```
=== PHASE 1: Config ===
[OK] Config imported
  GROQ_API_KEY set: True / use_groq: True
  database_url: sqlite:///./backend/data/sample.db
  fallback_llm_model: openai/gpt-oss-120b
  explanation_llm_model: openai/gpt-oss-20b
  embedding_model: sentence-transformers/all-MiniLM-L6-v2

=== PHASE 2: Agent Imports ===
[OK] intent_agent (IntentUnderstandingAgent)
[OK] schema_agent (SchemaRetrievalAgent)
[OK] sql_generation_agent (SQLGenerationAgent)
[OK] validation_agent (SQLValidationAgent)
[OK] security_agent (SecurityAgent)
[OK] optimization_agent (QueryOptimizationAgent)
[OK] execution_agent (SQLExecutionAgent)
[OK] explanation_agent (ExplanationAgent)
[OK] orchestrator (NL2SQLOrchestrator)

=== PHASE 3: FastAPI App ===
[OK] FastAPI app imported

=== PHASE 4: Orchestrator Instantiation ===
[OK] Orchestrator instantiated

=== PHASE 5: Database ===
[OK] DB connected. Tables: []
  WARNING: Database is EMPTY - no tables found!

=== PHASE 6: ChromaDB ===
[OK] ChromaDB initialized, collection: test_qa

=== PHASE 7: Embedding Model ===
[OK] Embedding model loaded. Vector dim: 384
```
