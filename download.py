"""
Script to download Panopto videos listed in an Excel file using yt-dlp."""


import os
import re
import pandas as pd
import subprocess
from dotenv import load_dotenv
load_dotenv()

def download_media():
    # Load environment variables
    excel_path = os.getenv("EXCEL_PATH")
    download_dir = os.getenv("DOWNLOAD_DIRECTORY")
    os.makedirs(download_dir, exist_ok=True)

    # Read Excel and take the first column as URLs
    df = pd.read_excel(excel_path)
    urls = df.iloc[:, 0].dropna().tolist()

    print(f"Found {len(urls)} URLs")

    # Regex to extract Panopto ID
    ID_RE = re.compile(r"id=([a-f0-9\-]+)", re.IGNORECASE)

    for i, url in enumerate(urls, start=1):
        m = ID_RE.search(url)
        if not m:
            print(f"\n[{i}] ❌ No video ID found in URL: {url}")
            continue

        video_id = m.group(1)
        out_path = os.path.join(download_dir, f"{video_id}.mp4")

        print(f"\n[{i}/{len(urls)}] Downloading:\n  {url}\n  -> {out_path}")

        try:
            subprocess.run(
                ["yt-dlp", "-o", out_path, url],
                check=True
            )
            print("  ✓ Done")
        except subprocess.CalledProcessError as e:
            print("  ❌ Failed:", e)
