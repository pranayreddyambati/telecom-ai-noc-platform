import os
from groq import Groq
from dotenv import load_dotenv
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prompts.prompt_templates import RESOLUTION_SYSTEM_PROMPT

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_resolution(customer_data: dict, triage_result: dict, network_events: list) -> str:
    """
    Takes customer info, triage classification, and network events
    and generates a full resolution plan.
    """
    print(f"\n🛠️ RESOLUTION AGENT generating fix...")

    # Build context for the AI
    context = f"""
CUSTOMER INFORMATION:
- Name: {customer_data.get('name')}
- Plan: {customer_data.get('plan')}
- Location: {customer_data.get('location')}
- Account Status: {customer_data.get('account_status')}

COMPLAINT ANALYSIS:
- Category: {triage_result.get('issue_category')}
- Priority: {triage_result.get('priority')}
- Summary: {triage_result.get('summary')}

ACTIVE NETWORK EVENTS IN {customer_data.get('location', 'their area')}:
{format_network_events(network_events)}

RECENT TICKETS:
{triage_result.get('summary', 'No prior tickets')}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": RESOLUTION_SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ],
        temperature=0.3
    )

    resolution = response.choices[0].message.content
    print("✅ Resolution generated!")
    return resolution


def format_network_events(events: list) -> str:
    if not events:
        return "No active network events found in this area."
    
    result = ""
    for e in events:
        result += f"- {e['event_type']} | Severity: {e['severity']} | Started: {e['start_time']} | Affected: {e['affected_customers']} customers\n"
    return result