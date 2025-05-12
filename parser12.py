import os
import re
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load env
load_dotenv()

# Load name → email map
with open("name_email_map.json") as f:
    name_to_email = json.load(f)

# Find the most recent meeting summary .md file
import sys

# Determine markdown input path
if len(sys.argv) > 1:
    latest_md = Path(sys.argv[1])
    if not latest_md.exists():
        raise FileNotFoundError(f"Specified file not found: {latest_md}")
else:
    output_dir = Path("output")
    md_files = list(output_dir.rglob("*_meeting_summaries.md"))
    if not md_files:
        raise FileNotFoundError("No meeting summaries markdown found.")
    latest_md = max(md_files, key=os.path.getctime)
print(f"[parser.py] Using .md file: {latest_md}")

# Extract structured tasks
structured = []

with open(latest_md, encoding="utf-8") as f:
    for line in f:
        if line.strip().startswith("- [ ]"):
            match = re.match(r"- \[ \] ([\w\s@.]+?)\s+to\s+(.*)", line.strip())
            print("[DEBUG] Line:", line.strip())

if match:
    names = match.group(1).strip().split(" and ")
    task = match.group(2).strip().rstrip(".")
    for name in names:
        name = name.strip()
        email = name_to_email.get(name)
        if email:
            structured.append({
                "name": name,
                "email": email,
                "task": task
            })
        else:
            print(f"[SKIP] Name '{name}' not found in name_email_map")




# Use OpenAI to group or pair tasks
calendar_payloads = []

for i in range(len(structured)):
    for j in range(i + 1, len(structured)):
        p1, p2 = structured[i], structured[j]
        prompt = (
            f"Person A: {p1['name']} - Task: {p1['task']}\n"
            f"Person B: {p2['name']} - Task: {p2['task']}\n\n"
            f"Should they coordinate? Reply with 'Yes' or 'No' and explain why."
        )
        try:
            response = client.chat.completions.create(model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=100)
            content = response.choices[0].message.content
            if "yes" in content.lower():
                calendar_payloads.append({
                    "summary": f"Collaboration between {p1['name']} and {p2['name']}",
                    "description": f"{p1['name']} task: {p1['task']}\n{p2['name']} task: {p2['task']}\n\nGPT rationale: {content}",
                    "attendees": [p1["email"], p2["email"]],
                    "preferred_time_range": {
                        "start": (datetime.utcnow() + timedelta(days=2)).replace(hour=13, minute=0).isoformat() + "Z",
                        "end": (datetime.utcnow() + timedelta(days=2)).replace(hour=18, minute=0).isoformat() + "Z"
                    }
                })
        except Exception as e:
            print(f"OpenAI error comparing {p1['name']} and {p2['name']}: {e}")
            print(f"[DEBUG] Structured tasks found: {len(structured)}")
for task in structured:
    print(" -", task)


# Save output
os.makedirs("output", exist_ok=True)
with open("output/calendar_payloads.json", "w") as f:
    json.dump(calendar_payloads, f, indent=2)

print(f" Generated {len(calendar_payloads)} calendar coordination payloads.")
