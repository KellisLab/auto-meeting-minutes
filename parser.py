import os
import re
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
from openai import OpenAI

# === Load env ===
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === Load name → email map (case-insensitive keys) ===
with open("name_email_map.json") as f:
    raw_map = json.load(f)
    name_to_email = {k.strip().lower(): v for k, v in raw_map.items()}

# === Determine markdown input path ===
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

# === Extract structured tasks ===
structured = []

with open(latest_md, encoding="utf-8") as f:
    for line in f:
        if line.strip().startswith("- [ ]"):
            match = re.match(r"- \[ \] ([\w\s@.]+?)\s+to\s+(.*)", line.strip())
            if match:
                names = match.group(1).strip().split(" and ")
                task = match.group(2).strip().rstrip(".")
                for name in names:
                    email = name_to_email.get(name.strip().lower())
                    if email:
                        structured.append({
                            "name": name.strip(),
                            "email": email,
                            "task": task
                        })
                    else:
                        print(f"[SKIP] Name '{name}' not found in name_email_map")

# === De-duplicate exact (name, task) entries ===
unique_structured = []
seen = set()
for item in structured:
    key = (item["name"].lower(), item["task"])
    if key not in seen:
        seen.add(key)
        unique_structured.append(item)
structured = unique_structured

print(f"[DEBUG] Structured tasks found: {len(structured)}")
for task in structured:
    print(" -", task)

# === GPT-based coordination logic ===
calendar_payloads = []
for i in range(len(structured)):
    for j in range(i + 1, len(structured)):
        p1, p2 = structured[i], structured[j]

        # ✅ Prevent self-pairing
        if p1["email"] == p2["email"]:
            continue

        prompt = (
            f"Person A: {p1['name']} - Task: {p1['task']}\n"
            f"Person B: {p2['name']} - Task: {p2['task']}\n\n"
            f"Should they coordinate? Reply with 'Yes' or 'No' and explain why."
        )
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=100
            )
            content = response.choices[0].message.content
            print(f"[GPT] {p1['name']} + {p2['name']} → {content.strip()}")
            if "yes" in content.lower():
                calendar_payloads.append({
                    "summary": f"Collaboration between {p1['name']} and {p2['name']}",
                    "description": f"{p1['name']} task: {p1['task']}\n{p2['name']} task: {p2['task']}\n\nGPT rationale: {content}",
                    "attendees": [
                        {"email": p1["email"]},
                        {"email": p2["email"]}
                    ],
                    "preferred_time_range": {
                        "start": (datetime.utcnow() + timedelta(days=2)).replace(hour=13, minute=0).isoformat() + "Z",
                        "end": (datetime.utcnow() + timedelta(days=2)).replace(hour=18, minute=0).isoformat() + "Z"
                    }
                })
        except Exception as e:
            print(f"[OpenAI ERROR] Comparing {p1['name']} and {p2['name']}: {e}")

# === Save output ===
os.makedirs("output", exist_ok=True)
with open("output/calendar_payloads.json", "w") as f:
    json.dump(calendar_payloads, f, indent=2)

print(f"✅ Generated {len(calendar_payloads)} calendar coordination payloads.")
