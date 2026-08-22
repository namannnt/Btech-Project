"""
Agent 3: SQL Generation

This agent generates SQL queries from the parsed intent and retrieved schema.
Key features:
- Generates multiple candidate SQL queries (not just one)
- Uses gpt-4o-mini for high-quality SQL generation (accuracy-critical)
- Incorporates schema information with foreign key relationships
- Supports different SQL dialects (PostgreSQL, MySQL, SQLite)

Based on best practices from DAIL-SQL and other SOTA approaches.
"""

import json
from typing import Dict, Any, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.core.config import settings
from backend.agents.state import AgentState, add_to_processing_log


# Prompt template for SQL generation
SQL_GENERATION_PROMPT = """
You are an expert SQL Generation Agent for a Natural Language to SQL system.
Your task is to generate accurate SQL queries based on the user's question, parsed intent, and database schema.

INPUTS:
- Question: {question}
- Intent: {intent}
- Relevant Tables: {relevant_tables}
- Table Schemas: {table_schemas}
- Foreign Keys: {foreign_keys}
- SQL Dialect: {sql_dialect}

GUIDELINES:
1. **Accuracy First**: Generate syntactically correct SQL that answers the question precisely
2. **Use Schema**: Only use tables and columns that exist in the provided schema
3. **JOIN Correctly**: Use foreign key relationships to construct proper JOINs
4. **Handle Aggregations**: Properly use GROUP BY with aggregate functions (COUNT, SUM, AVG, etc.)
5. **Optimize Implicitly**: Avoid SELECT *, specify only needed columns
6. **Dialect Compliance**: Follow {sql_dialect} syntax rules

GENERATE 3 CANDIDATES:
Create 3 different valid SQL queries that could answer the question. They can vary in:
- Different JOIN strategies
- Different WHERE clause formulations
- Different subquery vs JOIN approaches

For each candidate, provide:
- sql: The SQL query string
- confidence: Your confidence score (0.0-1.0)
- explanation: Brief explanation of the approach

OUTPUT FORMAT (JSON):
{{
    "candidates": [
        {{
            "sql": "SELECT ...",
            "confidence": 0.95,
            "explanation": "Uses INNER JOIN on customer_id..."
        }},
        ...
    ],
    "selected_index": 0,
    "reasoning": "Why the selected candidate is best"
}}

IMPORTANT:
- Return ONLY valid JSON, no markdown or extra text
- Ensure all table/column names match the schema exactly
- Handle NULL values appropriately
- Use parameterized query patterns where applicable (show as :param)

Generate the candidates now:"""


