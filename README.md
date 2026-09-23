# NL2SQL Multi-Agent System

A **Natural Language to SQL** conversion system using an **8-agent pipeline** orchestrated by **LangGraph**. Each agent has a single, clearly defined responsibility. The system converts plain-English questions into validated, security-checked, optimized, and executed SQL queries, then generates a human-readable explanation.

---

## Architecture

`
User Question
     ↓
Agent 1: Intent Understanding      ← parse entities, operations, question type
     ↓
Agent 2: Schema Retrieval (RAG)    ← ChromaDB semantic search for relevant tables
     ↓
Agent 3: SQL Generation            ← 3 LLM-generated candidates
     ↓
Agent 4: Validation                ← syntax + schema + semantic (hard check)
     ↓ (if fail → retry → Agent 3, up to max_retries)
Agent 5: Security Check            ← RBAC + forbidden statements + injection detection
     ↓ (if fail → pipeline stops, execution prevented)
Agent 6: Optimization              ← rule-based + LLM SQL optimization
     ↓
Agent 7: SQL Execution             ← safe execution with timeout & row limits
     ↓
Agent 8: Explanation               ← plain-English answer + insights
     ↓
Final Response (JSON via FastAPI)
`

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| 8 separate agent modules | Single responsibility — easier to test, debug, replace |
| Multi-candidate SQL generation | 3 candidates → best valid one selected by validation |
| Validation retry loop | Validation errors fed back to SQL Generation (not just fail fast) |
| Security BEFORE execution | Prevents any unsafe SQL from touching the database |
| semantic_valid as hard check | Prevents hallucinated SQL that ignores the question's intent |
| ChromaDB schema RAG | Only relevant schema sent to LLM — lower cost, higher accuracy |

---

## Validation Formula

`python
is_valid = syntax_valid AND schema_valid AND semantic_valid
`

All three dimensions are required. semantic_valid is a **hard check** that fails if the SQL is missing operations explicitly required by the parsed intent (e.g., COUNT mentioned in intent but absent from SQL).

---

## Security Model

| Role | SELECT | INSERT | UPDATE | DELETE | DDL |
|------|--------|--------|--------|--------|-----|
| guest | ✓ (restricted tables) | ✗ | ✗ | ✗ | ✗ |
| user | ✓ | ✗ | ✗ | ✗ | ✗ |
| analyst | ✓ | ✗ | ✗ | ✗ | ✗ |
| admin | ✓ | ✓ | ✓ | ✓ | ✗ |

> **DDL (DROP, ALTER, TRUNCATE, GRANT, REVOKE, CREATE) is blocked for ALL roles.**

---

## Project Structure

`
Btech-Project/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── intent_agent.py         # Agent 1
│   │   ├── schema_agent.py         # Agent 2
│   │   ├── sql_generation_agent.py # Agent 3
│   │   ├── validation_agent.py     # Agent 4
│   │   ├── security_agent.py       # Agent 5 (NEW)
│   │   ├── optimization_agent.py   # Agent 6 (split from other_agents.py)
│   │   ├── execution_agent.py      # Agent 7 (split from other_agents.py)
│   │   ├── explanation_agent.py    # Agent 8 (split from other_agents.py)
│   │   ├── orchestrator.py         # LangGraph 8-node graph
│   │   └── state.py                # AgentState TypedDict (all 8 agents)
│   ├── api/
│   │   └── main.py                 # FastAPI — single canonical endpoint
│   ├── core/
│   │   └── config.py               # Pydantic settings
│   ├── models/
│   │   └── schemas.py              # Pydantic request/response models
│   ├── services/
│   │   ├── database_service.py     # DB connection + safe execution
│   │   └── schema_service.py       # ChromaDB indexing + retrieval
│   └── utils/
│       ├── logging_utils.py        # Structured logging
│       └── sql_utils.py            # Dialect detection, SQL helpers
├── data/
│   └── sample.db                   # Canonical SQLite database
├── docs/
│   ├── architecture.md             # Mermaid diagram + state transitions
│   └── agent_contracts.md          # Input/output contracts per agent
├── frontend/
│   └── app.py                      # Streamlit chat UI (8-agent aware)
├── tests/
│   ├── test_intent_agent.py
│   ├── test_schema_agent.py
│   ├── test_sql_generation_agent.py
│   ├── test_validation_agent.py
│   ├── test_security_agent.py
│   ├── test_optimization_agent.py
│   ├── test_execution_agent.py
│   ├── test_explanation_agent.py
│   ├── test_orchestrator.py
│   └── test_api.py
├── .env.example
├── .gitignore
├── main.py                         # Convenience entry point
├── pyproject.toml
├── requirements.txt
└── README.md
`

---

## Quick Start

### 1. Clone & Setup

`ash
git clone https://github.com/namannnt/Btech-Project.git
cd Btech-Project
cp .env.example .env
# Edit .env — add your API keys
`

