#!/usr/bin/env python3

import requests
import json

# Test the API endpoint
def test_api():
    url = "http://localhost:8000/api/v1/query"  # REAL backend, not mock
    
    payload = {
        "question": "How many customers are there?",
        "database_id": "sample",
        "user_role": "user",
        "include_explanation": True
    }
    
    try:
        print("🧪 Testing REAL NL2SQL API (not mock)")        
        print(f"URL: {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        print("-" * 50)
        
        response = requests.post(url, json=payload, timeout=60)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed. Is the server running on port 8000?")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_api()