import json
import os
from groq import Groq
from dotenv import load_dotenv
from prompts.trash import TRIAGE_SYSTEM_PROMPT

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def triage_complaint(complaint: str) -> dict:
    """
    Takes a raw customer complaint and classifies it.
    Returns structured JSON with issue category, priority etc.
    """

    print(f"\n🔍 TRIAGE AGENT analyzing: '{complaint}'")

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Customer complaint: {complaint}"}
        ],
        temperature=0.1  # Low temp = consistent, focused output
    )

    raw = response.choices[0].message.content

    try:
        result = json.loads(raw)
        print(f"✅ Triage Result: {json.dumps(result, indent=2)}")
        return result
    except json.JSONDecodeError:
        print("⚠️ Could not parse JSON, returning raw response")
        return {"raw": raw, "issue_category": "Unknown", "priority": "Medium"}


if __name__ == "__main__":
    # Test the triage agent
    test_complaints = [
        "My 5G signal has been gone since this morning, I can't make calls!",
        "I was charged twice on my bill this month",
        "Internet is extremely slow, videos keep buffering"
    ]

    for complaint in test_complaints:
        triage_complaint(complaint)
        print("-" * 50)