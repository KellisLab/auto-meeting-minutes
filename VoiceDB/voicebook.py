import numpy as np
from pathlib import Path
from collections import defaultdict

def l2norm(x): 
    n = np.linalg.norm(x)
    return x if n == 0 else x / n

def cosine_sim(a, b): 
    return np.dot(a, b)

def robust_centroid(embs, outlier_drop=0.15):
    """L2-normalize -> remove outliers by median similarity -> mean -> L2-normalize."""
    E = np.array([l2norm(e) for e in embs], dtype=np.float32)
    if len(E) == 1:
        return l2norm(E[0]), np.arange(len(E))  # nothing to filter

    # compute similarity to provisional mean
    proto = l2norm(E.mean(axis=0))
    sims = E @ proto
    # keep the top (1 - outlier_drop) by similarity
    k = max(1, int(round((1 - outlier_drop) * len(E))))
    keep_idx = np.argsort(sims)[-k:]
    centroid = l2norm(E[keep_idx].mean(axis=0))
    return centroid, keep_idx

def incremental_update(old_centroid, old_count, new_embs):
    """Update centroid without recomputing from all history."""
    new_normed = np.array([l2norm(e) for e in new_embs], dtype=np.float32)
    total = old_count + len(new_normed)
    updated = l2norm((old_centroid * old_count + new_normed.sum(axis=0)) / total)
    return updated, total

# --- Example: load *.npy files organized as data/<person_id>/*.npy ---
from collections import defaultdict
import numpy as np
from pathlib import Path

root = Path("/Users/sadhikakamchetty/Desktop/VoiceDB/embeds_w2v")

by_person = defaultdict(list)

# 1) Collect embeddings per person from flat dir
for f in root.glob("*.npy"):
    parts = f.stem.split("_")
    if len(parts) < 4:
        # not in expected pattern: <idx>_<name...>_<start>_<end>
        continue
    name = "_".join(parts[1:-2])  # everything except first (idx) and last two (times)
    if name.lower() in {"speaker", "unknown"}:
        # optional: skip generic labels
        continue

    emb = np.load(f)
    emb = np.asarray(emb, dtype=np.float32).squeeze()
    if emb.ndim != 1:
        # if stored as (1, D) or (D, 1), squeeze above should fix; skip truly invalid shapes
        continue
    by_person[name].append(emb)

print("People found:", list(by_person.keys()))
print("Counts:", {k: len(v) for k, v in by_person.items()})

# 2) Build centroids robustly
def l2norm(x):
    n = np.linalg.norm(x)
    return x if n == 0 else x / n

def robust_centroid(embs, outlier_drop=0.15):
    E = np.array([l2norm(e) for e in embs], dtype=np.float32)
    if len(E) == 1:
        return l2norm(E[0]), np.arange(len(E))
    proto = l2norm(E.mean(axis=0))
    sims = E @ proto
    k = max(1, int(round((1 - outlier_drop) * len(E))))
    keep_idx = np.argsort(sims)[-k:]
    centroid = l2norm(E[keep_idx].mean(axis=0))
    return centroid, keep_idx

person_centroids = {}
person_keepmaps = {}

for person, embs in by_person.items():
    if not embs:
        continue
    centroid, kept = robust_centroid(embs, outlier_drop=0.15)
    person_centroids[person] = centroid
    person_keepmaps[person] = kept

# 3) Save voicebook — guard against "need at least one array to stack"
if not person_centroids:
    raise RuntimeError(
        "No centroids built. Check that *.npy files contain 1-D vectors and names parse correctly."
    )

persons = np.array(sorted(person_centroids.keys()), dtype=object)
centroids = np.stack([person_centroids[p] for p in persons])

np.savez_compressed("voicebook.npz", persons=persons, centroids=centroids)
print(f"Wrote voicebook.npz with {len(persons)} people.")
