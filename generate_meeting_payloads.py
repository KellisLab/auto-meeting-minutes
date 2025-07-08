import os
import re
import json
from pathlib import Path
from datetime import datetime, timedelta
from openai import OpenAI  # ✅ NEW SDK IMPORT

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # 🔐 Make sure this is set

# Load name → email mapping
with open("name_email_map.json") as f:
    name_email_map = json.load(f)

# Load latest meeting summaries .md
output_dir = Path("output")
md_files = list(output_dir.rglob("*_meeting_summaries.md"))
if not md_files:
    raise FileNotFoundError("No _meeting_summaries.md files found.")
latest_md = max(md_files, key=os.path.getctime)

with open(latest_md, encoding="utf-8") as f:
    content = f.read()

# Construct prompt
prompt = f"""
You are a smart assistant that reads meeting notes and identifies potential collaboration meetings.
Below is a transcript of meeting summaries.

Each meeting task should generate a calendar payload with:
- Title of the meeting
- At least two people involved
- Their names and email addresses (you have access to a name-email map)
- A default preferred time slot: two days from now, 2–6 PM UTC

Output a JSON list of dictionaries like:
{{
  "title": "Sync between Alice and Bob on model training",
  "attendees": [
    {{ "name": "Alice", "email": "alice@example.com" }},
    {{ "name": "Bob", "email": "bob@example.com" }}
  ],
  "preferred_time_range": {{
    "start": "2025-05-09T14:00:00Z",
    "end": "2025-05-09T18:00:00Z"
  }}
}}

Name-email map:
{json.dumps(name_email_map, indent=2)}

Meeting transcript:
{content}
"""

# ✅ FIXED OpenAI call
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are an assistant that generates structured meeting payloads from text."},
        {"role": "user", "content": prompt}
    ]
)

# Parse assistant's JSON output
payloads_json = response.choices[0].message.content.strip()
try:
    payloads = json.loads(payloads_json)
except json.JSONDecodeError:
    print("❌ Failed to parse OpenAI output as JSON.")
    print(payloads_json)
    exit(1)

# Save payloads
Path("output").mkdir(exist_ok=True)
with open("output/calendar_payloads.json", "w") as f:
    json.dump(payloads, f, indent=2)

print(f"✅ Generated {len(payloads)} meeting payloads.")
