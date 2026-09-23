"""
Agent 8: Explanation Generation

Generates human-readable explanations of the SQL query and its results.
Uses LLM with a structured prompt to produce:
- Plain-English SQL explanation
- Result summary contextualised to the original question
- Key insights from the data

8-agent pipeline position:
1. Intent -> 2. Schema -> 3. SQL Generation -> 4. Validation ->
5. Security -> 6. Optimization -> 7. Execution -> 8. Explanation
"""

from typing import Any, Dict, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.core.config import settings
from backend.agents.state import AgentState, add_to_processing_log


EXPLANATION_PROMPT = """
You are an Explanation Agent for a Natural Language to SQL system.
Your task is to explain the SQL query and its results in plain English.

INPUTS:
- Original Question: {question}
- Generated SQL: {sql}
- Query Results Summary: {results_summary}
- Result Columns: {columns}
- Row Count: {row_count}

PROVIDE:
1. **SQL Explanation**: What the SQL query does in simple terms (non-technical language)
2. **Result Summary**: What the results mean in the context of the original question
3. **Key Insights**: Interesting patterns or insights from the data (2-4 bullet points)

GUIDELINES:
- Use non-technical language where possible
- Relate the explanation back to the original question
- Do not just repeat the data — provide context and meaning
- If results are empty, explain why that might be the case

OUTPUT FORMAT (JSON):
{{
    "sql_explanation": "This query retrieves...",
    "result_summary": "The results show that...",
    "insights": ["Insight 1", "Insight 2"]
}}

Generate the explanation now:"""


class ExplanationAgent:
    """
    Agent 8: Explanation Generation

    Generates human-readable explanations of the SQL query and results.
    Falls back gracefully to a simple template-based explanation if LLM is unavailable.
    """

    def __init__(self) -> None:
        """Initialize the Explanation Agent."""
        self.prompt_template = ChatPromptTemplate.from_template(EXPLANATION_PROMPT)

        if settings.use_groq:
            from langchain_groq import ChatGroq
            self.llm = ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.explanation_llm_model,
                temperature=0.3,
                max_tokens=1000
            )
        elif settings.use_openai:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                api_key=settings.openai_api_key,
                model=settings.primary_llm_model,
                temperature=0.3,
                max_tokens=1000
            )
        else:
            self.llm = None

        self.json_parser = JsonOutputParser()

    def _summarize_results(
        self,
        rows: List[Any],
        columns: List[str]
    ) -> str:
        """Create a brief text summary of query results for the LLM prompt."""
        if not rows:
            return "No results returned by the query."

        row_count = len(rows)
        sample_row = rows[0] if rows else []
        summary = f"Returned {row_count} row(s) with columns: {', '.join(columns)}. "
        if sample_row:
            sample = dict(zip(columns, sample_row)) if columns else sample_row
            summary += f"Sample first row: {sample}"

        return summary

    def invoke(self, state: AgentState) -> AgentState:
        """
        Generate a plain-English explanation for the query and its results.

        Args:
            state: Current agent state with execution results populated

        Returns:
            Updated agent state with sql_explanation, result_summary, and insights
        """
        state["current_agent"] = "explanation"

        if not state.get("include_explanation", True):
            add_to_processing_log(state, "Agent 8 (Explanation): Skipped per request")
            return state

        sql = state.get("optimized_sql") or state.get("selected_sql")

        if not sql:
            add_to_processing_log(state, "Agent 8 (Explanation): No SQL to explain")
            return state

        rows: List[Any] = state.get("query_results") or []
        columns: List[str] = state.get("result_columns") or []
        results_summary = self._summarize_results(rows, columns)

        if not self.llm:
            # Fallback: template-based explanation (no LLM required)
            state["sql_explanation"] = (
                f"The following SQL was executed: {sql[:300]}"
                + ("..." if len(sql) > 300 else "")
            )
            state["result_summary"] = results_summary
            state["insights"] = []
            add_to_processing_log(
                state, "Agent 8 (Explanation): Generated template-based explanation (no LLM)"
            )
            return state

        try:
            chain = self.prompt_template | self.llm | self.json_parser

            result = chain.invoke({
                "question": state["question"],
                "sql": sql,
                "results_summary": results_summary,
                "columns": ", ".join(columns) if columns else "none",
                "row_count": len(rows)
            })

            state["sql_explanation"] = result.get("sql_explanation", "")
            state["result_summary"] = result.get("result_summary", results_summary)
            state["insights"] = result.get("insights", [])

            add_to_processing_log(state, "Agent 8 (Explanation): Explanation generated")

        except Exception as e:
            # Fallback on LLM failure — do not crash the pipeline
            error_msg = f"Explanation generation failed: {str(e)}"
            add_to_processing_log(state, f"WARNING: {error_msg} — using fallback")
            state["sql_explanation"] = (
                f"SQL executed: {sql[:300]}" + ("..." if len(sql) > 300 else "")
            )
            state["result_summary"] = results_summary
            state["insights"] = []

        return state


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

_explanation_agent_instance: Optional[ExplanationAgent] = None


def get_explanation_agent() -> ExplanationAgent:
    """Get or create the Explanation Agent singleton."""
    global _explanation_agent_instance
    if _explanation_agent_instance is None:
        _explanation_agent_instance = ExplanationAgent()
    return _explanation_agent_instance
