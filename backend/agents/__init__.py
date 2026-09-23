"""
NL2SQL Multi-Agent System — Agents Package

Exports all 8 agent classes and their singleton getters for easy import.
"""

from backend.agents.intent_agent import IntentUnderstandingAgent, get_intent_agent
from backend.agents.schema_agent import SchemaRetrievalAgent, get_schema_agent
from backend.agents.sql_generation_agent import SQLGenerationAgent, get_sql_generation_agent
from backend.agents.validation_agent import SQLValidationAgent, get_validation_agent
from backend.agents.security_agent import SecurityAgent, get_security_agent
from backend.agents.optimization_agent import QueryOptimizationAgent, get_optimization_agent
from backend.agents.execution_agent import SQLExecutionAgent, get_execution_agent
from backend.agents.explanation_agent import ExplanationAgent, get_explanation_agent
from backend.agents.orchestrator import NL2SQLOrchestrator, get_orchestrator, nl2sql
from backend.agents.state import AgentState, initialize_state

__all__ = [
    # Agent classes
    "IntentUnderstandingAgent",
    "SchemaRetrievalAgent",
    "SQLGenerationAgent",
    "SQLValidationAgent",
    "SecurityAgent",
    "QueryOptimizationAgent",
    "SQLExecutionAgent",
    "ExplanationAgent",
    "NL2SQLOrchestrator",
    # Singleton getters
    "get_intent_agent",
    "get_schema_agent",
    "get_sql_generation_agent",
    "get_validation_agent",
    "get_security_agent",
    "get_optimization_agent",
    "get_execution_agent",
    "get_explanation_agent",
    "get_orchestrator",
    # Convenience
    "nl2sql",
    "AgentState",
    "initialize_state",
]
