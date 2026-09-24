import sqlite3
import os
from datetime import datetime, timedelta
import random

def create_db():
    db_path = 'backend/data/sample.db'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Remove existing db if any to ensure clean slate
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.executescript("""
    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL, 
        email TEXT,
        country TEXT, 
        total_spent REAL DEFAULT 0
    );
    CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(customer_id),
        order_date TEXT, 
        total_amount REAL
    );
    CREATE TABLE products (
        product_id INTEGER PRIMARY KEY,
        product_name TEXT NOT NULL, 
        price REAL
    );
    CREATE TABLE order_items (
        item_id INTEGER PRIMARY KEY,
        order_id INTEGER REFERENCES orders(order_id),
        product_id INTEGER REFERENCES products(product_id),
        quantity INTEGER, 
        unit_price REAL
    );
    CREATE TABLE transactions (
        transaction_id INTEGER PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(customer_id),
        amount REAL, 
        transaction_date TEXT
    );
    CREATE TABLE sales (
        sale_id INTEGER PRIMARY KEY,
        sale_date TEXT,
        amount REAL
    );
    """)
    
    # Sample Data
    countries = ['India', 'USA', 'UK', 'Canada', 'Australia']
    
    # Insert Customers
    for i in range(1, 26):
        c.execute(
            "INSERT INTO customers (customer_id, name, email, country, total_spent) VALUES (?, ?, ?, ?, ?)",
            (i, f"Customer {i}", f"cust{i}@example.com", random.choice(countries), 0.0)
        )
        
    # Insert Products
    for i in range(1, 11):
        c.execute(
            "INSERT INTO products (product_id, product_name, price) VALUES (?, ?, ?)",
            (i, f"Product {i}", round(random.uniform(10.0, 500.0), 2))
        )
        
    # Generate Orders and related data
    current_date = datetime.now()
    
    for i in range(1, 51):
        customer_id = random.randint(1, 25)
        days_ago = random.randint(0, 365)
        order_date = (current_date - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
        
        c.execute(
            "INSERT INTO orders (order_id, customer_id, order_date, total_amount) VALUES (?, ?, ?, ?)",
            (i, customer_id, order_date, 0.0) # We will update total amount after items
        )
        
        order_total = 0
        num_items = random.randint(1, 5)
        for j in range(num_items):
            product_id = random.randint(1, 10)
            c.execute("SELECT price FROM products WHERE product_id = ?", (product_id,))
            price = c.fetchone()[0]
            quantity = random.randint(1, 3)
            
            c.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                (i, product_id, quantity, price)
            )
            order_total += price * quantity
            
        c.execute("UPDATE orders SET total_amount = ? WHERE order_id = ?", (order_total, i))
        c.execute("UPDATE customers SET total_spent = total_spent + ? WHERE customer_id = ?", (order_total, customer_id))
        
        # Add a transaction for this order
        c.execute(
            "INSERT INTO transactions (customer_id, amount, transaction_date) VALUES (?, ?, ?)",
            (customer_id, order_total, order_date)
        )
        
        # Add a sale record
        c.execute(
            "INSERT INTO sales (sale_date, amount) VALUES (?, ?)",
            (order_date, order_total)
        )
        
    # Specific tests requirements: 
    # T02, T07: Customers from India, Top 5 customers, spent > 5000 & placed >= 3 orders
    # Let's ensure at least one customer fits this perfectly
    c.execute("INSERT OR REPLACE INTO customers (customer_id, name, email, country, total_spent) VALUES (?, ?, ?, ?, ?)", (999, "VIP India Customer", "vip@example.com", "India", 15000.0))
    for i in range(101, 105):
        c.execute("INSERT INTO orders (order_id, customer_id, order_date, total_amount) VALUES (?, ?, ?, ?)", (i, 999, "2023-10-01 10:00:00", 4000.0))
        c.execute("INSERT INTO transactions (customer_id, amount, transaction_date) VALUES (?, ?, ?)", (999, 4000.0, "2023-10-01 10:00:00"))

    conn.commit()
    conn.close()
    
    # Also create data/sample.db or consolidate. The requirement asks to use backend/data/sample.db as canonical.
    # Let's create a symlink or just another file if necessary, or just rely on backend/data/sample.db
    # It says "Remove/avoid ambiguity with: data/sample.db. If another database path exists, document why or consolidate it."
    # I'll delete data/sample.db if it exists.
    alt_db_path = 'data/sample.db'
    if os.path.exists(alt_db_path):
        os.remove(alt_db_path)
    
    print(f"Database successfully created at {db_path}")

if __name__ == '__main__':
    create_db()
