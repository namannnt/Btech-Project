# NL2SQL Multi-Agent System

## 🎯 Project Overview

A sophisticated **Natural Language to SQL** conversion system using a **multi-agent architecture** orchestrated by **LangGraph**. This system converts user questions in plain English into executable SQL queries, validates them, optimizes performance, executes against databases, and provides human-readable explanations.

## 🏗️ Architecture

```
User (Browser/Streamlit)
   ↓
FastAPI Backend
   ↓
LangGraph Orchestrator (State Machine)
   ↓
┌─────────────────────────────────────────────────────────────┐
│  Agent 1: Intent Understanding (Groq/Llama)                │
│  Agent 2: Schema Retrieval (RAG + ChromaDB)                │
│  Agent 3: SQL Generation (gpt-4o-mini)                     │
│  Agent 4: Validation (sqlglot + permissions)               │
│  Agent 5: Query Optimization                               │
│  Agent 6: SQL Execution (SQLAlchemy)                       │
│  Agent 7: Explanation (Groq/Llama)                         │
└─────────────────────────────────────────────────────────────┘
   ↓
Database (PostgreSQL/MySQL/SQLite)
```

### Key Innovation: Validation Loop

Unlike simple linear pipelines, our system implements a **validation loop**:
- If validation fails, the system automatically routes back to SQL Generation
- The generation agent receives error feedback and regenerates improved SQL
- This continues until validation passes or max retries exceeded

## 🚀 Quick Start

### 1. Clone & Setup

```bash
cd /workspace
cp .env.example .env
# Edit .env with your API keys
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API Keys

Edit `.env` file:
```env
OPENAI_API_KEY=your_key_here
GROQ_API_KEY=your_key_here  # Optional fallback
```

### 4. Run the Backend

```bash
# Option A: Direct execution
python -m backend.api.main

# Option B: Using uvicorn
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access API

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/api/v1/health

## 📁 Project Structure

```
/workspace
├── backend/
│   ├── api/              # FastAPI endpoints
│   │   └── main.py       # API server
│   ├── agents/           # Multi-agent implementation
│   │   ├── state.py      # LangGraph state definition
│   │   ├── intent_agent.py
│   │   ├── schema_agent.py
│   │   ├── sql_generation_agent.py
│   │   ├── validation_agent.py
│   │   ├── other_agents.py  # Optimization, Execution, Explanation
│   │   └── orchestrator.py    # LangGraph workflow
│   ├── core/             # Configuration
│   │   └── config.py
│   ├── models/           # Pydantic schemas
│   │   └── schemas.py
│   ├── services/         # Business logic (to be implemented)
│   └── utils/            # Utilities (to be implemented)
├── frontend/             # Streamlit/React UI (to be implemented)
├── data/                 # Sample databases & ChromaDB storage
├── sample_dbs/           # Demo database files
├── tests/                # Unit & integration tests
├── docs/                 # Documentation
├── requirements.txt      # Python dependencies
├── .env.example          # Environment template
└── README.md             # This file
```

## 🔧 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend API** | FastAPI + Uvicorn | Async REST API with auto-docs |
| **Orchestration** | LangGraph | Stateful multi-agent workflow |
| **LLM (Primary)** | OpenAI gpt-4o-mini | SQL generation & validation |
| **LLM (Fallback)** | Groq Llama 3.1 | Intent & explanation (cost-saving) |
| **Vector Store** | ChromaDB | Schema embedding & retrieval |
| **Embeddings** | sentence-transformers | Local, free embeddings |
| **SQL Parsing** | sqlglot | Syntax validation & AST parsing |
| **Database** | SQLAlchemy | Multi-DB support (Postgres/MySQL/SQLite) |
| **Frontend** | Streamlit (Phase 1) / React (Phase 2) | Chat-style UI |

## 📊 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API info |
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/query` | Process NL query → SQL + results |
| `GET` | `/api/v1/databases` | List available databases |
| `POST` | `/api/v1/schema/index` | Index schema for RAG |
| `GET` | `/api/v1/schema/{id}` | Get schema info |

### Example Query Request

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Show me all customers who placed orders in 2023",
    "database_id": "chinook",
    "user_role": "user",
    "include_explanation": true
  }'
```

## 👥 Team Work Split (4 members)

| Person | Responsibility | Files |
|--------|---------------|-------|
| **A** | Intent + Explanation Agents | `intent_agent.py`, `other_agents.py` (ExplanationAgent) |
| **B** | Schema Retrieval (RAG) | `schema_agent.py`, ChromaDB setup |
| **C** | SQL Generation + Validation | `sql_generation_agent.py`, `validation_agent.py` |
| **D** | Orchestration + Backend | `orchestrator.py`, `main.py`, wiring |

## 📅 Development Timeline

| Weeks | Phase | Deliverables |
|-------|-------|--------------|
| 1-2 | Literature Review | Paper analysis, design decisions |
| 2-3 | Requirements | Functional/NFR specs |
| 3-4 | System Design | Architecture, agent contracts |
| 5-6 | Agents 1-2 | Intent + Schema agents working |
| 6-7 | Agents 3-4 | SQL Gen + Validation with retry loop |
| 7-8 | Agents 5-7 + Wiring | Full pipeline end-to-end |
| 8-10 | Refinement | Prompt tuning, error handling |
| 10-12 | Evaluation | Spider/BIRD metrics (EX/EM/VES) |
| 13-14 | Documentation | Report, demo video |

## 🧪 Testing

```bash
# Run unit tests
pytest tests/

# Test individual agents
python -m backend.agents.intent_agent
python -m backend.agents.validation_agent
python -m backend.agents.other_agents
```

## 📝 Key Features

1. **Multi-Agent Architecture**: 7 specialized agents with clear separation of concerns
2. **Validation Loop**: Automatic retry on validation failure (not just linear pipeline)
3. **RAG-based Schema Retrieval**: Only relevant schema sent to LLM (reduces cost, improves accuracy)
4. **Multi-Database Support**: PostgreSQL, MySQL, SQLite via SQLAlchemy
5. **Role-Based Permissions**: Configurable access control by user role
6. **Query Safety**: Read-only connections, timeout limits, row limits
7. **Explainable AI**: Plain English explanations of SQL and results
8. **Evaluation Metrics**: EX (Execution Accuracy), EM (Exact Match), VES (Valid Efficiency Score)

## 🔐 Security Considerations

- API keys stored in `.env` (never committed)
- Read-only database connections for query execution
- Role-based permission checking before execution
- Query timeout and row limits prevent DoS
- SQL injection prevented by parameterized queries

## 📚 References

Key papers from literature review:
- DAIL-SQL (Prompt engineering for SQL generation)
- MAC-SQL (Multi-agent collaboration)
- Graphix-T5 (Schema linking with relationships)
- NL2SQL360 (Evaluation framework with VES metric)
- AST-Ranking (Schema pruning techniques)

## 📄 License

MIT License - see LICENSE file

## 👨‍💻 Authors

B.Tech Project Team
- [Team Member Names]

---

**For Viva/Defense:**
> "Hum LangGraph se agents ko ek stateful graph mein orchestrate kar rahe hain — jisme validation fail hone par system automatically SQL Generation agent ko wapas route karta hai. Schema retrieval RAG-based hai taaki bade schema mein bhi sirf relevant part LLM ko mile. Evaluation NL2SQL360 paper ke metrics (EX/EM/VES) se hoga."