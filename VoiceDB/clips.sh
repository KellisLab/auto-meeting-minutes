#!/usr/bin/env bash
set -euo pipefail

# Usage check
if [ $# -ne 2 ]; then
  echo "Usage: $0 <input_video.mp4> <segments.csv>"
  exit 1
fi

INPUT="$1"
CSV="$2"

# Validate files
[ -f "$INPUT" ] || { echo "Input video not found: $INPUT"; exit 1; }
[ -f "$CSV" ]   || { echo "CSV file not found: $CSV"; exit 1; }

mkdir -p clips

# Trim helper
trim() {
  sed -e 's/\r$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

# Skip header, read idx, spk, start, end
tail -n +2 "$CSV" | while IFS=, read -r idx spk start end; do
  idx=$(printf '%s' "${idx:-}" | trim)
  spk=$(printf '%s' "${spk:-}" | trim)
  start=$(printf '%s' "${start:-}" | trim)
  end=$(printf '%s' "${end:-}" | trim)

  [ -n "$idx" ]   || { echo "SKIP: empty idx"; continue; }
  [ -n "$start" ] || { echo "SKIP: row $idx has empty start"; continue; }
  [ -n "$end" ]   || { echo "SKIP: row $idx has empty end"; continue; }

  # safe name
  safe_spk=$(printf '%s' "$spk" | tr ' ' '_' | tr -cd '[:alnum:]_.-')
  s_clean=$(printf '%s' "$start" | tr -d ':.')
  e_clean=$(printf '%s' "$end"   | tr -d ':.')
  out="clips/${idx}_${safe_spk}_${s_clean}_${e_clean}.wav"
  mkdir -p "$(dirname "$out")"

  echo "-> $out (${start}..${end}, spk=${spk})"

  ffmpeg -hide_banner -loglevel error -nostdin \
    -i "$INPUT" \
    -ss "$start" -to "$end" \
    -vn -ac 1 -ar 16000 -c:a pcm_s16le \
    -y "$out" \
    || echo "FFmpeg failed for $out"
done
