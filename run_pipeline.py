import subprocess
import sys
import time
from pathlib import Path

# === CONFIG ===
PANOPTO_URL = sys.argv[1] if len(sys.argv) > 1 else None
MEETING_DIR = Path("output")  # This must match MEETING_ROOT_DIR in your .env
TIMEOUT_SECONDS = 60
PARSER_PATH = "parser.py"

if not PANOPTO_URL:
    print("Usage: python run_pipeline.py <panopto_url>")
    sys.exit(1)

# === STEP 1: Run fullpipeline.py ===
print(f"[+] Running fullpipeline on: {PANOPTO_URL}")
subprocess.run(["python", "fullpipeline.py", PANOPTO_URL], check=True)

# === STEP 2: Wait for .md file to be generated ===
print("[+] Waiting for .md output...")
start_time = time.time()
md_file = None

while time.time() - start_time < TIMEOUT_SECONDS:
    md_files = list(MEETING_DIR.glob("*.md"))
    if md_files:
        md_file = md_files[0]
        print(f"[+] Found .md file: {md_file}")
        break
    time.sleep(2)

if not md_file:
    print("[-] .md file not found in time.")
    sys.exit(1)

# === STEP 3: Run parser.py on the .md file ===
print(f"[+] Parsing .md file: {md_file}")
subprocess.run(["python", PARSER_PATH, str(md_file)], check=True)

# === STEP 4: Send calendar invites (assumes send_payloads.py exists) ===
print("[+] Sending calendar payloads...")
subprocess.run(["python", "send_payloads.py"], check=True)
