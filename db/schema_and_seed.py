import sqlite3
import os
import random

DB_PATH = "db/telecom.db"

def create_database():

    os.makedirs("db", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    cursor = conn.cursor()

    # ─────────────────────────────────────────
    # CUSTOMERS TABLE
    # ─────────────────────────────────────────

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT,
            email TEXT,
            plan TEXT,
            location TEXT,
            account_status TEXT
        )
    """)

    # ─────────────────────────────────────────
    # TICKETS TABLE
    # ─────────────────────────────────────────

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            customer_id TEXT,
            issue_type TEXT,
            description TEXT,
            status TEXT,
            created_at TEXT,
            resolved_at TEXT,

            priority TEXT DEFAULT 'Medium',
            severity TEXT DEFAULT 'Medium',
            resolved_within_sla INTEGER DEFAULT 1,
            assigned_team TEXT,
            affected_customers INTEGER DEFAULT 0,

            FOREIGN KEY (customer_id)
                REFERENCES customers(customer_id)
        )
    """)

    # ─────────────────────────────────────────
    # NETWORK EVENTS TABLE
    # ─────────────────────────────────────────

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS network_events (
            event_id TEXT PRIMARY KEY,
            location TEXT,
            event_type TEXT,

            severity TEXT DEFAULT 'Minor',

            start_time TEXT,
            end_time TEXT,

            affected_customers INTEGER DEFAULT 0,

            region TEXT
        )
    """)

    # ─────────────────────────────────────────
    # USAGE DATA TABLE
    # ─────────────────────────────────────────

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_data (
            usage_id TEXT PRIMARY KEY,
            customer_id TEXT,
            month TEXT,
            data_used_gb REAL,
            call_minutes INTEGER,
            sms_count INTEGER,

            FOREIGN KEY (customer_id)
                REFERENCES customers(customer_id)
        )
    """)

    print("✅ Tables created successfully!")

    # ─────────────────────────────────────────
    # SEED CUSTOMERS
    # ─────────────────────────────────────────

    customers = [
        ("C001", "Ravi Kumar",   "9876543210", "ravi@email.com",   "5G Unlimited", "Hyderabad", "Active"),
        ("C002", "Priya Sharma", "9845012345", "priya@email.com",  "4G Basic",     "Mumbai",    "Active"),
        ("C003", "John Doe",     "9900112233", "john@email.com",   "5G Premium",   "Delhi",     "Suspended"),
        ("C004", "Anjali Singh", "9812345678", "anjali@email.com", "4G Unlimited", "Bangalore", "Active"),
        ("C005", "Mohammed Ali", "9798765432", "mali@email.com",   "5G Unlimited", "Chennai",   "Active"),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO customers
        VALUES (?,?,?,?,?,?,?)
    """, customers)

    # ─────────────────────────────────────────
    # SEED TICKETS
    # ─────────────────────────────────────────

    ticket_rows = []

    base_tickets = [
        ("T001", "C001", "No Signal",     "No 5G signal since morning",        "Open",     "2024-01-15 09:00", None),
        ("T002", "C002", "Slow Internet", "Internet very slow, can't stream",  "Open",     "2024-01-15 10:30", None),
        ("T003", "C003", "Billing Issue", "Charged twice for same month",      "Resolved", "2024-01-10 08:00", "2024-01-11 12:00"),
        ("T004", "C004", "Call Dropping", "Calls drop every 2-3 minutes",      "Open",     "2024-01-15 11:00", None),
        ("T005", "C005", "No Internet",   "Internet not working since 2 days", "Open",     "2024-01-14 14:00", None),
    ]

    for ticket in base_tickets:

        r = random.randint(1, 100)

        if r <= 10:
            priority = severity = "Critical"
        elif r <= 35:
            priority = severity = "High"
        elif r <= 75:
            priority = severity = "Medium"
        else:
            priority = severity = "Low"

        resolved_within_sla = 1 if random.randint(1, 100) <= 82 else 0

        affected_customers = random.randint(50, 5000)

        assigned_team = random.choice([
            "Core Network",
            "Billing Ops",
            "Fiber Support",
            "SIM Provisioning",
            "Customer Care"
        ])

        ticket_rows.append((
            *ticket,
            priority,
            severity,
            resolved_within_sla,
            assigned_team,
            affected_customers
        ))

    cursor.executemany("""
        INSERT OR IGNORE INTO tickets (
            ticket_id,
            customer_id,
            issue_type,
            description,
            status,
            created_at,
            resolved_at,
            priority,
            severity,
            resolved_within_sla,
            assigned_team,
            affected_customers
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, ticket_rows)

    # ─────────────────────────────────────────
    # SEED NETWORK EVENTS
    # ─────────────────────────────────────────

    network_rows = []

    base_events = [
        ("NE001", "Hyderabad", "Tower Outage",       "2024-01-15 08:00", "2024-01-15 14:00"),
        ("NE002", "Mumbai",    "Fiber Cut",          "2024-01-15 09:30", None),
        ("NE003", "Chennai",   "Planned Maintenance","2024-01-14 12:00", "2024-01-14 18:00"),
        ("NE004", "Delhi",     "Congestion",         "2024-01-15 08:00", None),
        ("NE005", "Bangalore", "Tower Outage",       "2024-01-15 10:00", None),
    ]

    for event in base_events:

        r = random.randint(1, 100)

        if r <= 15:
            severity = "Critical"
        elif r <= 45:
            severity = "Major"
        else:
            severity = "Minor"

        affected_customers = random.randint(1000, 50000)

        region = random.choice([
            "North",
            "South",
            "East",
            "West",
            "Central"
        ])

        network_rows.append((
            event[0],
            event[1],
            event[2],
            severity,
            event[3],
            event[4],
            affected_customers,
            region
        ))

    cursor.executemany("""
        INSERT OR IGNORE INTO network_events (
            event_id,
            location,
            event_type,
            severity,
            start_time,
            end_time,
            affected_customers,
            region
        )
        VALUES (?,?,?,?,?,?,?,?)
    """, network_rows)

    # ─────────────────────────────────────────
    # SEED USAGE DATA
    # ─────────────────────────────────────────

    usage_data = [
        ("U001", "C001", "2024-01", 45.5, 320, 150),
        ("U002", "C002", "2024-01", 8.2, 180, 90),
        ("U003", "C003", "2024-01", 60.0, 500, 200),
        ("U004", "C004", "2024-01", 22.3, 240, 110),
        ("U005", "C005", "2024-01", 38.7, 410, 175),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO usage_data
        VALUES (?,?,?,?,?,?)
    """, usage_data)

    conn.commit()

    conn.close()

    print("✅ Database ready successfully!")
    print("✅ Path:", DB_PATH)

if __name__ == "__main__":
    create_database()