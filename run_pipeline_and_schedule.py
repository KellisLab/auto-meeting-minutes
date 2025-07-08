import os
import subprocess
from dotenv import load_dotenv
from pathlib import Path
import sys

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

# === Step 0: Choose Input Source ===
USE_TEST_MD = False  # <<< SET THIS TO False if using Panopto URL and to true if using a raw file

if USE_TEST_MD:
    # Step 1: Use local test.md (for testing without Panopto)
    test_md_path = Path("input/test.md").resolve()
    if not test_md_path.exists():
        raise FileNotFoundError(f"Test markdown file not found: {test_md_path}")
    subprocess.run(["python", "parser.py", str(test_md_path)])
else:
    # Step 1: Full Panopto pipeline
    panopto_url = "https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=901bf468-a000-42f6-a8bf-b2cf016e342d"
    subprocess.run(["python", "fullpipeline.py", panopto_url])
    subprocess.run(["python", "generate_meeting_payloads.py"])

# === Step 2: Run payload sender ===
subprocess.run(["python", "send_payloads.py"])
