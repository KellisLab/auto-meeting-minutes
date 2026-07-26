"""Convert a timestamped transcript text file into a CSV with columns: idx, spk, start, end."""
#!/usr/bin/env python3
import sys, re, csv, argparse
from pathlib import Path

LINE_RE = re.compile(r'^(?P<start>\d{2}:\d{2}:\d{2})\s+(?P<spk>[^:]+):')

def parse_lines(text):
    rows = []
    for i, raw in enumerate(text.splitlines()):
        m = LINE_RE.match(raw.strip())
        if not m:
            continue  # skip non-dialog lines
        rows.append({
            "idx": i,  # temporary; we'll renumber later
            "spk": m.group("spk").strip(),
            "start": m.group("start").strip(),
        })
    # renumber idx compactly
    for j, r in enumerate(rows):
        r["idx"] = j
    return rows

def assign_ends(rows, last_end=None):
    for i in range(len(rows)):
        if i < len(rows) - 1:
            rows[i]["end"] = rows[i+1]["start"]
        else:
            rows[i]["end"] = last_end if last_end else ""
    return rows

def main():
    ap = argparse.ArgumentParser(description="Convert timestamped transcript to idx,spk,start,end CSV.")
    ap.add_argument("input", help="Transcript file (text). Use '-' to read stdin.")
    ap.add_argument("-o", "--output", help="Output CSV path (default: stdout).")
    ap.add_argument("--last-end", help="End time for the final row (e.g. 01:12:34). If omitted, left blank.")
    args = ap.parse_args()

    text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8", errors="ignore")

    rows = parse_lines(text)
    rows = assign_ends(rows, last_end=args.last_end)

    outfh = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    with outfh:
        w = csv.writer(outfh)
        w.writerow(["idx", "spk", "start", "end"])
        for r in rows:
            w.writerow([r["idx"], r["spk"], r["start"], r["end"]])

if __name__ == "__main__":
    main()
