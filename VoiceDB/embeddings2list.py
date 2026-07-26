import os
import pickle
import numpy as np

def l2norm(x, axis=-1, eps=1e-9):
    n = np.linalg.norm(x, axis=axis, keepdims=True)
    return x / np.clip(n, eps, None)

def coerce_to_2d(emb):
    """
    Returns a 2-D array of shape (N, D).
    Accepts:
      - 1-D array (D,)  -> (1, D)
      - 2-D array (N,D) -> unchanged
      - list/tuple of 1-D arrays -> stack to (N, D)
    """
    if isinstance(emb, (list, tuple)):
        emb = np.stack(emb, axis=0)              # (N, D)
    emb = np.asarray(emb)
    if emb.ndim == 1:
        emb = emb[None, :]                       # (1, D)
    if emb.ndim != 2:
        raise ValueError(f"Expected 1D/2D or list-of-1D, got shape {emb.shape}")
    return emb

def mean_emb_of_file(path):
    raw = np.load(path, allow_pickle=True)       # allow_pickle for list-like saves
    M = coerce_to_2d(raw)                        # (N, D)
    M = l2norm(M, axis=1)                        # normalize each row first
    mean = M.mean(axis=0)
    mean = l2norm(mean)                          # normalize final centroid
    return mean.astype(np.float32)

def extract_name_from_filename(fname):
    parts = fname.split("_")
    # example: "1_Manolis_Kellis_000016_000029.npy" -> Manolis_Kellis
    if len(parts) >= 4 and parts[-1].endswith(".npy"):
        return "_".join(parts[1:-2])
    # fallback: strip extension only
    return os.path.splitext(fname)[0]

def build_speaker_db(emb_dir, out_pkl, out_npz=None):
    speaker_vectors = {}
    for f in os.listdir(emb_dir):
        if not f.endswith(".npy"):
            continue
        path = os.path.join(emb_dir, f)
        name = extract_name_from_filename(f)
        vec = mean_emb_of_file(path)             # (D,)
        # if multiple files per same speaker, average incrementally
        if name in speaker_vectors:
            prev = speaker_vectors[name]
            vec = l2norm((prev + vec) / 2.0)     # simple running average
        speaker_vectors[name] = vec

    # save as pickle (dict: name -> np.ndarray)
    with open(out_pkl, "wb") as fh:
        pickle.dump(speaker_vectors, fh)

    # optional: also save a compact NPZ (names + matrix) for FAISS/etc.
    if out_npz:
        names = np.array(list(speaker_vectors.keys()), dtype=object)
        mat = np.stack([speaker_vectors[n] for n in names], axis=0)
        np.savez(out_npz, names=names, embeddings=mat)

    print(f"Saved {len(speaker_vectors)} speakers to:\n  {out_pkl}"
          + (f"\n  {out_npz}" if out_npz else ""))

# ---- run it ----
EMB_DIR = "/Users/sadhikakamchetty/Desktop/VoiceDB/embeds_w2v"  # <- change if needed
OUT_PKL = "/Users/sadhikakamchetty/Desktop/VoiceDB/speaker_db.pkl"
OUT_NPZ = "/Users/sadhikakamchetty/Desktop/VoiceDB/speaker_db.npz"

build_speaker_db(EMB_DIR, OUT_PKL, OUT_NPZ)


import pickle, numpy as np
from numpy.linalg import norm

db = pickle.load(open("/Users/sadhikakamchetty/Desktop/VoiceDB/speaker_db.pkl","rb"))
names = list(db.keys())
print("Speakers:", names[:5], "…", len(names))
print("Dim:", db[names[0]].shape)

def cos(a,b): return float(np.dot(a,b)/(norm(a)*norm(b)))
print("Self-sim:", cos(db[names[0]], db[names[0]]))
