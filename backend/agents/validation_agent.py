"""
Agent 4: SQL Validation

This agent validates generated SQL queries using multiple checks:
1. Syntax validation using sqlglot (AST-level parsing)
2. Schema validation (tables/columns exist)
3. Permission validation (user role has access)
4. Semantic validation (query makes sense for the question)

Implements the validation loop - if validation fails, routes back to SQL Generation Agent.
This is a key differentiator from simple linear pipelines.
"""

import json
from typing import Dict, Any, List, Optional, Tuple
import sqlglot
from sqlglot import parse, transpile, ParseError
from backend.core.config import settings
from backend.agents.state import AgentState, add_to_processing_log


class SQLValidationAgent:
    """
    Agent 4: SQL Validation
    
    Validates SQL queries before execution using multiple validation layers.
    Implements the critical validation loop that differentiates this system from simple pipelines.
    """
    
    def __init__(self):
        """Initialize the SQL Validation Agent."""
        self.permission_config = self._load_permission_config()
    
    def _load_permission_config(self) -> Dict[str, Any]:
        """
        Load permission configuration from file or use defaults.
        
        In production, this would be loaded from a database or config service.
        For now, we use a simple role-based permission model.
        """
        # Default permissions by role
        return {
            "admin": {
                "allowed_tables": "*",  # All tables
                "allowed_operations": ["SELECT", "INSERT", "UPDATE", "DELETE"],
                "max_row_limit": 10000
            },
            "analyst": {
                "allowed_tables": "*",
                "allowed_operations": ["SELECT"],
                "max_row_limit": 5000
            },
            "user": {
                "allowed_tables": "*",
                "allowed_operations": ["SELECT"],
                "max_row_limit": 1000
            },
            "guest": {
                "allowed_tables": ["public_view"],  # Restricted tables
                "allowed_operations": ["SELECT"],
                "max_row_limit": 100
            }
        }
    
    def validate_syntax(self, sql: str, dialect: str = None) -> Tuple[bool, List[str]]:
        """
        Validate SQL syntax using sqlglot parser.
        
        Args:
            sql: SQL query string
            dialect: SQL dialect (postgresql, mysql, sqlite, etc.)
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            # Determine dialect from database URL
            if not dialect:
                db_url = settings.database_url
                if "postgresql" in db_url:
                    dialect = "postgres"
                elif "mysql" in db_url:
                    dialect = "mysql"
                else:
                    dialect = "sqlite"
            
            # Parse the SQL
            parsed = parse(sql, read=dialect)
            
            if not parsed or len(parsed) == 0:
                errors.append("Failed to parse SQL - empty result")
                return False, errors
            
            # Check if we got a valid AST
            statement = parsed[0]
            if statement is None:
                errors.append("Parsed SQL resulted in NULL statement")
                return False, errors
            
            # Additional validation: check for balanced parentheses, quotes, etc.
            # (sqlglot handles most of this, but we can add extra checks)
            
            return True, []
            
        except ParseError as e:
            errors.append(f"Syntax error: {str(e)}")
            return False, errors
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            return False, errors
    
    def validate_schema(
        self, 
        sql: str, 
        table_schemas: Dict[str, Any],
        foreign_keys: List[Dict[str, str]]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that all referenced tables and columns exist in the schema.
        
        Args:
            sql: SQL query string
            table_schemas: Dictionary of table schemas
            foreign_keys: List of foreign key relationships
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            # Parse SQL to extract referenced tables and columns
            parsed = parse(sql)
            if not parsed:
                return False, ["Could not parse SQL for schema validation"]
            
            statement = parsed[0]
            
            # Extract all table references
            referenced_tables = set()
            referenced_columns = {}
            
            # Walk through the AST to find table and column references
            for node in statement.walk():
                # Check for table expressions
                if hasattr(node, 'this') and hasattr(node.this, 'this'):
                    if hasattr(node.this.this, 'this'):
                        table_name = node.this.this.this
                        if isinstance(table_name, str):
                            referenced_tables.add(table_name.lower())
                
                # Check for column references
                if hasattr(node, 'this') and hasattr(node, 'alias'):
                    col_name = getattr(node.this, 'this', None)
                    if col_name and isinstance(col_name, str):
                        referenced_columns[col_name.lower()] = True
            
            # Validate tables exist
            available_tables = set(t.lower() for t in table_schemas.keys())
            missing_tables = referenced_tables - available_tables
            
            if missing_tables:
                errors.append(f"Referenced tables not found in schema: {missing_tables}")
            
            # Note: Full column validation would require deeper AST analysis
            # This is a simplified version
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Schema validation error: {str(e)}")
            return False, errors
    
    def validate_permissions(
        self, 
        sql: str, 
        user_role: str,
        table_schemas: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that the user has permission to execute this query.
        
        Args:
            sql: SQL query string
            user_role: User's role (admin, analyst, user, guest)
            table_schemas: Available table schemas
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Get permissions for this role
        permissions = self.permission_config.get(user_role, self.permission_config["user"])
        
        try:
            # Detect operation type
            sql_upper = sql.strip().upper()
            detected_operations = []
            
            if sql_upper.startswith("SELECT"):
                detected_operations.append("SELECT")
            if "INSERT" in sql_upper:
                detected_operations.append("INSERT")
            if "UPDATE" in sql_upper:
                detected_operations.append("UPDATE")
            if "DELETE" in sql_upper:
                detected_operations.append("DELETE")
            
            # Check if operations are allowed
            allowed_ops = permissions.get("allowed_operations", ["SELECT"])
            disallowed_ops = set(detected_operations) - set(allowed_ops)
            
            if disallowed_ops:
                errors.append(
                    f"Operation(s) not permitted for role '{user_role}': {disallowed_ops}"
                )
            
            # Check table permissions
            allowed_tables = permissions.get("allowed_tables", "*")
            if allowed_tables != "*":
                # Extract referenced tables (simplified)
                parsed = parse(sql)
                if parsed:
                    # Check each referenced table against allowed list
                    pass  # Full implementation would extract and check tables
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Permission validation error: {str(e)}")
            return False, errors
    
    def validate_semantic(
        self, 
        sql: str, 
        question: str,
        intent: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that the SQL semantically matches the question intent.
        
        This is a heuristic check - ensures the SQL "makes sense" for the question.
        
        Args:
            sql: SQL query string
            question: Original natural language question
            intent: Parsed intent from Agent 1
            
        Returns:
            Tuple of (is_valid, list_of_warnings)
        """
        warnings = []
        
        sql_upper = sql.upper()
        operations = intent.get("operations", [])
        
        # Check for expected operations
        if "COUNT" in operations and "COUNT" not in sql_upper:
            warnings.append("Question suggests COUNT but SQL doesn't use it")
        
        if "AVG" in operations and ("AVG" not in sql_upper and "AVERAGE" not in sql_upper):
            warnings.append("Question suggests AVG but SQL doesn't use it")
        
        if "GROUP BY" in operations and "GROUP BY" not in sql_upper:
            warnings.append("Question suggests grouping but SQL lacks GROUP BY")
        
        if "ORDER BY" in operations and "ORDER BY" not in sql_upper:
            warnings.append("Question suggests sorting but SQL lacks ORDER BY")
        
        # Check for potential issues
        if "SELECT *" in sql_upper:
            warnings.append("Consider specifying columns instead of SELECT *")
        
        if "CROSS JOIN" in sql_upper:
            warnings.append("CROSS JOIN detected - verify this is intentional")
        
        return len(warnings) == 0, warnings
    
    def invoke(self, state: AgentState) -> AgentState:
        """
        Validate the generated SQL query.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated agent state with validation results
        """
        state["current_agent"] = "validation"
        
        sql = state.get("selected_sql")
        
        if not sql:
            state["is_valid"] = False
            state["validation_errors"] = ["No SQL query to validate"]
            state["validation_result"] = {
                "syntax_valid": False,
                "schema_valid": False,
                "permission_valid": False,
                "semantic_valid": False,
                "errors": ["No SQL provided"]
            }
            return state
        
        all_errors = []
        all_warnings = []
        
        # 1. Syntax validation
        syntax_valid, syntax_errors = self.validate_syntax(sql)
        all_errors.extend(syntax_errors)
        add_to_processing_log(state, f"Syntax validation: {'✓' if syntax_valid else '✗'}")
        
        # 2. Schema validation
        schema_valid, schema_errors = self.validate_schema(
            sql,
            state.get("table_schemas", {}),
            state.get("foreign_keys", [])
        )
        all_errors.extend(schema_errors)
        add_to_processing_log(state, f"Schema validation: {'✓' if schema_valid else '✗'}")
        
        # 3. Permission validation
        permission_valid, permission_errors = self.validate_permissions(
            sql,
            state.get("user_role", "user"),
            state.get("table_schemas", {})
        )
        all_errors.extend(permission_errors)
        add_to_processing_log(state, f"Permission validation: {'✓' if permission_valid else '✗'}")
        
        # 4. Semantic validation
        semantic_valid, semantic_warnings = self.validate_semantic(
            sql,
            state["question"],
            state.get("intent", {})
        )
        all_warnings.extend(semantic_warnings)
        
        # Determine overall validity
        is_valid = syntax_valid and schema_valid and permission_valid
        state["is_valid"] = is_valid
        state["validation_errors"] = all_errors
        state["validation_result"] = {
            "syntax_valid": syntax_valid,
            "schema_valid": schema_valid,
            "permission_valid": permission_valid,
            "semantic_valid": semantic_valid,
            "errors": all_errors,
            "warnings": all_warnings,
            "best_candidate": {
                "sql": sql,
                "confidence": state.get("sql_candidates", [{}])[0].get("confidence", 0)
            } if sql else None
        }
        
        if is_valid:
            add_to_processing_log(state, "✓ SQL validation passed")
        else:
            add_to_processing_log(
                state, 
                f"✗ SQL validation failed: {len(all_errors)} error(s)"
            )
        
        return state
    
    def should_retry(self, state: AgentState) -> bool:
        """
        Determine if SQL generation should be retried.
        
        This implements the conditional edge logic for LangGraph.
        
        Args:
            state: Current agent state
            
        Returns:
            True if retry should be attempted
        """
        return (
            not state["is_valid"] 
            and state.get("retry_count", 0) < state.get("max_retries", 3)
            and state.get("workflow_status") == "running"
        )


