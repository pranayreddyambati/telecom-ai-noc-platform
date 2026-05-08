import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.triage_agent import triage_complaint
from agents.sql_agent import get_customer_data, check_network_in_location
from agents.resolution_agent import generate_resolution

def run_support_pipeline(customer_id: str, complaint: str):
    print("\n" + "="*60)
    print(f"🚀 TELECOM AI ANALYST - Processing Support Request")
    print(f"   Customer ID : {customer_id}")
    print(f"   Complaint   : {complaint}")
    print("="*60)

    # --- STEP 1: TRIAGE AGENT ---
    print("\n📋 STEP 1: Triage Agent classifying complaint...")
    triage_result = triage_complaint(complaint)

    # --- STEP 2: SQL AGENT - Fetch Customer Data ---
    print("\n📋 STEP 2: SQL Agent fetching customer data...")
    db_data = get_customer_data(customer_id)
    customer = db_data.get("customer")

    if not customer:
        print(f"❌ Customer {customer_id} not found in database!")
        return

    print(f"✅ Found customer: {customer['name']} | Plan: {customer['plan']} | Location: {customer['location']}")

    # --- STEP 3: Check Network Events (if needed) ---
    network_events = []
    if triage_result.get("needs_network_check"):
        print(f"\n📋 STEP 3: Checking network events in {customer['location']}...")
        network_events = check_network_in_location(customer['location'])
        if network_events:
            print(f"⚠️  Found {len(network_events)} active network event(s)!")
        else:
            print(f"✅ No active network events in {customer['location']}")
    else:
        print("\n📋 STEP 3: Network check skipped (not a network issue)")

    # --- STEP 4: RESOLUTION AGENT ---
    print("\n📋 STEP 4: Resolution Agent generating fix...")
    resolution = generate_resolution(customer, triage_result, network_events)

    # --- FINAL OUTPUT ---
    print("\n" + "="*60)
    print("📊 FINAL RESOLUTION REPORT")
    print("="*60)
    print(resolution)
    print("="*60)

    return {
        "customer": customer,
        "triage": triage_result,
        "network_events": network_events,
        "resolution": resolution
    }


if __name__ == "__main__":
    # Test Case 1 — Network Issue
    run_support_pipeline(
        customer_id="C001",
        complaint="My 5G signal has been gone since this morning, I can't make calls!"
    )

    print("\n\n")

    # Test Case 2 — Billing Issue
    run_support_pipeline(
        customer_id="C003",
        complaint="I was charged twice on my bill this month"
    )