import sqlite3
import os
from groq import Groq
from dotenv import load_dotenv
from prompts.supporting_agent_prompts import SQL_AGENT_SYSTEM_PROMPT

load_dotenv()

DB_PATH = "db/telecom.db"
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def get_customer_data(customer_id: str) -> dict:
    """Fetch basic customer info directly from DB"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    customer = cursor.fetchone()

    cursor.execute(
        "SELECT * FROM tickets WHERE customer_id = ? ORDER BY created_at DESC LIMIT 5",
        (customer_id,)
    )
    tickets = cursor.fetchall()

    conn.close()

    return {
        "customer": dict(customer) if customer else None,
        "recent_tickets": [dict(t) for t in tickets]
    }


def check_network_in_location(location: str) -> list:
    """Check for active network events in customer's location"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """SELECT * FROM network_events 
           WHERE location = ? AND end_time IS NULL
           ORDER BY severity""",
        (location,)
    )
    events = cursor.fetchall()
    conn.close()

    return [dict(e) for e in events]


def ai_query(question: str, customer_id: str) -> str:
    """Let AI generate and run a SQL query based on natural language"""
    print(f"\n🗄️ SQL AGENT processing: '{question}'")

    prompt = f"Customer ID: {customer_id}\nQuestion: {question}"

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": SQL_AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    sql_query = response.choices[0].message.content.strip()
    print(f"📝 Generated SQL: {sql_query}")

    # Execute the AI-generated query
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql_query)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        print(f"✅ Query returned {len(results)} rows")
        return results
    except Exception as e:
        print(f"❌ SQL Error: {e}")
        return []


if __name__ == "__main__":
    # Test SQL agent
    print("=" * 50)
    print("Testing direct DB fetch for C001:")
    data = get_customer_data("C001")
    print(f"Customer: {data['customer']}")
    print(f"Tickets: {data['recent_tickets']}")

    print("\n" + "=" * 50)
    print("Testing network check for Hyderabad:")
    events = check_network_in_location("Hyderabad")
    print(f"Active events: {events}")

    print("\n" + "=" * 50)
    print("Testing AI-generated SQL query:")
    results = ai_query(
        "Show me all open tickets with usage data for this customer",
        "C001"
    )
    print(f"Results: {results}")