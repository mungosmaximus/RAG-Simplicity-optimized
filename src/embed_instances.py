"""
Faza 6.5 — embedding instanciranih pitanja u poseban FAISS indeks.

Za svako pitanje iz data/questions/instanced/*.jsonl:
  1) Ucitaj tekst pitanja.
  2) Izracunaj embedding (intfloat/multilingual-e5-small).
  3) Normalizuj vektor (L2).
  4) Dodaj u FAISS indeks (IndexFlatIP).

E5 prefiks za pitanja: "query: " + text
  (pitanja su upiti, ne dokumenti — zato "query: ", ne "passage: ")

Sacuvaj:
  data/index/instanced.index           — FAISS indeks (2507 pitanja)
  data/index/instanced_indexed.jsonl   — pitanja + embedding_id
  data/index/instanced_meta.json       — metadata

Izvor:  data/questions/instanced/*.jsonl
Izlaz:  data/index/instanced.*
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
INSTANCED_DIR = Path("data/questions/instanced")
OUTPUT_DIR = Path("data/index")

# E5 prefiks za pitanja (upiti)
QUERY_PREFIX = "query: "

BATCH_SIZE = 32


def load_questions(instanced_dir: Path) -> list[dict]:
    """
    Ucitava sva pitanja iz svih .jsonl fajlova u folderu.
    Dodaje `source_file` ako nije prisutan.
    """
    questions = []
    jsonl_files = sorted(instanced_dir.glob("*.jsonl"))

    for jsonl_path in jsonl_files:
        print(f"  Ucitavam: {jsonl_path.name}")
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    q = json.loads(line)
                    # Sacuvaj izvorni fajl (za dijagnostiku)
                    q["_source_file"] = jsonl_path.stem
                    questions.append(q)

    return questions


def embed_questions(questions: list[dict],
                    model: SentenceTransformer,
                    batch_size: int = BATCH_SIZE) -> np.ndarray:
    """Za svako pitanje izracunaj vektor sa prefiksom 'query: '."""
    texts = [QUERY_PREFIX + q["query"] for q in questions]

    print(f"\nEmbedding {len(texts)} pitanja...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.astype("float32")


def build_faiss_index(embeddings: np.ndarray) -> faiss.Index:
    """Gradi FAISS IndexFlatIP (inner product = cosine similarity)."""
    dim = embeddings.shape[1]
    print(f"\nGradim FAISS indeks (dim={dim}, n={len(embeddings)})...")
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    print(f"  FAISS indeks: {index.ntotal} vektora")
    return index


def save_outputs(questions: list[dict],
                 index: faiss.Index,
                 embeddings: np.ndarray,
                 output_dir: Path,
                 model_name: str) -> None:
    """Cuva FAISS indeks, pitanja sa embedding_id, i metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) FAISS indeks
    index_path = output_dir / "instanced.index"
    faiss.write_index(index, str(index_path))
    print(f"  Sacuvan FAISS indeks: {index_path}")

    # 2) Pitanja sa embedding_id
    questions_path = output_dir / "instanced_indexed.jsonl"
    with open(questions_path, "w", encoding="utf-8") as f:
        for i, q in enumerate(questions):
            q["embedding_id"] = i
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"  Sacuvana pitanja:     {questions_path}")

    # 3) Metadata
    meta = {
        "model_name": model_name,
        "dimension": int(embeddings.shape[1]),
        "n_questions": int(len(questions)),
        "index_type": "IndexFlatIP",
        "normalized": True,
        "query_prefix": QUERY_PREFIX,
        "created_at": datetime.now().isoformat(),
    }
    meta_path = output_dir / "instanced_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  Sacuvana metadata:    {meta_path}")


def print_stats(questions: list[dict]) -> None:
    """Ispisuje statistiku pitanja."""
    by_source = {}
    by_template = {}
    by_intent = {}
    for q in questions:
        s = q.get("source", "?")
        t = q.get("template_id", "?")
        i = q.get("intent", "?")
        by_source[s] = by_source.get(s, 0) + 1
        by_template[t] = by_template.get(t, 0) + 1
        by_intent[i] = by_intent.get(i, 0) + 1

    print("\nPo dokumentu:")
    for s, n in sorted(by_source.items()):
        print(f"  {s:30s}: {n}")

    print("\nPo nameri (top 10):")
    for i, n in sorted(by_intent.items(), key=lambda x: -x[1])[:10]:
        print(f"  {i:25s}: {n}")

    print("\nPo sablonu (top 10):")
    for t, n in sorted(by_template.items(), key=lambda x: -x[1])[:10]:
        print(f"  {t:35s}: {n}")


def main():
    if not INSTANCED_DIR.exists():
        print(f"Nema: {INSTANCED_DIR}")
        print("Pokreni prvo: python src/instances.py")
        return

    print(f"Ucitavam pitanja iz: {INSTANCED_DIR}")
    questions = load_questions(INSTANCED_DIR)

    if not questions:
        print("Nema pitanja.")
        return

    print(f"  Ukupno pitanja: {len(questions)}")
    print_stats(questions)

    # Ucitaj model
    print(f"\nUcitavam model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    print(f"  Dimenzija: {model.get_embedding_dimension()}")

    # Embedding
    embeddings = embed_questions(questions, model)

    # FAISS indeks
    index = build_faiss_index(embeddings)

    # Sacuvaj
    print("\nSacuvavam izlaze...")
    save_outputs(questions, index, embeddings, OUTPUT_DIR, MODEL_NAME)

    # Finalna statistika
    print(f"\n{'=' * 60}")
    print(f"GOTOVO")
    print(f"{'=' * 60}")
    print(f"Ukupno pitanja: {len(questions)}")
    print(f"Dimenzija:      {embeddings.shape[1]}")
    print(f"Indeks:         {OUTPUT_DIR / 'instanced.index'}")
    print(f"Pitanja:        {OUTPUT_DIR / 'instanced_indexed.jsonl'}")
    print(f"Metadata:       {OUTPUT_DIR / 'instanced_meta.json'}")


if __name__ == "__main__":
    main()