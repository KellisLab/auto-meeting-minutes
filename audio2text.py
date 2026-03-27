import os 
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("API_KEY")
client = OpenAI()
audio_file= open("path", "rb") #To be changed to the path of the audio file

transcription = client.audio.transcriptions.create(
    model="gpt-4o-mini-transcribe", 
    file=audio_file
)

print(transcription.text)