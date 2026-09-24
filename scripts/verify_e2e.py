import json
from backend.agents.orchestrator import NL2SQLOrchestrator

def main():
    queries = [
        ("T01", "Show me the total number of records in each table.", "user"),
        ("T02", "Show me all customers from India.", "user"),
        ("T03", "Show me the top 5 customers by total spending.", "user"),
        ("T04", "Show me the 10 highest value transactions.", "user"),
        ("T05", "Show me the names of customers and the orders they placed.", "user"),
        ("T06", "Show me total sales by month.", "user"),
        ("T07", "Show me customers who spent more than 5000 and placed at least 3 orders.", "user"),
        ("T08", "Which products have been purchased by customers from India?", "user"),
        ("T09", "Show me the best customers.", "user"),
        ("T10", "Show me information about employees that does not exist in the database.", "user"),
        ("T11", "Delete all customers.", "user"),
        ("T12", "Update every customer's balance to 0.", "user"),
    ]
    
    orchestrator = NL2SQLOrchestrator()
    results = []
    
    for q_id, q_text, role in queries:
        print(f"\\n--- Running {q_id}: {q_text} ---")
        try:
            res = orchestrator.process_query(q_text, user_role=role)
            results.append({
                "id": q_id,
                "question": q_text,
                "sql": res.get("selected_sql"),
                "rows": len(res.get("execution_result", {}).get("data", [])),
                "status": res.get("workflow_status"),
                "tables_retrieved": res.get("relevant_tables", []),
                "intent": res.get("intent", {}),
                "error": res.get("error_message", ""),
                "security_passed": res.get("security_passed", True),
                "data": res.get("execution_result", {}).get("data", [])
            })
            print(f"Status: {res.get('workflow_status')}")
            print(f"SQL: {res.get('selected_sql')}")
            print(f"Rows returned: {len(res.get('execution_result', {}).get('data', []))}")
        except Exception as e:
            print(f"FAILED TO PROCESS: {e}")
            results.append({
                "id": q_id,
                "question": q_text,
                "error": str(e),
                "status": "exception"
            })
            
    with open("e2e_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
