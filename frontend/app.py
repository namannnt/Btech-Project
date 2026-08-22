import streamlit as st
import requests
import pandas as pd
import json

# Page Config
st.set_page_config(page_title="NL2SQL Multi-Agent", layout="wide")

# Custom CSS for better look
st.markdown("""
<style>
.stChatMessage { 
    border-radius: 10px; 
    padding: 10px; 
}
.code-block { 
    background-color: #f0f2f6; 
    padding: 10px; 
    border-radius: 5px; 
    font-family: monospace; 
}
</style>
""", unsafe_allow_html=True)

# Sidebar Configuration
with st.sidebar:
    st.title("⚙️ Settings")
    api_url = st.text_input("Backend API URL", value="http://localhost:8000")
    st.divider()
    st.info("💡 **Tips:**\n- Ask questions like 'Show me all employees in IT'\n- Try 'What is the average salary?'\n- System auto-validates SQL before running")

# Main Title
st.title("🤖 NL2SQL Multi-Agent System")
st.caption("Powered by LangGraph • Intent → Schema → SQL → Validate → Execute → Explain")

# Initialize Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sql" in message:
            st.code(message["sql"], language="sql")
        if "data" in message and message["data"]:
            df = pd.DataFrame(message["data"])
            st.dataframe(df, use_container_width=True)
        if "explanation" in message:
            with st.expander("🧠 Agent Explanation"):
                st.markdown(message["explanation"])

# Chat Input
if prompt := st.chat_input("Ask anything about your database..."):
    # 1. Show User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # 2. Call Backend API
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("🔄 Agents are working...\n- 🔍 Understanding Intent\n- 📂 Retrieving Schema\n- 📝 Generating SQL\n- ✅ Validating Query\n- 🚀 Executing & Explaining")
        
        try:
            response = requests.post(
                f"{api_url}/api/v1/query",
                json={"question": prompt},
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract fields - matching backend NLQueryResponse schema
                explanation_obj = data.get("explanation") or {}
                sql_query = data.get("generated_sql", "")
                exec_result = data.get("execution_result") or {}
                results = exec_result.get("rows", [])
                explanation = explanation_obj.get("sql_explanation", "")
                answer = explanation_obj.get("result_summary", "No answer generated.")
                
                # Display Response
                message_placeholder.markdown(f"**Answer:** {answer}")
                
                if sql_query:
                    st.code(sql_query, language="sql")
                
                if results:
                    df = pd.DataFrame(results)
                    st.dataframe(df, use_container_width=True)
                
                if explanation:
                    with st.expander("🧠 View Agent Explanation"):
                        st.markdown(explanation)
                
                # Save to history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sql": sql_query,
                    "data": results,
                    "explanation": explanation
                })
            else:
                error_msg = f"❌ Error {response.status_code}: {response.text}"
                message_placeholder.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                
        except requests.exceptions.ConnectionError:
            error_msg = "❌ Could not connect to Backend. Is `uvicorn` running on port 8000?"
            message_placeholder.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
        except Exception as e:
            message_placeholder.error(f"❌ Unexpected error: {str(e)}")