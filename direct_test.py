#!/usr/bin/env python3

# Test the orchestrator directly without going through the API
import sys
import traceback

def test_orchestrator():
    print("🧪 Testing orchestrator directly...")
    
    try:
        # Import and test orchestrator
        from backend.agents.orchestrator import get_orchestrator
        print("✅ Orchestrator imported successfully")
        
        orchestrator = get_orchestrator()
        print("✅ Orchestrator instance created successfully")
        
        # Try to process a simple query
        print("\n🔍 Processing test query...")
        result = orchestrator.process_query(
            question="How many customers are there?",
            database_id="sample", 
            user_role="user",
            include_explanation=True
        )
        
        print("✅ Query processed successfully!")
        print(f"Success: {result.get('success', False)}")
        print(f"Error: {result.get('error_message', 'None')}")
        
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        print("\nFull traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    test_orchestrator()