class SQLGenerationAgent:
    """
    Agent 3: SQL Generation
    
    Generates multiple candidate SQL queries using LLM with structured prompting.
    Multiple candidates allow downstream validation to select the best one.
    """
    
    def __init__(self):
        """Initialize the SQL Generation Agent."""
        self.prompt_template = ChatPromptTemplate.from_template(
            SQL_GENERATION_PROMPT
        )
        
        # Use OpenAI gpt-4o-mini for SQL generation (accuracy-critical)
        if settings.use_openai:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.primary_llm_model,
                temperature=0.2,  # Slightly higher for diversity in candidates
                max_tokens=2000
            )
        elif settings.use_groq:
            from langchain_groq import ChatGroq
            self.llm = ChatGroq(
                model=settings.fallback_llm_model,
                temperature=0.2,
                max_tokens=2000
            )
        else:
            self.llm = None
        
        self.json_parser = JsonOutputParser()
    
    def _format_schema_context(self, state: AgentState) -> str:
        """Format schema information into a readable context string."""
        context_parts = []
        
        # Add table schemas
        for table_name, schema in state.get("table_schemas", {}).items():
            columns = ", ".join(
                f"{col['name']} ({col['type']})" 
                for col in schema.get("columns", [])
            )
            context_parts.append(f"Table '{table_name}': {columns}")
        
        return "\n".join(context_parts) if context_parts else "No schema available"
    
    def _format_foreign_keys(self, fks: List[Dict[str, str]]) -> str:
        """Format foreign key relationships."""
        if not fks:
            return "No foreign key relationships"
        
        fk_strings = []
        for fk in fks:
            fk_strings.append(
                f"{fk['table']}.{fk['column']} → {fk['referenced_table']}.{fk['referenced_column']}"
            )
        
        return "\n".join(fk_strings)
    
    def invoke(self, state: AgentState) -> AgentState:
        """
        Generate SQL candidates from intent and schema.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated agent state with generated SQL candidates
        """
        state["current_agent"] = "sql_generation"
        
        if not self.llm:
            error_msg = "No LLM configured for SQL generation."
            state["error_message"] = error_msg
            state["workflow_status"] = "failed"
            return state
        
        try:
            # Prepare context
            schema_context = self._format_schema_context(state)
            fk_context = self._format_foreign_keys(state.get("foreign_keys", []))
            
            # Determine SQL dialect based on database type
            db_url = settings.database_url
            if "postgresql" in db_url:
                sql_dialect = "PostgreSQL"
            elif "mysql" in db_url:
                sql_dialect = "MySQL"
            else:
                sql_dialect = "SQLite"
            
            # Create the chain
            chain = self.prompt_template | self.llm | self.json_parser
            
            # Invoke the chain
            result = chain.invoke({
                "question": state["question"],
                "intent": json.dumps(state.get("intent", {}), indent=2),
                "relevant_tables": ", ".join(state.get("relevant_tables", [])),
                "table_schemas": schema_context,
                "foreign_keys": fk_context,
                "sql_dialect": sql_dialect
            })
            
            # Update state with results
            candidates = result.get("candidates", [])
            state["sql_candidates"] = candidates
            state["generation_metadata"] = {
                "num_candidates": len(candidates),
                "dialect": sql_dialect,
                "selected_index": result.get("selected_index", 0)
            }
            
            # Select the best candidate
            if candidates:
                selected_idx = result.get("selected_index", 0)
                if 0 <= selected_idx < len(candidates):
                    state["selected_sql"] = candidates[selected_idx]["sql"]
                else:
                    # Fallback to highest confidence
                    best_candidate = max(candidates, key=lambda c: c.get("confidence", 0))
                    state["selected_sql"] = best_candidate["sql"]
            
            # Log the processing
            add_to_processing_log(
                state,
                f"Generated {len(candidates)} SQL candidates. "
                f"Selected: {state['selected_sql'][:100]}..." if state["selected_sql"]
                else "No SQL generated"
            )
            
        except Exception as e:
            error_msg = f"SQL generation failed: {str(e)}"
            state["error_message"] = error_msg
            state["sql_candidates"] = []
            state["selected_sql"] = None
            add_to_processing_log(state, f"ERROR: {error_msg}")
        
        return state
    
    def retry_generation(self, state: AgentState, errors: List[str]) -> AgentState:
        """
        Retry SQL generation with error feedback.
        
        This implements the validation loop: when validation fails,
        we call this method to regenerate SQL with error context.
        
        Args:
            state: Current state
            errors: List of validation errors to address
            
        Returns:
            Updated state with new candidates
        """
        state["current_agent"] = "sql_generation_retry"
        
        if not self.llm:
            return state
        
        # Enhanced prompt for retry with error feedback
        retry_prompt = """
Previous SQL generation failed validation. Please regenerate SQL addressing these issues:

ERRORS TO FIX:
{errors}

PREVIOUS ATTEMPT: {previous_sql}

ORIGINAL QUESTION: {question}
SCHEMA: {table_schemas}

Generate improved SQL candidates that fix the above errors.
Return in the same JSON format as before."""
        
        try:
            chain = ChatPromptTemplate.from_template(retry_prompt) | self.llm | self.json_parser
            
            result = chain.invoke({
                "errors": "\n".join(errors),
                "previous_sql": state.get("selected_sql", "None"),
                "question": state["question"],
                "table_schemas": self._format_schema_context(state)
            })
            
            # Update retry count
            state["retry_count"] = state.get("retry_count", 0) + 1
            
            # Update candidates
            candidates = result.get("candidates", [])
            state["sql_candidates"] = candidates
            
            if candidates:
                state["selected_sql"] = candidates[0]["sql"]
            
            add_to_processing_log(
                state,
                f"Retry #{state['retry_count']}: Generated {len(candidates)} new candidates"
            )
            
        except Exception as e:
            add_to_processing_log(state, f"Retry failed: {str(e)}")
        
        return state


# Singleton instance
_sql_generation_agent_instance = None


def get_sql_generation_agent() -> SQLGenerationAgent:
    """Get or create the SQL Generation Agent singleton."""
    global _sql_generation_agent_instance
    if _sql_generation_agent_instance is None:
        _sql_generation_agent_instance = SQLGenerationAgent()
    return _sql_generation_agent_instance


if __name__ == "__main__":
    # Test the agent (requires LLM API keys)
    print("Testing SQL Generation Agent\n" + "=" * 50)
    
    from backend.agents.state import initialize_state
    
    # Create a mock state
    test_state = initialize_state(
        question="Show me all customers who placed orders in 2023",
        database_id="test_db"
    )
    
    # Mock intent and schema
    test_state["intent"] = {
        "entities": ["customers", "orders"],
        "conditions": [{"column": "order_date", "operator": ">=", "value": "2023-01-01"}],
        "operations": ["SELECT", "JOIN", "WHERE"],
        "question_type": "factual"
    }
    
    test_state["relevant_tables"] = ["customers", "orders"]
    test_state["table_schemas"] = {
        "customers": {
            "columns": [
                {"name": "customer_id", "type": "INTEGER"},
                {"name": "name", "type": "TEXT"},
                {"name": "email", "type": "TEXT"}
            ]
        },
        "orders": {
            "columns": [
                {"name": "order_id", "type": "INTEGER"},
                {"name": "customer_id", "type": "INTEGER"},
                {"name": "order_date", "type": "DATE"},
                {"name": "total", "type": "DECIMAL"}
            ]
        }
    }
    test_state["foreign_keys"] = [{
        "table": "orders",
        "column": "customer_id",
        "referenced_table": "customers",
        "referenced_column": "customer_id"
    }]
    
    print(f"\nQuestion: {test_state['question']}")
    print("-" * 50)
    
    agent = get_sql_generation_agent()
    
    if agent.llm:
        result_state = agent.invoke(test_state)
        print("\nGenerated SQL Candidates:")
        for i, candidate in enumerate(result_state["sql_candidates"], 1):
            print(f"\n{i}. Confidence: {candidate.get('confidence', 0):.2f}")
            print(f"   SQL: {candidate.get('sql', 'N/A')}")
            print(f"   Explanation: {candidate.get('explanation', 'N/A')}")
    else:
        print("\n⚠ No LLM configured. Set OPENAI_API_KEY or GROQ_API_KEY to test.")
