import sys
from backend.agents.schema_agent import get_schema_agent

def main():
    agent = get_schema_agent()
    agent.connect_to_database()
    print("Introspecting schema...")
    schema_info = agent.introspect_schema()
    print(f"Found {len(schema_info['tables'])} tables.")
    
    print("Indexing into ChromaDB...")
    agent.index_schema(schema_info)
    print("Indexing complete.")

if __name__ == "__main__":
    main()
