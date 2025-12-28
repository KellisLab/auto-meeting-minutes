#!/usr/bin/env python3
"""
cut_clips.py - Cut WAV clips from a video/audio file using a CSV with columns:
idx, spk, start, end (first row is a header)

Pipeline-friendly refactor:
- Adds an importable stage function: cut_clips(...)
- Keeps CLI support via main()
- Stage raises exceptions instead of sys.exit
- Optional checkpointing behavior (skip existing outputs unless overwrite)
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, Iterable


LOG = logging.getLogger(__name__)


# ----------------------------
# Helpers
# ----------------------------

def trim(s: str | None) -> str:
    if s is None:
        return ""
    return s.replace("\r", "").strip()


def safe_name(s: str) -> str:
    s = s.replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_.-]+", "", s)


def time_clean(s: str) -> str:
    return s.replace(":", "").replace(".", "")


@dataclass(frozen=True)
class Segment:
    idx: str
    spk: str
    start: str
    end: str


def read_segments(csv_path: Path) -> list[Segment]:
    """
    Reads segments from CSV. Expects header in first row.
    Columns: idx, spk, start, end (extra columns ignored).
    """
    segments: list[Segment] = []

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)

        header = next(reader, None)
        if header is None:
            return segments  # empty file

        for row_num, row in enumerate(reader, start=2):
            row = (row + ["", "", "", ""])[:4]
            idx, spk, start, end = (trim(x) for x in row)

            if not idx:
                LOG.warning("SKIP line %d: empty idx", row_num)
                continue
            if not start:
                LOG.warning("SKIP line %d (idx=%s): empty start", row_num, idx)
                continue
            if not end:
                LOG.warning("SKIP line %d (idx=%s): empty end", row_num, idx)
                continue

            segments.append(Segment(idx=idx, spk=spk, start=start, end=end))

    return segments


def segment_outpath(out_dir: Path, seg: Segment) -> Path:
    safe_spk = safe_name(seg.spk)
    s_clean = time_clean(seg.start)
    e_clean = time_clean(seg.end)
    return out_dir / f"{seg.idx}_{safe_spk}_{s_clean}_{e_clean}.wav"


def run_ffmpeg_cut(
    input_media: Path,
    seg: Segment,
    out_wav: Path,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
    overwrite: bool = True,
    dry_run: bool = False,
) -> None:
    """
    Runs ffmpeg to cut a single clip.
    Raises:
      FileNotFoundError if ffmpeg is missing
      subprocess.CalledProcessError if ffmpeg fails
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-i", str(input_media),
        "-ss", seg.start,
        "-to", seg.end,
        "-vn",
        "-ac", str(channels),
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
    ]

    if overwrite:
        cmd += ["-y"]
    else:
        cmd += ["-n"]

    cmd += [str(out_wav)]

    if dry_run:
        LOG.info("DRY_RUN ffmpeg: %s", " ".join(cmd))
        return

    subprocess.run(cmd, check=True)


# ----------------------------
# Pipeline-stage function
# ----------------------------

def cut_clips(
    input_media: Union[str, Path],
    segments_csv: Union[str, Path],
    out_dir: Union[str, Path] = "clips",
    *,
    limit: Optional[int] = None,
    sample_rate: int = 16000,
    channels: int = 1,
    overwrite: bool = False,
    dry_run: bool = False,
    skip_existing: bool = True,
) -> Path:
    """
    Pipeline-stage function.

    Args:
        input_media: path to .mp4/.m4a/.wav etc.
        segments_csv: CSV with header and columns idx,spk,start,end
        out_dir: output directory for clips
        limit: process only first N segments (useful for small-file tests)
        sample_rate: output WAV sample rate
        channels: output channels (1 = mono)
        overwrite: if True, overwrite existing outputs
        dry_run: if True, print commands but do not run ffmpeg
        skip_existing: if True and file exists, skip it (unless overwrite)

    Returns:
        Path to output directory containing clips.

    Raises:
        FileNotFoundError: if input_media or segments_csv missing, or ffmpeg missing
        RuntimeError: if all segments fail (optional strictness)
        subprocess.CalledProcessError: if ffmpeg fails and you choose not to catch it
    """
    input_path = Path(input_media)
    csv_path = Path(segments_csv)
    out_path = Path(out_dir)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input media not found: {input_path}")
    if not csv_path.is_file():
        raise FileNotFoundError(f"Segments CSV not found: {csv_path}")

    out_path.mkdir(parents=True, exist_ok=True)

    segments = read_segments(csv_path)
    if limit is not None:
        segments = segments[: max(0, limit)]

    ok = 0
    failed = 0

    for seg in segments:
        clip_path = segment_outpath(out_path, seg)
        clip_path.parent.mkdir(parents=True, exist_ok=True)

        if clip_path.exists() and skip_existing and not overwrite:
            LOG.info("SKIP exists: %s", clip_path)
            continue

        LOG.info("-> %s (%s..%s, spk=%s)", clip_path, seg.start, seg.end, seg.spk)

        try:
            run_ffmpeg_cut(
                input_media=input_path,
                seg=seg,
                out_wav=clip_path,
                sample_rate=sample_rate,
                channels=channels,
                overwrite=overwrite,
                dry_run=dry_run,
            )
            ok += 1
        except FileNotFoundError as e:
            # ffmpeg missing
            raise FileNotFoundError("ffmpeg not found. Install FFmpeg and ensure it's on your PATH.") from e
        except subprocess.CalledProcessError as e:
            failed += 1
            LOG.error("FFmpeg failed for %s (exit=%s)", clip_path, e.returncode)

    LOG.info("Cut clips done. ok=%d failed=%d out_dir=%s", ok, failed, out_path)
    return out_path


# ----------------------------
# CLI wrapper
# ----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Cut WAV clips from media using segments CSV.")
    ap.add_argument("input_media", help="Input media file (.mp4/.wav/...)")
    ap.add_argument("segments_csv", help="Segments CSV (idx,spk,start,end)")
    ap.add_argument("--out-dir", default="clips", help="Output directory (default: clips)")
    ap.add_argument("--limit", type=int, default=None, help="Process only first N segments")
    ap.add_argument("--sample-rate", type=int, default=16000, help="Output sample rate (default: 16000)")
    ap.add_argument("--channels", type=int, default=1, help="Output channels (default: 1)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    ap.add_argument("--dry-run", action="store_true", help="Print ffmpeg commands without running them")
    ap.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")

    try:
        out_dir = cut_clips(
            args.input_media,
            args.segments_csv,
            args.out_dir,
            limit=args.limit,
            sample_rate=args.sample_rate,
            channels=args.channels,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
        print(f"Clips written to: {out_dir}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
