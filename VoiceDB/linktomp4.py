"""
Converts panopto to mp4 for usage of models """
#!/usr/bin/env python3
import re
import sys
import argparse
import requests
from urllib.parse import urlparse, parse_qs
from pathlib import Path

PANOPTO_HOST = "mit.hosted.panopto.com"

def url_or_id_to_guid32(s: str) -> str:
    """
    Accepts either:
      - a Panopto Viewer URL like ...Viewer.aspx?id=27437355-590c-4635-ab48-b37a014f764e
      - or a GUID with/without hyphens
    Returns the 32-char lowercase GUID (no hyphens).
    """
    # If it's a URL, pull ?id=...
    if s.startswith("http"):
        q = parse_qs(urlparse(s).query)
        gid = q.get("id", [None])[0]
        if not gid:
            raise ValueError("No ?id=... found in the URL")
    else:
        gid = s

    # Validate and strip hyphens
    m = re.fullmatch(r"[0-9a-fA-F\-]{32,36}", gid)
    if not m:
        raise ValueError(f"Not a valid Panopto GUID: {gid}")
    return gid.replace("-", "").lower()

def download_podcast_mp4(guid32: str, output_file: Path) -> bool:
    """
    Downloads the Panopto podcast MP4 for a given 32-char GUID (no hyphens).
    Note: You may need to be authenticated for private sessions.
    """
    podcast_url = f"https://{PANOPTO_HOST}/Panopto/Podcast/Download/{guid32}.mp4"
    try:
        with requests.Session() as s:
            # Basic UA helps avoid some blocked requests
            headers = {"User-Agent": "Mozilla/5.0"}
            r = s.get(podcast_url, headers=headers, stream=True, allow_redirects=True, timeout=60)

            if r.status_code != 200:
                print(f"Error: download failed (HTTP {r.status_code}) from {podcast_url}", file=sys.stderr)
                return False

            # write to disk
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            print(f"Saved: {output_file}")
            return True
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False

def main():
    ap = argparse.ArgumentParser(description="Download Panopto podcast MP4 by Viewer URL or GUID.")
    ap.add_argument("url_or_id", help="Viewer URL with ?id=... or the GUID (with/without hyphens)")
    ap.add_argument("-o", "--output", help="Output file path (default: ./podcast.mp4)", default="podcast.mp4")
    args = ap.parse_args()

    guid32 = url_or_id_to_guid32(args.url_or_id)
    out = Path(args.output)
    ok = download_podcast_mp4(guid32, out)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
