import subprocess
from pathlib import Path

# === Hardcoded Panopto URL ===
PANOPTO_URL = "https://mit.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=901bf468-a000-42f6-a8bf-b2cf016e342d"

# === Define paths ===
MINUTES_JSON_PATH = Path("Email Integration/minutesToJson.py")
OTHER_SCRIPTS = [
    "Email Integration/github_Auth.py",
    "Email Integration/gpt_recommendations.py",
    "Email Integration/contextual_enrichment.py",
    "Email Integration/cursor.py"
]

def run_script(script_path, args=None):
    print(f"\n🔧 Running: {script_path}")
    command = ["python", str(script_path)]
    if args:
        command.extend(args)
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print("🟩 STDOUT:\n", result.stdout or "(empty)")
        if result.stderr:
            print("🟥 STDERR:\n", result.stderr)
    except Exception as e:
        print(f"❌ Error running {script_path}: {e}")

def main():
    # 1. Run minutesToJson.py — pass Panopto URL as argument
    if MINUTES_JSON_PATH.exists():
        run_script(MINUTES_JSON_PATH, args=[PANOPTO_URL])
    else:
        print(f"⚠️ Skipped (not found): {MINUTES_JSON_PATH}")

    # 2. Run other post-processing scripts
    for script in OTHER_SCRIPTS:
        path = Path(script)
        if path.exists():
            run_script(path)
        else:
            print(f"⚠️ Skipped (not found): {script}")

if __name__ == "__main__":
    main()
