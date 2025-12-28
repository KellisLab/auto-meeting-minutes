#!/usr/bin/env python3
"""
Convert a timestamped transcript text file into a CSV with columns: idx, spk, start, end.

Refactor goals:
- Keep your existing parsing logic
- Add an importable pipeline-stage function: transcript2csv(...)
- Keep CLI support via main()
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union


# Matches lines like: "00:12:34 Speaker Name: ..."
LINE_RE = re.compile(r"^(?P<start>\d{2}:\d{2}:\d{2})\s+(?P<spk>[^:]+):")


@dataclass
class Row:
    idx: int
    spk: str
    start: str
    end: str = ""


def parse_lines(text: str) -> list[Row]:
    """
    Extract rows with (idx, spk, start) from transcript lines.
    idx is compactly renumbered (0..k-1) based on matched dialog lines only.
    """
    rows: list[Row] = []
    for _, raw in enumerate(text.splitlines()):
        m = LINE_RE.match(raw.strip())
        if not m:
            continue  # skip non-dialog lines
        rows.append(
            Row(
                idx=0,  # temp; renumbered below
                spk=m.group("spk").strip(),
                start=m.group("start").strip(),
            )
        )

    # Renumber idx compactly
    for j, r in enumerate(rows):
        r.idx = j
    return rows


def assign_ends(rows: list[Row], last_end: Optional[str] = None) -> list[Row]:
    """
    Assign end timestamps:
    - end of row i = start of row i+1
    - last row end = last_end if provided, else blank
    """
    for i in range(len(rows)):
        if i < len(rows) - 1:
            rows[i].end = rows[i + 1].start
        else:
            rows[i].end = last_end or ""
    return rows


def write_csv(rows: Iterable[Row], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["idx", "spk", "start", "end"])
        for r in rows:
            w.writerow([r.idx, r.spk, r.start, r.end])
    return out_path

def transcript2csv(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    *,
    last_end: Optional[str] = None,
    encoding: str = "utf-8",
) -> Path:
    in_path = Path(input_path)
    out_path = Path(output_path)
    text = in_path.read_text(encoding=encoding)
    rows = parse_lines(text)
    rows = assign_ends(rows, last_end=last_end)

    return write_csv(rows, out_path)

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert timestamped transcript to idx,spk,start,end CSV."
    )
    ap.add_argument("input", help="Transcript file (text). Use '-' to read stdin.")
    ap.add_argument(
        "-o",
        "--output",
        help="Output CSV path (default: stdout).",
    )
    ap.add_argument(
        "--last-end",
        help="End time for the final row (e.g. 01:12:34). If omitted, left blank.",
    )
    args = ap.parse_args()

    # CLI behavior preserved:
    # - if input is '-', read from stdin
    # - if output is omitted, write to stdout
    if args.input == "-":
        text = sys.stdin.read()
        rows = assign_ends(parse_lines(text), last_end=args.last_end)

        if args.output:
            write_csv(rows, Path(args.output))
        else:
            w = csv.writer(sys.stdout)
            w.writerow(["idx", "spk", "start", "end"])
            for r in rows:
                w.writerow([r.idx, r.spk, r.start, r.end])
        return

    # Standard path-based call
    if args.output:
        transcript2csv(args.input, args.output, last_end=args.last_end)
    else:
        # If no output path, mimic old behavior: write to stdout
        in_path = Path(args.input)
        text = in_path.read_text(encoding="utf-8", errors="ignore")
        rows = assign_ends(parse_lines(text), last_end=args.last_end)

        w = csv.writer(sys.stdout)
        w.writerow(["idx", "spk", "start", "end"])
        for r in rows:
            w.writerow([r.idx, r.spk, r.start, r.end])


if __name__ == "__main__":
    main()