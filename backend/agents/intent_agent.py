"""
Agent 1: Intent Understanding

This agent parses the natural language question to extract:
- Entities (tables, columns mentioned)
- Conditions (filters, WHERE clauses)
- Operations (SELECT, COUNT, AVG, GROUP BY, etc.)
- Question type (factual, analytical, comparative, etc.)

Uses LLM with structured prompting (DAIL-SQL style) to parse intent.
Cost optimization: Uses Groq/Llama for this non-critical reasoning task.
"""

import json
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.core.config import settings
from backend.agents.state import AgentState, add_to_processing_log


# Prompt template for intent understanding
INTENT_UNDERSTANDING_PROMPT = """
You are an Intent Understanding Agent for a Natural Language to SQL system.
Your task is to analyze the user's question and extract structured information that will help generate the correct SQL query.

Analyze the following natural language question and extract:

1. **entities**: List of database objects mentioned (tables, columns, values)
2. **conditions**: Filter conditions with their operators (e.g., {"column": "age", "operator": ">", "value": "30"})
3. **operations**: SQL operations needed (SELECT, COUNT, SUM, AVG, GROUP BY, ORDER BY, JOIN, etc.)
4. **question_type**: Type of question (factual, analytical, comparative, aggregation, temporal, etc.)
5. **confidence**: Your confidence in this interpretation (0.0 to 1.0)

IMPORTANT GUIDELINES:
- Be precise about column and table names - use exact naming from typical database schemas
- Identify implicit conditions (e.g., "best" implies ORDER BY + LIMIT)
- Detect aggregations (COUNT, SUM, AVG, MAX, MIN)
- Identify time-based filters (last year, recent, etc.)
- Note any ambiguous terms that might need clarification

Question: {question}

Provide your response as a valid JSON object with the following structure:
{{
    "entities": ["entity1", "entity2", ...],
    "conditions": [{{"column": "col_name", "operator": "=", "value": "value"}}, ...],
    "operations": ["SELECT", "COUNT", "GROUP BY", ...],
    "question_type": "type",
    "confidence": 0.95,
    "ambiguous_terms": ["term1", "term2"],
    "reasoning": "Brief explanation of your interpretation"
}}

Response:"""


class IntentUnderstandingAgent:
    """
    Agent 1: Intent Understanding
    
    This agent uses an LLM to parse the natural language question into structured intent.
    It's the first step in the pipeline and sets context for all downstream agents.
    """
    
    def __init__(self):
        """Initialize the Intent Understanding Agent."""
        self.prompt_template = ChatPromptTemplate.from_template(
            INTENT_UNDERSTANDING_PROMPT
        )
        
        # Use Groq for cost-effective intent parsing (not accuracy-critical)
        if settings.use_groq:
            from langchain_groq import ChatGroq
            self.llm = ChatGroq(
                model=settings.fallback_llm_model,
                temperature=0.1,  # Low temperature for consistent parsing
                max_tokens=1000
            )
        elif settings.use_openai:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.primary_llm_model,
                temperature=0.1,
                max_tokens=1000
            )
        else:
            self.llm = None
        
        self.json_parser = JsonOutputParser()
    
    def invoke(self, state: AgentState) -> AgentState:
        """
        Process the natural language question and extract intent.
        
        Args:
            state: Current agent state containing the question
            
        Returns:
            Updated agent state with parsed intent
        """
        state["current_agent"] = "intent_understanding"
        
        if not self.llm:
            error_msg = "No LLM configured. Please set OPENAI_API_KEY or GROQ_API_KEY in .env file."
            state["error_message"] = error_msg
            state["workflow_status"] = "failed"
            return state
        
        try:
            # Create the chain
            chain = self.prompt_template | self.llm | self.json_parser
            
            # Invoke the chain
            result = chain.invoke({"question": state["question"]})
            
            # Update state with parsed intent
            state["intent"] = result
            state["intent_confidence"] = result.get("confidence", 0.0)
            
            # Log the processing
            add_to_processing_log(
                state, 
                f"Intent understood: {result.get('question_type', 'unknown')} question "
                f"with {len(result.get('entities', []))} entities and "
                f"{len(result.get('operations', []))} operations"
            )
            
        except Exception as e:
            error_msg = f"Intent understanding failed: {str(e)}"
            state["error_message"] = error_msg
            state["intent"] = {
                "entities": [],
                "conditions": [],
                "operations": ["SELECT"],
                "question_type": "unknown",
                "confidence": 0.0,
                "error": str(e)
            }
            state["intent_confidence"] = 0.0
            add_to_processing_log(state, f"ERROR: {error_msg}")
        
        return state


# Singleton instance
_intent_agent_instance = None


def get_intent_agent() -> IntentUnderstandingAgent:
    """Get or create the Intent Understanding Agent singleton."""
    global _intent_agent_instance
    if _intent_agent_instance is None:
        _intent_agent_instance = IntentUnderstandingAgent()
    return _intent_agent_instance


# Convenience function for direct invocation
def understand_intent(question: str) -> Dict[str, Any]:
    """
    Standalone function to understand intent from a question.
    
    Args:
        question: Natural language question
        
    Returns:
        Parsed intent as dictionary
    """
    from backend.agents.state import initialize_state
    
    agent = get_intent_agent()
    state = initialize_state(question)
    state = agent.invoke(state)
    
    return state["intent"]


if __name__ == "__main__":
    # Test the agent
    test_questions = [
        "Show me all customers who bought products in the last month",
        "What is the average salary of employees in each department?",
        "List the top 5 best-selling products by revenue",
        "How many orders were placed in 2023?"
    ]
    
    print("Testing Intent Understanding Agent\n" + "=" * 50)
    
    for question in test_questions:
        print(f"\nQuestion: {question}")
        print("-" * 50)
        intent = understand_intent(question)
        if intent:
            print(json.dumps(intent, indent=2))
        else:
            print("Failed to parse intent")
        print()
