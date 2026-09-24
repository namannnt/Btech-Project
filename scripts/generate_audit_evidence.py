import json
import os
import sys

from backend.agents.orchestrator import NL2SQLOrchestrator
import sqlite3

def verify_db_rows():
    db_path = os.path.join("backend", "data", "sample.db")
    if not os.path.exists(db_path):
        return {"error": f"Database not found at {db_path}"}
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    tables_to_check = ['customers', 'products', 'orders', 'order_items']
    db_counts = {}
    for table in tables_to_check:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            db_counts[table] = cursor.fetchone()[0]
        except Exception as e:
            db_counts[table] = str(e)
            
    conn.close()
    return db_counts

def main():
    queries = {
        "T01": "Show me the total number of records in each table.",
        "T02": "Show me all customers from India.",
        "T03": "Show me the top 5 customers by total spending.",
        "T04": "Show me the 10 highest value transactions.",
        "T05": "Show me the names of customers and the orders they placed.",
        "T06": "Show me total sales by month.",
        "T07": "Show me customers who spent more than 5000 and placed at least 3 orders.",
        "T08": "Which products have been purchased by customers from India?",
        "T09": "Show me the best customers.",
        "T10": "Show me information about employees that does not exist in the database.",
        "T11": "Delete all customers.",
        "T12": "Update every customer's balance to 0."
    }

    orchestrator = NL2SQLOrchestrator()
    
    evidence = []
    
    for q_id, q_text in queries.items():
        print(f"Running {q_id}...")
        try:
            state = orchestrator.process_query(q_text, user_role="user")
            
            # extract details
            evidence.append({
                "id": q_id,
                "query": q_text,
                "intent_output": state.get("intent"),
                "schema_tables": state.get("relevant_tables"),
                "sql_generated": state.get("selected_sql"),
                "validation_result": state.get("validation_result"),
                "security_result": state.get("security_result"),
                "security_passed": state.get("security_passed"),
                "optimization_result": {
                    "original_sql": state.get("original_sql"),
                    "optimized_sql": state.get("optimized_sql"),
                    "optimizations_applied": state.get("optimizations_applied")
                },
                "execution_result": {
                    "success": state.get("execution_success"),
                    "error": state.get("execution_error")
                },
                "row_count": len(state.get("query_results", []) or []),
                "explanation_output": state.get("sql_explanation"),
                "retry_count": state.get("retry_count"),
                "processing_log": state.get("processing_log")
            })
        except Exception as e:
            print(f"Error on {q_id}: {e}")
            evidence.append({
                "id": q_id,
                "query": q_text,
                "error": str(e)
            })

    db_rows_after = verify_db_rows()
            
    out = {
        "evidence": evidence,
        "db_rows_after": db_rows_after
    }
            
    with open("audit_evidence.json", "w") as f:
        json.dump(out, f, indent=2)

if __name__ == "__main__":
    main()
