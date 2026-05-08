import sqlite3
import os

DB_PATH = "db/telecom.db"

def create_database():
    os.makedirs("db", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # --- CUSTOMERS TABLE ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT,
            email TEXT,
            plan TEXT,
            location TEXT,
            account_status TEXT
        )
    ''')

    # --- TICKETS TABLE ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            customer_id TEXT,
            issue_type TEXT,
            description TEXT,
            status TEXT,
            created_at TEXT,
            resolved_at TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
    ''')

    # --- NETWORK EVENTS TABLE ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS network_events (
            event_id TEXT PRIMARY KEY,
            location TEXT,
            event_type TEXT,
            severity TEXT,
            start_time TEXT,
            end_time TEXT,
            affected_customers INTEGER
        )
    ''')

    # --- USAGE DATA TABLE ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usage_data (
            usage_id TEXT PRIMARY KEY,
            customer_id TEXT,
            month TEXT,
            data_used_gb REAL,
            call_minutes INTEGER,
            sms_count INTEGER,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
    ''')

    print("✅ Tables created successfully!")

    # --- SEED CUSTOMERS ---
    customers = [
        ("C001", "Ravi Kumar",    "9876543210", "ravi@email.com",    "5G Unlimited", "Hyderabad", "Active"),
        ("C002", "Priya Sharma",  "9845012345", "priya@email.com",   "4G Basic",     "Mumbai",    "Active"),
        ("C003", "John Doe",      "9900112233", "john@email.com",    "5G Premium",   "Delhi",     "Suspended"),
        ("C004", "Anjali Singh",  "9812345678", "anjali@email.com",  "4G Unlimited", "Bangalore", "Active"),
        ("C005", "Mohammed Ali",  "9798765432", "mali@email.com",    "5G Unlimited", "Chennai",   "Active"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?,?)", customers
    )

    # --- SEED TICKETS ---
    tickets = [
        ("T001", "C001", "No Signal",       "No 5G signal since morning",         "Open",     "2024-01-15 09:00", None),
        ("T002", "C002", "Slow Internet",   "Internet very slow, can't stream",   "Open",     "2024-01-15 10:30", None),
        ("T003", "C003", "Billing Issue",   "Charged twice for same month",       "Resolved", "2024-01-10 08:00", "2024-01-11 12:00"),
        ("T004", "C004", "Call Dropping",   "Calls drop every 2-3 minutes",       "Open",     "2024-01-15 11:00", None),
        ("T005", "C005", "No Internet",     "Internet not working since 2 days",  "Open",     "2024-01-14 14:00", None),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO tickets VALUES (?,?,?,?,?,?,?)", tickets
    )

    # --- SEED NETWORK EVENTS ---
    network_events = [
        ("NE001", "Hyderabad", "Tower Outage",       "High",   "2024-01-15 08:00", "2024-01-15 14:00", 250),
        ("NE002", "Mumbai",    "Fiber Cut",           "Medium", "2024-01-15 09:30", None,               120),
        ("NE003", "Chennai",   "Planned Maintenance", "Low",    "2024-01-14 12:00", "2024-01-14 18:00", 80),
        ("NE004", "Delhi",     "Congestion",          "Medium", "2024-01-15 08:00", None,               500),
        ("NE005", "Bangalore", "Tower Outage",        "High",   "2024-01-15 10:00", None,               300),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO network_events VALUES (?,?,?,?,?,?,?)", network_events
    )

    # --- SEED USAGE DATA ---
    usage_data = [
        ("U001", "C001", "2024-01", 45.5, 320, 150),
        ("U002", "C002", "2024-01",  8.2, 180,  90),
        ("U003", "C003", "2024-01", 60.0, 500, 200),
        ("U004", "C004", "2024-01", 22.3, 240, 110),
        ("U005", "C005", "2024-01", 38.7, 410, 175),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO usage_data VALUES (?,?,?,?,?,?)", usage_data
    )

    conn.commit()
    conn.close()
    print("✅ Seed data inserted successfully!")
    print("✅ Database ready at:", DB_PATH)

if __name__ == "__main__":
    create_database()