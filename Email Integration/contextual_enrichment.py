import json
import feedparser
from urllib.parse import quote
from openai import OpenAI
import os
from dotenv import load_dotenv

# === Load environment and initialize OpenAI client ===
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === Load grouped minutes ===
def load_meeting_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# === Fetch arXiv links for a topic ===
def fetch_arxiv_links(query, max_results=2):
    encoded_query = quote(query)
    url = f"http://export.arxiv.org/api/query?search_query=all:{encoded_query}&start=0&max_results={max_results}"
    feed = feedparser.parse(url)
    return [entry.link for entry in feed.entries]

# === Optional GitHub tutorial link fetcher ===
def fetch_tutorial_links(keywords):
    return [f"https://github.com/search?q={kw.replace(' ', '+')}&type=repositories" for kw in keywords]

# === Ask GPT for implementation advice ===
def generate_implementation_suggestions(paper_links, speaker_name):
    prompt = f"""
The following arXiv research papers are relevant to {speaker_name}'s meeting contributions:

{chr(10).join(paper_links)}

Based on these papers, generate concrete implementation recommendations for {speaker_name}.
Include libraries, code ideas, or research-based tools they could use.
"""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()

# === Main ===
if __name__ == "__main__":
    minutes = load_meeting_json("by_speaker.json")

    print("Available speakers:")
    for name in minutes.keys():
        print(f"- {name}")

    speaker_name = input("\nEnter speaker name: ").strip()

    if speaker_name in minutes:
        topics = minutes[speaker_name].get("topics", [])
        paper_links = []
        for topic in set(topics):
            paper_links.extend(fetch_arxiv_links(topic, max_results=2))

        suggestions = generate_implementation_suggestions(paper_links, speaker_name)
        print(f"\n== GPT-4 Implementation Suggestions for {speaker_name} ==\n")
        print(suggestions)
    else:
        print(f"\nError: Speaker '{speaker_name}' not found.")
