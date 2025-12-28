"""
Download ONE Panopto video via yt-dlp.
Usage examples:
  python download.py --url "https://....id=XXXX"
  # or let it read PANOPTO_URL from .env
"""

import os
import re
import subprocess
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ID_RE = re.compile(r"id=([a-f0-9\-]+)", re.IGNORECASE)

def download_media(url: str, download_dir: str) -> str:
    Path(download_dir).mkdir(parents=True, exist_ok=True)

    m = ID_RE.search(url)
    if not m:
        raise ValueError(f"No video ID found in URL: {url}")

    video_id = m.group(1)
    out_path = os.path.join(download_dir, f"{video_id}.mp4")

    print(f"Downloading:\n  {url}\n  -> {out_path}")

    subprocess.run(
        ["yt-dlp", "-o", out_path, url],
        check=True
    )

    print("Done for f{video_id}")
    return out_path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.getenv("PANOPTO_URL"), help="Single Panopto URL (or set PANOPTO_URL in .env)")
    p.add_argument("--download-dir", default=os.getenv("DOWNLOAD_DIRECTORY", "downloads"))
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    if not args.url:
        raise RuntimeError("Provide --url or set PANOPTO_URL in your .env")
    download_media(args.url, args.download_dir)
