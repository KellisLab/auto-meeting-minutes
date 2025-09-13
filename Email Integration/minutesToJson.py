import os
import subprocess
from dotenv import load_dotenv
from pathlib import Path
import sys
import re
import json
from gpt_recommendations import extract_action_items
from code_specific_recommendations import generate_code_recommendations
from contextual_enrichment import fetch_arxiv_links, fetch_tutorial_links
from cursor import CursorCopilotIntegrator
from github_Auth import get_commits, generate_collaboration_recommendations  # whatever your script is named



load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

normalized = []
panopto_url = input("Enter the Panopto URL: ")

minutes_md = subprocess.run(
    ["python", "fullpipeline.py", panopto_url],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

print("=== STDOUT ===")
print(minutes_md.stdout)
print("==============")

md_path = None
for line in minutes_md.stdout.splitlines():
    if "Speaker summary Markdown:" in line:
        md_path = line.split("Speaker summary Markdown:")[1].strip()
        break

if not md_path or not os.path.exists(md_path):
    print("ERROR: Markdown file not found.")
    sys.exit(1)

# === Step 1: Parse enhanced markdown file ===
with open(md_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

print("\n=== RAW MARKDOWN CONTENT ===")
print("".join(lines))
print("============================\n")

current_speaker = ""
for line in lines:
    line = line.strip()

    # Match speaker line
    speaker_match = re.match(r"<b>([^<]+)</b>", line)
    if speaker_match and not line.startswith("<b>("):  # Ensure it's not a topic line
        current_speaker = speaker_match.group(1).strip()
        continue

    # Match topic + timestamp line
    topic_match = re.match(r"<b>\(\d+\)\s+(.*?)\s*</b>\[\(([\d:]+)\)\]", line)
    if topic_match:
        topic = topic_match.group(1).strip()
        timestamp = topic_match.group(2).strip()

        # Extract summary
        summary_split = line.split("):", 1)
        summary = summary_split[1].strip() if len(summary_split) > 1 else ""

        normalized.append({
            "topic": topic,
            "speaker": current_speaker,
            "timestamp": timestamp,
            "summary": summary
        })

# === Step 2: Group by speaker ===
grouped = {}
for entry in normalized:
    speaker = entry["speaker"]
    if speaker not in grouped:
        grouped[speaker] = {"contributions": [], "timestamps": [], "topics": []}
    grouped[speaker]["contributions"].append(entry["summary"])
    grouped[speaker]["timestamps"].append(entry["timestamp"])
    grouped[speaker]["topics"].append(entry["topic"])



enriched = []
for entry in normalized:
    summary = entry["summary"]
    actions = extract_action_items(summary)
    papers = fetch_arxiv_links(entry["topic"])
    tutorials = fetch_tutorial_links([entry["topic"]])
    code_rec = generate_code_recommendations(summary)

    print(f"\n--- Enrichment Debug ---")
    print(f"Topic: {entry['topic']}")
    print(f"Speaker: {entry['speaker']}")
    print(f"Actions: {actions}")
    print(f"Papers: {papers}")
    print(f"Tutorials: {tutorials}")
    print(f"Code Recs: {code_rec}")
    print("--- End ---\n")

    enriched.append({
        "topic": entry["topic"],
        "speaker": entry["speaker"],
        "timestamp": entry["timestamp"],
        "summary": summary,
        "action_items": actions,
        "papers": papers,
        "tutorials": tutorials,
        "code_recommendations": code_rec
    })

# === Step 4: Save to output directory ===
output_dir = Path(md_path).parent

with open(output_dir / "normalized_minutes.json", "w", encoding="utf-8") as f:
    json.dump(normalized, f, indent=2)

with open(output_dir / "by_speaker.json", "w", encoding="utf-8") as out:
    json.dump(grouped, out, indent=2)

with open(output_dir / "enriched_minutes.json", "w", encoding="utf-8") as out:
    json.dump(enriched, out, indent=2)

print(f"\n✅ Output files saved to: {output_dir}")

# === Step 5: Combine everything into one JSON payload for emailing ===
# === Step 5: Combine everything into one JSON payload for emailing (cleaned) ===
final_payload = {
    "panopto_url": panopto_url,
    "speaker_data": normalized,
    "grouped_by_speaker": grouped,
    "enriched_minutes": enriched
}

# Save combined file
combined_output_path = output_dir / "final_meeting_summary.json"
with open(combined_output_path, "w", encoding="utf-8") as f:
    json.dump(final_payload, f, indent=2)

print(f"\n📦 Final summary saved: {combined_output_path}")
