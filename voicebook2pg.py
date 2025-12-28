import os
import numpy as np
import psycopg2, getpass
from pathlib import Path
from psycopg2.extras import execute_values

root = Path("/Users/sadhikakamchetty/Desktop/VoiceDB/embeds_w2v")

def l2norm(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x)
    return x if n == 0 else x / n

def parse_name(file: Path) -> str:
    # e.g. '12_Manolis_Kellis_000016_000029.npy' -> 'Manolis_Kellis'
    parts = file.stem.split("_")
    return "_".join(parts[1:-2])

# 1) Aggregate sums + counts per person (streaming, memory-safe)
sums = {}   # name -> running sum vector (np.ndarray)
counts = {} # name -> int

files = list(root.glob("*.npy"))
print(f"Found {len(files)} embedding files...")

for f in files:
    emb = np.load(f).astype(np.float64).squeeze()
    if emb.ndim != 1:
        raise ValueError(f"Embedding not 1D in {f}: shape={emb.shape}")

    # (optional) normalize each clip before averaging — often better for speakers
    emb = l2norm(emb)

    name = parse_name(f)

    if name not in sums:
        sums[name] = np.zeros_like(emb, dtype=np.float64)
        counts[name] = 0

    sums[name] += emb
    counts[name] += 1

# 2) Build averaged, normalized rows
rows = []
for name, s in sums.items():
    mean = s / counts[name]
    mean = l2norm(mean)
    rows.append((name, mean.tolist(), counts[name]))

print(f"Computed {len(rows)} averaged embeddings.")

# 3) UPSERT into Postgres (one row per name)
conn = psycopg2.connect(dbname="voicedb", user=getpass.getuser())
cur = conn.cursor()

# Make sure the table exists (safe if already created)
cur.execute("""
CREATE TABLE IF NOT EXISTS speaker_embeddings (
  name        TEXT PRIMARY KEY,
  embedding   DOUBLE PRECISION[] NOT NULL,
  n_samples   INTEGER NOT NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
""")

# Upsert: replace the embedding, n_samples, and updated_at when name exists
upsert_sql = """
INSERT INTO speaker_embeddings (name, embedding, n_samples)
VALUES %s
ON CONFLICT (name) DO UPDATE
SET embedding = EXCLUDED.embedding,
    n_samples = EXCLUDED.n_samples,
    updated_at = now();
"""

execute_values(cur, upsert_sql, rows, template="(%s, %s, %s)")
conn.commit()
cur.close()
conn.close()

print("Stored one averaged embedding per person in Postgres.")
