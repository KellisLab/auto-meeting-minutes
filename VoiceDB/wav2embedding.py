"""Extracts embeddings from .wav files """

import os
import numpy as np
import torch
import pandas as pd
import soundfile as sf
from pathlib import Path
from scipy.signal import resample_poly
from transformers import AutoProcessor, Wav2Vec2Model

CLIPS_DIR = Path("/Users/sadhikakamchetty/Desktop/VoiceDB/clips")
OUT_DIR   = Path("/Users/sadhikakamchetty/Desktop/VoiceDB/embeds_w2v")
OUT_DIR.mkdir(parents=True, exist_ok=True)

rows = []

# ---------- audio loading ----------
def load_mono_16k_safe(path, target_sr=16000, min_len_sec=0.3):
    wav, sr = sf.read(path, dtype="float32", always_2d=True)  # [T, C]
    if wav.size == 0:
        raise ValueError(f"Empty audio: {path}")
    wav = wav[:, 0]  # first channel
    wav = np.nan_to_num(wav, nan=0.0, posinf=0.0, neginf=0.0)
    if sr != target_sr:
        g = np.gcd(sr, target_sr)
        up, down = target_sr // g, sr // g
        wav = resample_poly(wav, up, down)
        sr = target_sr
    # pad very short clips (protect conv kernel)
    min_len = int(min_len_sec * target_sr)
    if wav.shape[0] < min_len:
        wav = np.pad(wav, (0, min_len - wav.shape[0]))
    return wav, sr

# ---------- model (cached globals so you don't reload each call) ----------
_W2V_ID = "facebook/wav2vec2-base"
_processor = AutoProcessor.from_pretrained(_W2V_ID)
_model = Wav2Vec2Model.from_pretrained(_W2V_ID).eval().to(
    "cuda" if torch.cuda.is_available() else "cpu"
)

def wav2vec_embed(path: str,
                  model_id: str = _W2V_ID,
                  target_sr: int = 16000,
                  layer: int = -1) -> torch.Tensor:
    wav, _ = load_mono_16k_safe(path, target_sr=target_sr)
    inputs = _processor(wav, sampling_rate=target_sr, return_tensors="pt")
    inputs = {k: v.to(_model.device) for k, v in inputs.items()}
    with torch.inference_mode():
        out = _model(**inputs, output_hidden_states=True)
    emb = out.hidden_states[layer].mean(dim=1).squeeze(0)  # [H]
    return emb  # on _model.device

# ---------- helpers ----------
def parse_name(path: str) -> str:
    base = os.path.basename(path)
    stem, _ = os.path.splitext(base)
    parts = stem.split("_")  # idx_Name_With_Underscores_start_end
    return "_".join(parts[1:-2]) if len(parts) >= 4 else stem

def l2norm(x: torch.Tensor) -> torch.Tensor:
    return x / (x.norm(p=2) + 1e-12)

def save_embedding(vec: torch.Tensor, wav_path: str, out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    npy = out / f"{Path(wav_path).stem}.npy"
    np.save(npy, vec.detach().cpu().numpy())
    return {
        "file": wav_path,
        "speaker": parse_name(wav_path),
        "embedding_path": str(npy),
        "dim": int(vec.numel()),
    }


for wav_file in sorted(CLIPS_DIR.glob("*.wav")):
    try:
        print(f"Processing: {wav_file}")

        # Get embedding
        vec = wav2vec_embed(str(wav_file))
        vec = l2norm(vec)

        # Save vector + metadata row
        row = save_embedding(vec, str(wav_file), str(OUT_DIR))
        rows.append(row)

    except Exception as e:
        print(f"⚠️ Skipping {wav_file} due to error: {e}")


df = pd.DataFrame(rows)
df.to_parquet(OUT_DIR / "index.parquet", index=False)

print(f"✅ Done. Saved {len(rows)} embeddings to {OUT_DIR}")

# wav_path = "/Users/sadhikakamchetty/Desktop/VoiceDB/clips/576_Hongning_Wang_010450_010509.wav"
# vec = wav2vec_embed(wav_path)
# vec = l2norm(vec)  # normalize for cosine similarity
# row = save_embedding(vec, wav_path, "/Users/sadhikakamchetty/Desktop/VoiceDB/embeds_w2v")
# print(row)

