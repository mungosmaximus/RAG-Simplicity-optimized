"""
Faza 4 — embedding chunkova i FAISS indeks.

Za svaki chunk iz data/chunks/_all_chunks.jsonl:
  1) Ucitaj tekst.
  2) Izracunaj embedding (intfloat/multilingual-e5-small).
  3) Normalizuj vektor (L2).
  4) Dodaj u FAISS indeks (IndexFlatIP).

Sacuvaj:
  data/index/faiss.index           — FAISS indeks
  data/index/chunks_indexed.jsonl  — chunkovi + embedding_id
  data/index/meta.json             — model, dimenzija, broj chunkova, datum

E5 prefiks:
  - Za dokumente (chunkove): "passage: " + text
  - Za upite (kasnije):      "query: " + text
  (bez prefiksa kvalitet opada ~10%)

Izvor:  data/chunks/_all_chunks.jsonl
Izlaz:  data/index/*
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json
from datetime import datetime

import numpy as np
import faiss
from tqdm import tqdm
from sentence_transformers import SentenceTransformer


# --- Konfiguracija ---
MODEL_NAME = "intfloat/multilingual-e5-small"
CHUNKS_PATH = Path("data/chunks/_all_chunks.jsonl")
OUTPUT_DIR = Path("data/index")

# E5 prefiks za dokumente
PASSAGE_PREFIX = "passage: "

# Batch za embedding (CPU: 16-32 je OK)
BATCH_SIZE = 32


def load_chunks(path: Path) -> list[dict]:
    """Ucitava chunkove iz .jsonl fajla."""
    chunks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    return chunks


def embed_chunks(chunks: list[dict],
                 model: SentenceTransformer,
                 batch_size: int = BATCH_SIZE) -> np.ndarray:
    """
    Za svaki chunk izracunaj vektor.
    Vraca np.ndarray shape (n_chunks, dim), float32, normalizovan L2.
    """
    texts = [PASSAGE_PREFIX + c["text"] for c in chunks]

    print(f"\nEmbedding {len(texts)} chunkova...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,   # L2 normalizacija
    )
    return embeddings.astype("float32")


def build_faiss_index(embeddings: np.ndarray) -> faiss.Index:
    """
    Gradi FAISS IndexFlatIP (inner product = cosine similarity
    za normalizovane vektore).
    """
    dim = embeddings.shape[1]
    print(f"\nGradim FAISS indeks (dim={dim}, n={len(embeddings)})...")
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    print(f"  FAISS indeks: {index.ntotal} vektora")
    return index


def save_outputs(chunks: list[dict],
                 index: faiss.Index,
                 embeddings: np.ndarray,
                 output_dir: Path,
                 model_name: str) -> None:
    """Cuva FAISS indeks, chunkove sa embedding_id, i metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) FAISS indeks
    index_path = output_dir / "faiss.index"
    faiss.write_index(index, str(index_path))
    print(f"  Sacuvan FAISS indeks: {index_path}")

    # 2) Chunkovi sa embedding_id
    chunks_path = output_dir / "chunks_indexed.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as f:
        for i, c in enumerate(chunks):
            c["embedding_id"] = i
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"  Sacuvani chunkovi:    {chunks_path}")

    # 3) Metadata
    meta = {
        "model_name": model_name,
        "dimension": int(embeddings.shape[1]),
        "n_chunks": int(len(chunks)),
        "index_type": "IndexFlatIP",
        "normalized": True,
        "passage_prefix": PASSAGE_PREFIX,
        "created_at": datetime.now().isoformat(),
    }
    meta_path = output_dir / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  Sacuvana metadata:    {meta_path}")


def print_stats(chunks: list[dict]) -> None:
    """Ispisuje statistiku chunkova."""
    by_source = {}
    by_type = {}
    for c in chunks:
        s = c.get("source", "?")
        t = c.get("chunk_type", "?")
        by_source[s] = by_source.get(s, 0) + 1
        by_type[t] = by_type.get(t, 0) + 1

    print("\nPo dokumentu:")
    for s, n in sorted(by_source.items()):
        print(f"  {s:30s}: {n}")

    print("\nPo tipu:")
    for t, n in sorted(by_type.items()):
        print(f"  {t:20s}: {n}")


def main():
    if not CHUNKS_PATH.exists():
        print(f"Nema: {CHUNKS_PATH}")
        print("Pokreni prvo: python src/chunk.py")
        return

    print(f"Ucitavam chunkove: {CHUNKS_PATH}")
    chunks = load_chunks(CHUNKS_PATH)
    print(f"  Ukupno chunkova: {len(chunks)}")

    if not chunks:
        print("Nema chunkova.")
        return

    print_stats(chunks)

    # Ucitaj model
    print(f"\nUcitavam model: {MODEL_NAME}")
    print("  (prvi put se skida sa HuggingFace-a, ~450 MB)")
    model = SentenceTransformer(MODEL_NAME)
    print(f"  Dimenzija: {model.get_embedding_dimension()}")

    # Embedding
    embeddings = embed_chunks(chunks, model)

    # FAISS indeks
    index = build_faiss_index(embeddings)

    # Sacuvaj
    print("\nSacuvavam izlaze...")
    save_outputs(chunks, index, embeddings, OUTPUT_DIR, MODEL_NAME)

    # Finalna statistika
    print(f"\n{'=' * 60}")
    print(f"GOTOVO")
    print(f"{'=' * 60}")
    print(f"Ukupno chunkova: {len(chunks)}")
    print(f"Dimenzija:       {embeddings.shape[1]}")
    print(f"Indeks:          {OUTPUT_DIR / 'faiss.index'}")
    print(f"Chunkovi:        {OUTPUT_DIR / 'chunks_indexed.jsonl'}")
    print(f"Metadata:        {OUTPUT_DIR / 'meta.json'}")


if __name__ == "__main__":
    main()