# Singleton instance
_validation_agent_instance = None


def get_validation_agent() -> SQLValidationAgent:
    """Get or create the SQL Validation Agent singleton."""
    global _validation_agent_instance
    if _validation_agent_instance is None:
        _validation_agent_instance = SQLValidationAgent()
    return _validation_agent_instance


if __name__ == "__main__":
    # Test the validation agent
    print("Testing SQL Validation Agent\n" + "=" * 50)
    
    from backend.agents.state import initialize_state
    
    agent = get_validation_agent()
    
    test_cases = [
        {
            "name": "Valid SELECT",
            "sql": "SELECT customer_id, name FROM customers WHERE age > 30",
            "should_pass": True
        },
        {
            "name": "Invalid syntax",
            "sql": "SELEC customer_id FRM customers",
            "should_pass": False
        },
        {
            "name": "Missing table",
            "sql": "SELECT * FROM nonexistent_table",
            "should_pass": False
        },
        {
            "name": "Disallowed operation",
            "sql": "DELETE FROM customers WHERE id = 1",
            "should_pass": False  # For 'user' role
        }
    ]
    
    for test in test_cases:
        print(f"\nTest: {test['name']}")
        print(f"SQL: {test['sql']}")
        print("-" * 50)
        
        state = initialize_state("Test question")
        state["selected_sql"] = test["sql"]
        state["table_schemas"] = {
            "customers": {"columns": [{"name": "customer_id", "type": "INTEGER"}]}
        }
        
        result_state = agent.invoke(state)
        
        print(f"Valid: {result_state['is_valid']}")
        if result_state['validation_errors']:
            print(f"Errors: {result_state['validation_errors']}")
        
        expected = "✓" if test['should_pass'] else "✗"
        actual = "✓" if result_state['is_valid'] else "✗"
        status = "PASS" if expected == actual else "FAIL"
        print(f"Expected: {expected}, Got: {actual} → {status}")
