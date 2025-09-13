import os
import re
import json
from pathlib import Path

# Load name-to-email map
with open("name_email_map.json", "r", encoding="utf-8") as f:
    name_email_map = json.load(f)

# Locate the latest *_meeting_summaries.md file
output_dir = Path("output")
md_files = list(output_dir.rglob("*_meeting_summaries.md"))
if not md_files:
    raise FileNotFoundError("No meeting summaries markdown files found.")

latest_md = max(md_files, key=os.path.getctime)

# Read content from .md file
with open(latest_md, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Match names to emails
matched_names = {}

for line in lines:
    # Extract names with format: capitalized words, possibly with a space (e.g., "Josh Wu")
    names = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\b", line)
    for name in names:
        if name in name_email_map:
            matched_names[name] = name_email_map[name]

# Output the matches
print(f"\nMatched names from {latest_md.name}:")
for name, email in matched_names.items():
    print(f"{name}: {email}")
