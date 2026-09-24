import sqlite3
import os

db_path = 'backend/data/demo_employees.db'
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
conn.execute('CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, department_id INTEGER)')
conn.execute('CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT)')
conn.execute('CREATE TABLE salaries (employee_id INTEGER, amount REAL)')
conn.execute("INSERT INTO departments VALUES (1, 'Engineering')")
conn.execute("INSERT INTO employees VALUES (1, 'Alice', 1)")
conn.execute("INSERT INTO salaries VALUES (1, 95000.0)")
conn.commit()
conn.close()
print('Database created.')
