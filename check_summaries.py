#!/usr/bin/env python3
"""
check_summaries.py - List generated summaries that contain leaked model reasoning.

Walks one or more output trees (*_meeting_summaries.md/.html,
*_speaker_summaries.md/.html) and prints every file whose text carries
deliberation or prompt-echo, i.e. the meetings to re-run. Exit code 1 when any
file is flagged, so it can gate a publish step.

    python check_summaries.py /opt/data/amm-output
    python check_summaries.py --since 2026-08-28 --paths-only out/ | xargs ...
"""

import argparse
import os
import re
import sys
from datetime import datetime

from llm_output import deliberation_markers

_TAG_RE = re.compile(r"<[^>]+>")
_NAME_RE = re.compile(r"_(?:meeting|speaker)_summaries\.(?:md|html)$")
_DATE_RE = re.compile(r"(\d{4})[.\-_](\d{2})[.\-_](\d{2})")

# Pieces of the prompt or of the structured-reply scaffold that only appear in
# a summary when the model's scratchpad was published.
_ECHO_RE = re.compile(
    r"PRIMARY_SPEAKER:|\[Brief descriptive title|\[Detailed summary in|"
    r"SPEAKER TIMESTAMPS|NON-NEGOTIABLE GUARDRAILS|Key points from the transcript",
)


def findings(text):
    """Distinct leak evidence in one summary file."""
    plain = _TAG_RE.sub(" ", text)
    return deliberation_markers(plain) + sorted({m.group(0) for m in _ECHO_RE.finditer(plain)})


def file_date(path):
    """Meeting date from the file name (YYYY.MM.DD), else the file's mtime."""
    m = _DATE_RE.search(os.path.basename(path))
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    return datetime.fromtimestamp(os.path.getmtime(path))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+", help="output directories or files to check")
    ap.add_argument("--since", help="only meetings on or after YYYY-MM-DD")
    ap.add_argument("--paths-only", action="store_true", help="print flagged paths only")
    args = ap.parse_args()
    since = datetime.strptime(args.since, "%Y-%m-%d") if args.since else None

    paths = []
    for root in args.roots:
        if os.path.isfile(root):
            paths.append(root)
        for folder, _, names in os.walk(root):
            paths.extend(os.path.join(folder, n) for n in names if _NAME_RE.search(n))

    checked = flagged = 0
    for path in sorted(paths):
        if since and file_date(path) < since:
            continue
        checked += 1
        with open(path, encoding="utf-8", errors="replace") as fh:
            found = findings(fh.read())
        if found:
            flagged += 1
            print(path if args.paths_only else f"{path}\n    {', '.join(found[:6])}")
    if not args.paths_only:
        print(f"\n{flagged} of {checked} summary files contain leaked reasoning", file=sys.stderr)
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
