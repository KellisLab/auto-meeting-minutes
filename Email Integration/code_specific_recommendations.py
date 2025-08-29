import os
import json
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def load_meeting_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_code_recommendations(summary_text):
    prompt = f"""Given the following contributions and action items, provide:
6. Libraries that can be used to implement the new features
7. Libraries that can be used to implement the new optimizations
8. Libraries that can be used to implement the new libraries
9. Libraries that can be used to implement the new research papers and articles

Summary:
\"\"\"
{summary_text}
\"\"\"

Respond in JSON format with keys: "libraries", "refactoring", "implementation".
"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    return response.choices[0].message.content.strip()


