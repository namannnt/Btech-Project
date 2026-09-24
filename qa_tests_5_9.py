import urllib.request
import json
import time
import sqlite3
import sys

url = 'http://localhost:8000/api/v1/query'
tests = [
    {"name": "TEST 5", "q": "Show me total sales by month."},
    {"name": "TEST 6", "q": "Show me the employees' salaries."},
    {"name": "TEST 7", "q": "Delete all customers from India."},
    {"name": "TEST 8", "q": "Update all customers from India and set their total_spent to 0."},
    {"name": "TEST 9", "q": "Show me customers from India'; DROP TABLE customers; --"}
]

for t in tests:
    q = t["q"]
    req = urllib.request.Request(url, method='POST')
    req.add_header('Content-Type', 'application/json')
    data = json.dumps({'question': q, 'user_role': 'user', 'include_explanation': True}).encode('utf-8')
    
    success = False
    while not success:
        try:
            response = urllib.request.urlopen(req, data=data)
            res_data = json.loads(response.read().decode('utf-8'))
            
            logs = res_data.get('processing_log', [])
            error_msg = str(res_data.get('error_message') or '')
            
            if '429' in error_msg or any('429' in log for log in logs) or 'rate_limit' in error_msg.lower():
                print(f"Test {t['name']} hit 429. Sleeping 60s...")
                sys.stdout.flush()
                time.sleep(60)
                continue
                
            print('=========================')
            print(f"Test Name: {t['name']}")
            print(f"User Question: {res_data.get('question')}")
            print(f"Generated SQL: {res_data.get('generated_sql')}")
            print(f"SQL parameters: {res_data.get('sql_parameters')}")
            
            val = res_data.get('validation') or {}
            print(f"Validation Result: {val.get('is_valid')} (Errors: {val.get('errors')})")
            
            sec = res_data.get('security') or {}
            print(f"Security Result: {sec.get('passed')} (Violations: {sec.get('violations')})")
            
            exec_res = res_data.get('execution_result') or {}
            print(f"Execution success/failure: {exec_res.get('success')} (Error: {exec_res.get('error_message')})")
            
            rows = exec_res.get('rows')
            print(f"Row count: {exec_res.get('row_count')}")
            print(f"First 3 returned rows: {rows[:3] if rows else []}")
            
            exp = res_data.get('explanation') or {}
            res_sum = exp.get('result_summary')
            print(f"Final application explanation: {res_sum}".encode('utf-8', 'ignore').decode('ascii', 'ignore') if res_sum else "None")
            
            print('Processing log:')
            for log in logs:
                print(log)
            print('\n')
            sys.stdout.flush()
            
            success = True
            time.sleep(20)
            
        except Exception as e:
            print(f'Error on query: {q}, {str(e)}')
            sys.stdout.flush()
            time.sleep(30)

print('=========================')
print('Database Check:')
try:
    conn = sqlite3.connect('./backend/data/sample.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM customers")
    print(f"Customers table count after tests: {c.fetchone()[0]}")
    conn.close()
except Exception as e:
    print(f"Database check failed: {str(e)}")
