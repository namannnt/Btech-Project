"""
NL2SQL Multi-Agent System — Streamlit Frontend

Connects to the canonical backend API (POST /api/v1/query) and displays
the full 8-agent pipeline result:
- Natural language answer
- Generated SQL (and optimized SQL)
- Validation status (syntax / schema / semantic)
- Security status
- Execution results table
- Agent explanation & insights
- Full processing log / agent trace
"""

import streamlit as st
import requests
import pandas as pd
import json

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="NL2SQL Multi-Agent",
    page_icon="🤖",
    layout="wide"
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
.stChatMessage { border-radius: 10px; padding: 10px; }
.status-badge { padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; }
.status-pass { background-color: #d4edda; color: #155724; }
.status-fail { background-color: #f8d7da; color: #721c24; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("⚙️ Settings")
    api_url = st.text_input("Backend API URL", value="http://localhost:8000")
    user_role = st.selectbox("User Role", ["user", "analyst", "admin", "guest"], index=0)
    include_explanation = st.checkbox("Include explanation", value=True)
    show_processing_log = st.checkbox("Show agent processing log", value=False)
    
    st.divider()
    
    st.title("🗄️ Database Connection")
    db_file = st.file_uploader("Upload SQLite .db", type=["db", "sqlite"])
    
    if "db_info" not in st.session_state:
        st.session_state.db_info = None
        
    if st.button("🔌 Connect Database") and db_file:
        with st.spinner("Connecting and analyzing schema..."):
            try:
                files = {"file": (db_file.name, db_file, "application/octet-stream")}
                upload_res = requests.post(f"{api_url}/api/v1/database/upload", files=files, timeout=60)
                if upload_res.status_code == 200:
                    st.session_state.db_info = upload_res.json()
                    st.success("Successfully connected!")
                else:
                    st.error(f"Failed to connect: {upload_res.text}")
            except Exception as e:
                st.error(f"Error connecting: {e}")
                
    if st.session_state.db_info:
        db_info = st.session_state.db_info
        st.success("Status: Connected")
        st.write(f"**Database:** {db_info.get('filename')}")
        st.write(f"**Tables:** {db_info.get('table_count')}")
        for table in db_info.get("tables", []):
            st.markdown(f"- `{table}`")
        
        if st.button("Disconnect Custom DB"):
            st.session_state.db_info = None
            st.rerun()
    else:
        st.info("Status: Default (sample.db)")
    
    st.divider()
    st.info(
        "💡 **Pipeline:**\n"
        "1. Intent Understanding\n"
        "2. Schema Retrieval (RAG)\n"
        "3. SQL Generation\n"
        "4. Validation (retry loop)\n"
        "5. Security Check\n"
        "6. Optimization\n"
        "7. Execution\n"
        "8. Explanation"
    )

# ---------------------------------------------------------------------------
# Main title
# ---------------------------------------------------------------------------

st.title("🤖 NL2SQL Multi-Agent System")
st.caption(
    "Powered by LangGraph · 8 agents: "
    "Intent → Schema → SQL Gen → Validate → Security → Optimize → Execute → Explain"
)

# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sql"):
            st.code(message["sql"], language="sql")
        if message.get("data"):
            st.dataframe(pd.DataFrame(message["data"]), use_container_width=True)

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask anything about your database..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown(
            "🔄 Running 8-agent pipeline...\n"
            "1️⃣ Understanding intent  2️⃣ Retrieving schema  3️⃣ Generating SQL  "
            "4️⃣ Validating  5️⃣ Security check  6️⃣ Optimizing  7️⃣ Executing  8️⃣ Explaining"
        )

        try:
            payload = {
                "question": prompt,
                "user_role": user_role,
                "include_explanation": include_explanation,
            }
            if st.session_state.db_info:
                payload["database_id"] = st.session_state.db_info.get("database_id")

            response = requests.post(
                f"{api_url}/api/v1/query",
                json=payload,
                timeout=120
            )

            if response.status_code == 200:
                data = response.json()
                success = data.get("success", False)

                # ----------------------------------------------------------
                # Answer / result summary
                # ----------------------------------------------------------
                explanation = data.get("explanation") or {}
                answer = explanation.get("result_summary") or (
                    "Pipeline completed but no result summary generated."
                    if success else
                    f"❌ Pipeline failed: {data.get('error_message', 'Unknown error')}"
                )
                placeholder.markdown(f"**Answer:** {answer}")

                # ----------------------------------------------------------
                # SQL display
                # ----------------------------------------------------------
                optimized_sql = data.get("optimized_sql")
                generated_sql = data.get("generated_sql")
                display_sql = optimized_sql or generated_sql

                if display_sql:
                    if optimized_sql and generated_sql and optimized_sql != generated_sql:
                        sql_tab1, sql_tab2 = st.tabs(["✅ Optimized SQL", "📝 Generated SQL"])
                        with sql_tab1:
                            st.code(optimized_sql, language="sql")
                        with sql_tab2:
                            st.code(generated_sql, language="sql")
                    else:
                        st.code(display_sql, language="sql")

                # ----------------------------------------------------------
                # Validation status
                # ----------------------------------------------------------
                validation = data.get("validation") or {}
                if validation:
                    with st.expander("✅ Validation Status", expanded=False):
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Syntax", "✓" if validation.get("syntax_valid") else "✗")
                        col2.metric("Schema", "✓" if validation.get("schema_valid") else "✗")
                        col3.metric("Semantic", "✓" if validation.get("semantic_valid") else "✗")
                        if validation.get("errors"):
                            st.error("Validation errors: " + "; ".join(validation["errors"][:3]))
                        retry_count = data.get("retry_count", 0)
                        if retry_count:
                            st.info(f"SQL generation retried {retry_count} time(s)")

                # ----------------------------------------------------------
                # Security status
                # ----------------------------------------------------------
                security = data.get("security") or {}
                if security:
                    with st.expander("🔒 Security Status", expanded=False):
                        sec_pass = security.get("passed", False)
                        sec_badge = "✅ APPROVED" if sec_pass else "❌ REJECTED"
                        st.markdown(f"**Decision:** {sec_badge}")
                        st.markdown(f"**Role:** {security.get('role', 'unknown')}")
                        if security.get("violations"):
                            st.error("Violations: " + "; ".join(security["violations"][:3]))

                # ----------------------------------------------------------
                # Query results
                # ----------------------------------------------------------
                exec_result = data.get("execution_result") or {}
                rows = exec_result.get("rows", [])
                columns = exec_result.get("columns", [])

                if rows and columns:
                    st.subheader("📊 Results")
                    try:
                        df = pd.DataFrame(rows, columns=columns)
                        st.dataframe(df, use_container_width=True)
                    except Exception:
                        st.write(rows)
                    st.caption(
                        f"{exec_result.get('row_count', len(rows))} rows "
                        f"in {exec_result.get('execution_time_ms', 0):.1f}ms"
                    )
                    if exec_result.get("warning"):
                        st.warning(exec_result["warning"])
                elif not success and exec_result.get("error_message"):
                    st.error(f"Execution error: {exec_result['error_message']}")

                # ----------------------------------------------------------
                # Explanation & insights
                # ----------------------------------------------------------
                sql_explanation = explanation.get("sql_explanation", "")
                insights = explanation.get("insights", [])

                if sql_explanation or insights:
                    with st.expander("🧠 Agent Explanation", expanded=False):
                        if sql_explanation:
                            st.markdown(f"**SQL explanation:** {sql_explanation}")
                        if insights:
                            st.markdown("**Insights:**")
                            for insight in insights:
                                st.markdown(f"- {insight}")

                # ----------------------------------------------------------
                # Processing log
                # ----------------------------------------------------------
                if show_processing_log:
                    log = data.get("processing_log", [])
                    if log:
                        with st.expander("🔍 Agent Processing Log", expanded=False):
                            for entry in log:
                                st.text(entry)

                # ----------------------------------------------------------
                # Save to history
                # ----------------------------------------------------------
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sql": display_sql,
                    "data": rows if (rows and columns) else None,
                })

            else:
                error_text = f"❌ Backend error {response.status_code}: {response.text[:300]}"
                placeholder.error(error_text)
                st.session_state.messages.append({"role": "assistant", "content": error_text})

        except requests.exceptions.ConnectionError:
            msg = (
                f"❌ Cannot connect to backend at {api_url}. "
                "Is uvicorn backend.api.main:app running on port 8000?"
            )
            placeholder.error(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})

        except requests.exceptions.Timeout:
            msg = "❌ Request timed out (>120s). The pipeline is taking too long."
            placeholder.error(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})

        except Exception as e:
            placeholder.error(f"❌ Unexpected error: {e}")