### 2. Install Dependencies

`ash
pip install -r requirements.txt
`

### 3. Configure Environment

Edit .env:
`env
OPENAI_API_KEY=your_key_here
GROQ_API_KEY=your_key_here          # Optional (used for intent + explanation)
SQLITE_URL=sqlite:///./data/sample.db
`

### 4. Run the Backend

`ash
# Option A: convenience script
python main.py

# Option B: direct uvicorn
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
`

### 5. Run the Frontend

`ash
streamlit run frontend/app.py
`

### 6. Test the API

`ash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How many customers are there?",
    "user_role": "user",
    "include_explanation": true
  }'
`

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | / | API info |
| GET | /api/v1/health | Health check (reports LLM, DB, vector store status) |
| **POST** | **/api/v1/query** | **Main endpoint — NL to SQL + execution** |
| GET | /api/v1/databases | List configured databases |
| POST | /api/v1/schema/index | Trigger schema indexing into ChromaDB |
| GET | /api/v1/schema/{id} | Get introspected schema |
| GET | /docs | Swagger UI |

### Request Schema

`json
{
  "question": "How many customers placed orders in 2023?",
  "database_id": null,
  "user_role": "user",
  "include_explanation": true
}
`

### Response Schema

`json
{
  "success": true,
  "question": "...",
  "intent": { "entities": [...], "operations": [...], "confidence": 0.95 },
  "retrieved_schema": { "relevant_tables": [...] },
  "generated_sql": "SELECT COUNT(*) FROM orders WHERE ...",
  "optimized_sql": "SELECT COUNT(*) FROM orders WHERE ...",
  "validation": { "is_valid": true, "syntax_valid": true, "schema_valid": true, "semantic_valid": true },
  "security": { "passed": true, "role": "user", "decision": "APPROVED", "violations": [] },
  "execution_result": { "success": true, "rows": [[42]], "columns": ["count"], "row_count": 1 },
  "explanation": { "sql_explanation": "...", "result_summary": "...", "insights": [...] },
  "retry_count": 0,
  "processing_log": [...],
  "processing_time_ms": 1234.5
}
`

---

## Environment Variables

All variables documented in .env.example:

| Variable | Description | Default |
|----------|-------------|---------|
| OPENAI_API_KEY | OpenAI API key | |
| GROQ_API_KEY | Groq API key (optional) | |
| SQLITE_URL | SQLite database path | sqlite:///./data/sample.db |
| POSTGRES_URL | PostgreSQL URL (overrides SQLite) | |
| MYSQL_URL | MySQL URL (overrides SQLite) | |
| CHROMA_PERSIST_DIR | ChromaDB persistence directory | ./data/chroma_db |
| EMBEDDING_MODEL | HuggingFace embedding model | sentence-transformers/all-MiniLM-L6-v2 |
| PRIMARY_LLM_MODEL | OpenAI model for SQL generation | gpt-4o-mini |
| FALLBACK_LLM_MODEL | Groq model for SQL generation | llama-3.1-70b-versatile |
| EXPLANATION_LLM_MODEL | Groq model for explanations | llama-3.1-8b-instant |
| MAX_QUERY_TIMEOUT | SQL execution timeout (seconds) | 30 |
| MAX_ROWS_RETURNED | Hard row-limit for results | 1000 |
| DEFAULT_ROLE | Default user role | user |
| SECRET_KEY | Application secret key | |
| DEBUG | Enable debug/reload mode | 	rue |
| LOG_LEVEL | Logging level | INFO |

---

## Running Tests

`ash
# Full test suite
python -m pytest tests/ -v

# Specific agent
python -m pytest tests/test_security_agent.py -v
python -m pytest tests/test_validation_agent.py -v

# No external dependencies (validation + security run without LLM)
python -m pytest tests/test_validation_agent.py tests/test_security_agent.py tests/test_execution_agent.py tests/test_optimization_agent.py tests/test_orchestrator.py -v
`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM (primary) | OpenAI gpt-4o-mini |
| LLM (fallback) | Groq llama-3.1-70b-versatile |
| Schema RAG | ChromaDB + sentence-transformers |
| SQL Validation | [sqlglot](https://github.com/tobymao/sqlglot) |
| Database | SQLAlchemy (SQLite / PostgreSQL / MySQL) |
| API | FastAPI + Uvicorn |
| Frontend | Streamlit |
| Testing | pytest |

---

## Academic References

- **DAIL-SQL** — Prompt engineering for NL2SQL
- **MAC-SQL** — Multi-agent collaboration for SQL generation
- **Graphix-T5** — Schema linking with graph relationships
- **NL2SQL360** — Evaluation framework (EX / EM / VES metrics)
- **AST-Ranking** — Schema pruning via abstract syntax trees

---

## License

MIT License

## Authors

B.Tech Final Year Project Team
