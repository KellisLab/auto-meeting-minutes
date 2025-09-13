import os
import json
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_action_items(summary_text):
    prompt = f""" 
Extract from the following presentation summary:
1. A list of next step recommendations for the speaker
2. Key decisions or implied changes
Respond in JSON with keys: "next_steps", "decisions"

Summary:
\"\"\"
{summary_text}
\"\"\"
"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        timeout=30,  # Set a timeout to avoid long waits
    )

    content = response.choices[0].message.content.strip()

    if not content or "can't assist" in content.lower():
        raise ValueError(f"OpenAI refused the request.\nResponse: {content}")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON returned by OpenAI.\nResponse: {content}")

def generate_action_recommendations(grouped_minutes: dict) -> dict:
    action_recommendations = {}
    for speaker, content in grouped_minutes.items():
        speaker_actions = []
        for contribution in content["contributions"]:
            try:
                result = extract_action_items(contribution)
                speaker_actions.append(result)
            except Exception as e:
                speaker_actions.append({
                    "error": str(e),
                    "input": contribution
                })
        action_recommendations[speaker] = {
            "topics": content["topics"],
            "timestamps": content["timestamps"],
            "actions": speaker_actions
        }
    return action_recommendations
