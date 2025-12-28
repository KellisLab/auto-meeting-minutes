#!/usr/bin/env python3
"""
url2file.py - Download Panopto video transcript (SRT) from a Viewer URL.

Pipeline-friendly refactor:
- Adds an importable stage function: url2srt(...)
- Keeps CLI support via main()
- No prompts / sys.exit inside the stage function
- Deterministic outputs + optional skip-if-exists
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Optional, Union

import requests


LOG = logging.getLogger(__name__)

# Pattern to match Panopto video ID in the URL
ID_RE = re.compile(
    r"id=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def extract_id_from_url(url: str) -> Optional[str]:
    """
    Extract Panopto video ID from a URL.

    Returns:
        video_id if found, else None
    """
    m = ID_RE.search(url)
    return m.group(1) if m else None


def _transcript_url(video_id: str, language: str) -> str:
    return (
        "https://mit.hosted.panopto.com/Panopto/Pages/Transcription/GenerateSRT.ashx"
        f"?id={video_id}&language={language}"
    )


def download_transcript_bytes(
    video_id: str,
    *,
    language: str = "English_USA",
    timeout_s: int = 60,
    session: Optional[requests.Session] = None,
) -> bytes:
    """
    Download transcript content as bytes.
    Raises requests.HTTPError on non-200 responses.
    """
    url = _transcript_url(video_id, language)
    sess = session or requests.Session()

    resp = sess.get(url, timeout=timeout_s)
    resp.raise_for_status()
    return resp.content


def url2srt(
    url: str,
    output_path: Union[str, Path, None] = None,
    *,
    language: str = "English_USA",
    overwrite: bool = False,
    timeout_s: int = 60,
) -> Path:
    """
    Pipeline-stage function.

    Args:
        url: Panopto viewer URL containing ?id=<uuid>
        output_path: where to write the .srt. If None, uses "<video_id>.srt" in CWD.
        language: Panopto language code (default: English_USA)
        overwrite: if False and output exists, skip download and return existing path
        timeout_s: network timeout seconds

    Returns:
        Path to the .srt file on disk

    Raises:
        ValueError: if URL doesn't contain a video id
        requests.HTTPError: if Panopto returns a non-200 response
        OSError: if writing fails
    """
    video_id = extract_id_from_url(url)
    if not video_id:
        raise ValueError("No valid Panopto video ID found in the URL")

    out = Path(output_path) if output_path is not None else Path(f"{video_id}.srt")
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists() and not overwrite:
        LOG.info("SRT exists, skipping download: %s", out)
        return out

    LOG.info("Downloading transcript: id=%s lang=%s -> %s", video_id, language, out)

    content = download_transcript_bytes(video_id, language=language, timeout_s=timeout_s)

    # Write bytes exactly (SRT may contain non-utf8 chars sometimes)
    out.write_bytes(content)

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Panopto video transcript (SRT) from a URL"
    )
    parser.add_argument("url", nargs="?", help="Panopto video URL")
    parser.add_argument("output_file", nargs="?", help="Output file path (optional)")
    parser.add_argument(
        "--language",
        default="English_USA",
        help="Language code for transcript (default: English_USA)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output if it exists",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Network timeout seconds (default: 60)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(message)s",
    )

    # CLI-only behavior: prompt if URL not provided
    url = args.url or input("Enter Panopto video URL: ").strip()
    out_path = args.output_file

    try:
        srt_path = url2srt(
            url,
            output_path=out_path,
            language=args.language,
            overwrite=args.overwrite,
            timeout_s=args.timeout,
        )
        print(f"Transcript downloaded to {srt_path}")
    except Exception as e:
        # CLI prints a friendly message; pipeline code would let exception bubble up
        print(f"Failed to download transcript: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
