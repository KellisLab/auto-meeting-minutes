#!/usr/bin/env python3
"""
wav2embeddings.py - Extract embeddings from .wav clips and write:
- one .npy per wav
- index.parquet with metadata

Pipeline-friendly refactor:
- Adds an importable stage function: extract_embeddings(...)
- Keeps CLI support
- Does not run work at import time
- Lazy-loads wav2vec model/processor
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd
import soundfile as sf
import torch
from scipy.signal import resample_poly
from transformers import AutoProcessor, Wav2Vec2Model


LOG = logging.getLogger(__name__)


# ----------------------------
# Audio loading
# ----------------------------

def load_mono_16k_safe(path: Union[str, Path], target_sr: int = 16000, min_len_sec: float = 0.3):
    path = Path(path)
    wav, sr = sf.read(path, dtype="float32", always_2d=True)  # [T, C]
    if wav.size == 0:
        raise ValueError(f"Empty audio: {path}")

    wav = wav[:, 0]  # take first channel
    wav = np.nan_to_num(wav, nan=0.0, posinf=0.0, neginf=0.0)

    if sr != target_sr:
        g = np.gcd(sr, target_sr)
        up, down = target_sr // g, sr // g
        wav = resample_poly(wav, up, down)
        sr = target_sr

    min_len = int(min_len_sec * target_sr)
    if wav.shape[0] < min_len:
        wav = np.pad(wav, (0, min_len - wav.shape[0]))

    return wav, sr


# ----------------------------
# Model cache (lazy)
# ----------------------------

@dataclass
class _W2VBundle:
    processor: AutoProcessor
    model: Wav2Vec2Model
    device: torch.device


_W2V_CACHE: dict[str, _W2VBundle] = {}


def get_wav2vec_bundle(model_id: str, device: Optional[str] = None) -> _W2VBundle:
    """
    Lazy-load and cache processor+model so importing this module doesn't download weights.
    """
    if model_id in _W2V_CACHE:
        return _W2V_CACHE[model_id]

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    dev = torch.device(device)
    processor = AutoProcessor.from_pretrained(model_id)
    model = Wav2Vec2Model.from_pretrained(model_id).eval().to(dev)

    bundle = _W2VBundle(processor=processor, model=model, device=dev)
    _W2V_CACHE[model_id] = bundle
    return bundle


def wav2vec_embed(
    wav_path: Union[str, Path],
    *,
    model_id: str,
    target_sr: int = 16000,
    layer: int = -1,
    device: Optional[str] = None,
) -> torch.Tensor:
    """
    Returns a single embedding vector [H] on the model device.
    """
    bundle = get_wav2vec_bundle(model_id, device=device)

    wav, _ = load_mono_16k_safe(wav_path, target_sr=target_sr)
    inputs = bundle.processor(wav, sampling_rate=target_sr, return_tensors="pt")
    inputs = {k: v.to(bundle.device) for k, v in inputs.items()}

    with torch.inference_mode():
        out = bundle.model(**inputs, output_hidden_states=True)

    emb = out.hidden_states[layer].mean(dim=1).squeeze(0)  # [H]
    return emb


# ----------------------------
# Helpers
# ----------------------------

def parse_name(wav_path: Union[str, Path]) -> str:
    """
    Assumes filename format:
      idx_Name_With_Underscores_start_end.wav
    """
    base = Path(wav_path).name
    stem = Path(base).stem
    parts = stem.split("_")
    return "_".join(parts[1:-2]) if len(parts) >= 4 else stem


def l2norm(x: torch.Tensor) -> torch.Tensor:
    return x / (x.norm(p=2) + 1e-12)


def save_embedding(vec: torch.Tensor, wav_path: Union[str, Path], out_dir: Union[str, Path]) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    wav_path = Path(wav_path)
    npy = out / f"{wav_path.stem}.npy"
    np.save(npy, vec.detach().cpu().numpy())

    return {
        "file": str(wav_path),
        "speaker": parse_name(wav_path),
        "embedding_path": str(npy),
        "dim": int(vec.numel()),
    }


# ----------------------------
# Pipeline-stage function
# ----------------------------

def extract_embeddings(
    clips_dir: Union[str, Path],
    out_dir: Union[str, Path],
    *,
    model_id: str = "facebook/wav2vec2-base",
    target_sr: int = 16000,
    layer: int = -1,
    device: Optional[str] = None,
    limit: Optional[int] = None,
    overwrite: bool = False,
    index_name: str = "index.parquet",
) -> Path:
    """
    Pipeline-stage function.

    Inputs:
      clips_dir: directory containing *.wav
      out_dir: where to write *.npy and index.parquet

    Output:
      out_dir (Path). Writes index parquet into out_dir.
    """
    clips_dir = Path(clips_dir)
    out_dir = Path(out_dir)

    if not clips_dir.is_dir():
        raise FileNotFoundError(f"CLIPS_DIR not found or not a directory: {clips_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)

    wav_files = sorted(clips_dir.glob("*.wav"))
    if limit is not None:
        wav_files = wav_files[: max(0, limit)]

    rows: list[dict] = []
    skipped = 0

    for wav_file in wav_files:
        try:
            npy_path = out_dir / f"{wav_file.stem}.npy"
            if npy_path.exists() and not overwrite:
                LOG.info("SKIP exists: %s", npy_path)
                rows.append({
                    "file": str(wav_file),
                    "speaker": parse_name(wav_file),
                    "embedding_path": str(npy_path),
                    "dim": int(np.load(npy_path, mmap_mode="r").shape[0]),
                })
                continue

            LOG.info("Processing: %s", wav_file)

            vec = wav2vec_embed(
                wav_file,
                model_id=model_id,
                target_sr=target_sr,
                layer=layer,
                device=device,
            )
            vec = l2norm(vec)

            row = save_embedding(vec, wav_file, out_dir)
            rows.append(row)

        except Exception as e:
            skipped += 1
            LOG.warning("Skipping %s due to error: %s", wav_file, e)

    df = pd.DataFrame(rows)
    index_path = out_dir / index_name
    df.to_parquet(index_path, index=False)

    LOG.info("Done. Saved %d embeddings to %s (skipped=%d). Index: %s",
             len(rows), out_dir, skipped, index_path)

    return out_dir


# ----------------------------
# CLI wrapper
# ----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Extract wav2vec2 embeddings from .wav clips.")
    ap.add_argument("--clips-dir", default=os.getenv("CLIPS_DIR", ""), help="Directory with .wav clips")
    ap.add_argument("--out-dir", default=os.getenv("OUT_DIR", ""), help="Output directory for embeddings + index")
    ap.add_argument("--model-id", default="facebook/wav2vec2-base")
    ap.add_argument("--layer", type=int, default=-1)
    ap.add_argument("--target-sr", type=int, default=16000)
    ap.add_argument("--device", default=None, help="cpu | cuda | cuda:0 etc (default auto)")
    ap.add_argument("--limit", type=int, default=None, help="Process only first N wavs (small-file test)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing .npy files")
    ap.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")

    if not args.clips_dir:
        raise SystemExit("Error: --clips-dir not provided (and CLIPS_DIR env var is empty).")
    if not args.out_dir:
        raise SystemExit("Error: --out-dir not provided (and OUT_DIR env var is empty).")

    extract_embeddings(
        clips_dir=args.clips_dir,
        out_dir=args.out_dir,
        model_id=args.model_id,
        target_sr=args.target_sr,
        layer=args.layer,
        device=args.device,
        limit=args.limit,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()

