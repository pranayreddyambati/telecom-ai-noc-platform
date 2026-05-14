import sqlite3
import random

from faker import Faker
from datetime import datetime, timedelta

fake = Faker("en_IN")

DB_PATH = "db/telecom.db"

# ─────────────────────────────────────────────
# MASTER DATA
# ─────────────────────────────────────────────

LOCATIONS = [
    "Hyderabad",
    "Mumbai",
    "Delhi",
    "Bangalore",
    "Chennai",
    "Pune",
    "Kolkata",
    "Ahmedabad"
]

PLANS = [
    "4G Basic",
    "4G Unlimited",
    "5G Unlimited",
    "5G Premium",
    "Fiber Max"
]

ISSUE_TYPES = [
    "No Signal",
    "Slow Internet",
    "Billing Issue",
    "Call Dropping",
    "No Internet",
    "Fiber Down",
    "SIM Activation",
    "5G Connectivity"
]

EVENT_TYPES = [
    "Tower Outage",
    "Fiber Cut",
    "Congestion",
    "Planned Maintenance",
    "Power Failure"
]

SUPPORT_TEAMS = [
    "Core Network",
    "Billing Ops",
    "Fiber Support",
    "SIM Provisioning",
    "Customer Care"
]

REGIONS = [
    "North",
    "South",
    "East",
    "West",
    "Central"
]

# ─────────────────────────────────────────────
# RANDOM DATE GENERATOR
# ─────────────────────────────────────────────

def random_past_datetime(days_back=30):

    dt = datetime.now() - timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59)
    )

    return dt

# ─────────────────────────────────────────────
# DATABASE CONNECTION
# ─────────────────────────────────────────────

conn = sqlite3.connect(DB_PATH)

# Enable foreign keys
conn.execute("PRAGMA foreign_keys = ON")

cursor = conn.cursor()

print("Connected to database")

# ─────────────────────────────────────────────
# CUSTOMERS
# ─────────────────────────────────────────────

customers = []

TOTAL_CUSTOMERS = 250

for i in range(1, TOTAL_CUSTOMERS + 1):

    cid = f"C{i:04}"

    customer = (
        cid,
        fake.name(),
        fake.msisdn()[:10],
        fake.email(),
        random.choice(PLANS),
        random.choice(LOCATIONS),
        random.choices(
            ["Active", "Suspended", "Inactive"],
            weights=[85, 10, 5]
        )[0]
    )

    customers.append(customer)

cursor.executemany("""
INSERT OR IGNORE INTO customers (
    customer_id,
    name,
    phone,
    email,
    plan,
    location,
    account_status
)
VALUES (?,?,?,?,?,?,?)
""", customers)

print(f"Inserted {len(customers)} customers")

# ─────────────────────────────────────────────
# TICKETS
# ─────────────────────────────────────────────

tickets = []

ticket_counter = 1

for customer in customers:

    customer_id = customer[0]

    # ONLY SOME CUSTOMERS HAVE TICKETS
    has_ticket = random.random() < 0.38

    if not has_ticket:
        continue

    # SOME CUSTOMERS HAVE MULTIPLE TICKETS
    ticket_count = random.choices(
        [1, 2, 3, 4, 5],
        weights=[50, 25, 12, 8, 5]
    )[0]

    for _ in range(ticket_count):

        created_dt = random_past_datetime(21)

        status = random.choices(
            ["Open", "Resolved"],
            weights=[35, 65]
        )[0]

        resolved_at = None

        if status == "Resolved":

            resolved_dt = created_dt + timedelta(
                hours=random.randint(2, 72)
            )

            resolved_at = resolved_dt.strftime(
                "%Y-%m-%d %H:%M"
            )

        issue_type = random.choices(
            ISSUE_TYPES,
            weights=[14, 20, 10, 16, 18, 8, 6, 12]
        )[0]

        # ─────────────────────────────────────
        # NEW ANALYTICS FIELDS
        # ─────────────────────────────────────

        priority = random.choices(
            ["Low", "Medium", "High", "Critical"],
            weights=[20, 45, 25, 10]
        )[0]

        severity = priority

        resolved_within_sla = (
            1 if random.random() < 0.82 else 0
        )

        assigned_team = random.choice(
            SUPPORT_TEAMS
        )

        affected_customers = random.randint(
            50,
            5000
        )

        ticket = (
            f"T{ticket_counter:05}",
            customer_id,
            issue_type,
            fake.sentence(nb_words=10),
            status,
            created_dt.strftime("%Y-%m-%d %H:%M"),
            resolved_at,

            priority,
            severity,
            resolved_within_sla,
            assigned_team,
            affected_customers
        )

        tickets.append(ticket)

        ticket_counter += 1

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
""", tickets)

print(f"Inserted {len(tickets)} tickets")

# ─────────────────────────────────────────────
# NETWORK EVENTS
# ─────────────────────────────────────────────

events = []

for i in range(1, 45):

    start_dt = random_past_datetime(14)

    active = random.random() < 0.32

    end_time = None

    if not active:

        end_dt = start_dt + timedelta(
            hours=random.randint(1, 18)
        )

        end_time = end_dt.strftime(
            "%Y-%m-%d %H:%M"
        )

    severity = random.choices(
        ["Minor", "Major", "Critical"],
        weights=[50, 35, 15]
    )[0]

    location = random.choices(
        LOCATIONS,
        weights=[15, 18, 14, 16, 12, 10, 8, 7]
    )[0]

    affected_customers = {
        "Minor": random.randint(40, 500),
        "Major": random.randint(500, 5000),
        "Critical": random.randint(5000, 50000)
    }[severity]

    region = random.choice(REGIONS)

    event = (
        f"NE{i:04}",
        location,
        random.choice(EVENT_TYPES),
        severity,
        start_dt.strftime("%Y-%m-%d %H:%M"),
        end_time,
        affected_customers,
        region
    )

    events.append(event)

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
""", events)

print(f"Inserted {len(events)} network events")

# ─────────────────────────────────────────────
# USAGE DATA
# ─────────────────────────────────────────────

usage_rows = []

usage_counter = 1

for customer in customers:

    customer_id = customer[0]

    for month in ["2026-03", "2026-04", "2026-05"]:

        usage = (
            f"U{usage_counter:05}",
            customer_id,
            month,

            # Data usage in GB
            round(random.uniform(2, 220), 1),

            # Call minutes
            random.randint(20, 2400),

            # SMS count
            random.randint(5, 1200)
        )

        usage_rows.append(usage)

        usage_counter += 1

cursor.executemany("""
INSERT OR IGNORE INTO usage_data (
    usage_id,
    customer_id,
    month,
    data_used_gb,
    call_minutes,
    sms_count
)
VALUES (?,?,?,?,?,?)
""", usage_rows)

print(f"Inserted {len(usage_rows)} usage rows")

# ─────────────────────────────────────────────
# SAVE CHANGES
# ─────────────────────────────────────────────

conn.commit()

print("\nDatabase population complete.")

# ─────────────────────────────────────────────
# OPTIONAL VALIDATION
# ─────────────────────────────────────────────

print("\nTicket Severity Distribution:")

rows = cursor.execute("""
    SELECT severity, COUNT(*)
    FROM tickets
    GROUP BY severity
""").fetchall()

for row in rows:
    print(row)

print("\nNetwork Event Severity Distribution:")

rows = cursor.execute("""
    SELECT severity, COUNT(*)
    FROM network_events
    GROUP BY severity
""").fetchall()

for row in rows:
    print(row)

conn.close()

print("\nDone")