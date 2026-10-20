"""
Faza 7 — retrieval sa tri nivoa.

Tok:
  1) Prepoznaj intent (intents.py).
  2) NIVO 1: Instanced kes (FAISS pretraga + heuristika po section_path).
     - Ako nade match: vrati originalne chunk-ove iz chunks_indexed.jsonl.
  3) NIVO 3: RAG fallback (FAISS pretraga u faiss.index).
     - Ako Nivo 1 ne nade nista, koristi RAG.

Filter po intent-u:
  - Svaki intent ima listu kljucnih reci koje moraju biti u section_path.
  - Ako section_path ne sadrzi nijednu kljucnu rec, chunk se odbacuje.

Izlaz:
  {
    "query": str,
    "intent": str,
    "source": "instanced" | "rag",
    "chunks": [
      {
        "chunk_id": str,
        "source": str,
        "pdf_page": int,
        "section_path": [...],
        "chunk_type": str,
        "text": str,
        "match_score": float,
        "matched_query": str | None,
        "template_id": str | None,
      },
      ...
    ],
  }

Izvor:
  data/index/faiss.index              (888 chunkova)
  data/index/instanced.index          (2507 pitanja)
  data/index/chunks_indexed.jsonl     (888 + embedding_id)
  data/index/instanced_indexed.jsonl  (2507 + embedding_id)
  data/index/meta.json
  data/index/instanced_meta.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json
from collections import defaultdict

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from intents import detect_intent


# --- Konfiguracija ---
INDEX_DIR = Path("data/index")

# Model za embedding upita
MODEL_NAME = "intfloat/multilingual-e5-small"

# E5 prefiks za upite
QUERY_PREFIX = "query: "

# Threshold za instanced kes
INSTANCED_THRESHOLD = 0.90

# Threshold za RAG
RAG_THRESHOLD = 0.70

# Broj rezultata
INSTANCED_TOP_K = 5
RAG_TOP_K = 5


# =====================================================================
# MAPA: intent -> kljucne reci u section_path
# =====================================================================

INTENT_SECTION_KEYWORDS = {
    # --- Nove namere ---
    "curability":        ["lečenje", "terapija", "izlečiv", "prognoza", "uvod"],
    "dosage":            ["doza", "doziranje", "primena", "terapija"],
    "symptoms":          ["simptom", "klinička slika", "manifestacij", "dijagnoza"],
    "prevention":        ["prevencija", "sprečavanje", "vakcinacija", "imunizacija"],
    "risk_factors":      ["faktor rizika", "rizik", "uzrok", "etiology"],

    # --- Postojece namere ---
    "therapeutic":       ["lečenje", "terapija", "lek", "farmakološk"],
    "diagnostic":        ["dijagnoza", "dijagnostik", "ispitivanje", "test"],
    "definitional":      ["definicij", "uvod", "pojam"],
    "causal":            ["uzrok", "patogenez", "mehanizam", "nastanak"],
    "complications":     ["komplikacij", "posledic"],
    "contraindication":  ["kontraindikacij", "oprez", "mere opreza"],
    "prognosis":         ["prognoza", "preživljavanje"],
    "monitoring":        ["praćenje", "monitoring", "kontrola"],
    "lifestyle":         ["životni stil", "ishrana", "vežbanje", "pušenje"],
    "epidemiology":      ["epidemiolog", "prevalencij", "incidenc", "mortalitet"],
    "differential_diagnosis": ["diferencijalna", "diferencijaln"],

    # --- Namere bez filtera ---
    "comprehensive":     [],
    "precise":           [],
    "reference":         [],
    "procedural":        [],
    "comparison":        [],
}


# --- Globalno stanje (ucitava se jednom) ---
_state = {
    "model": None,
    "faiss_index": None,
    "instanced_index": None,
    "chunks": None,
    "chunks_by_id": None,
    "instanced_questions": None,
}


# =====================================================================
# UCITAVANJE
# =====================================================================

def load_indexes() -> None:
    """Ucitava modele i indekse u globalno stanje."""
    if _state["model"] is not None:
        return

    print("Ucitavam modele i indekse...")

    # 1) Model
    print(f"  Model: {MODEL_NAME}")
    _state["model"] = SentenceTransformer(MODEL_NAME)

    # 2) FAISS indeks (chunkovi)
    faiss_path = INDEX_DIR / "faiss.index"
    if not faiss_path.exists():
        raise FileNotFoundError(f"Nema: {faiss_path}")
    _state["faiss_index"] = faiss.read_index(str(faiss_path))
    print(f"  FAISS chunkovi: {_state['faiss_index'].ntotal} vektora")

    # 3) FAISS indeks (instanced pitanja)
    instanced_path = INDEX_DIR / "instanced.index"
    if not instanced_path.exists():
        raise FileNotFoundError(f"Nema: {instanced_path}")
    _state["instanced_index"] = faiss.read_index(str(instanced_path))
    print(f"  FAISS instanced: {_state['instanced_index'].ntotal} vektora")

    # 4) Chunkovi sa metadata
    chunks_path = INDEX_DIR / "chunks_indexed.jsonl"
    chunks = []
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    _state["chunks"] = chunks
    _state["chunks_by_id"] = {c["chunk_id"]: c for c in chunks}
    print(f"  Chunkovi: {len(chunks)}")

    # 5) Instancirana pitanja sa metadata
    instanced_q_path = INDEX_DIR / "instanced_indexed.jsonl"
    instanced_questions = []
    with open(instanced_q_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                instanced_questions.append(json.loads(line))
    _state["instanced_questions"] = instanced_questions
    print(f"  Instancirana pitanja: {len(instanced_questions)}")

    print("Spremno.\n")


# =====================================================================
# EMBEDDING UPITA
# =====================================================================

def embed_query(query: str) -> np.ndarray:
    """Embedding upita sa prefiksom 'query: '."""
    text = QUERY_PREFIX + query
    emb = _state["model"].encode(
        [text],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return emb.astype("float32")


# =====================================================================
# FILTER PO SECTION_PATH
# =====================================================================

def section_matches_intent(section_path: list[str], intent: str) -> bool:
    """
    Proverava da li section_path sadrzi bar jednu kljucnu rec za intent.
    Ako intent nema definisane kljucne reci — vraca True (bez filtera).
    """
    keywords = INTENT_SECTION_KEYWORDS.get(intent, [])
    if not keywords:
        return True

    section_text = " ".join(section_path).lower()
    return any(kw in section_text for kw in keywords)


# =====================================================================
# NIVO 1: INSTANCED KES
# =====================================================================

def search_instanced(query: str, intent: str,
                     top_k: int = INSTANCED_TOP_K) -> list[dict]:
    """
    Pretraga u instanced indeksu sa filterom po intent-u i section_path.
    Vraca listu chunk-ova (originalnih) sa metadata.
    """
    if _state["instanced_index"].ntotal == 0:
        return []

    q_emb = embed_query(query)
    D, I = _state["instanced_index"].search(q_emb, k=top_k * 5)

    matched = []
    seen_chunks = set()   # deduplikacija po chunk_id

    for dist, idx in zip(D[0], I[0]):
        if dist < INSTANCED_THRESHOLD:
            continue

        inst_q = _state["instanced_questions"][idx]
        section_path = inst_q.get("section_path", [])

        # Filter po section_path
        if not section_matches_intent(section_path, intent):
            continue

        # Dohvati originalni chunk
        source_chunk_id = inst_q.get("source_chunk")
        if source_chunk_id in seen_chunks:
            continue
        chunk = _state["chunks_by_id"].get(source_chunk_id)
        if not chunk:
            continue
        seen_chunks.add(source_chunk_id)

        matched.append({
            "chunk_id": chunk["chunk_id"],
            "source": chunk.get("source"),
            "pdf_page": chunk.get("pdf_page"),
            "section_path": chunk.get("section_path", []),
            "chunk_type": chunk.get("chunk_type"),
            "text": chunk.get("text", ""),
            "match_score": float(dist),
            "matched_query": inst_q.get("query"),
            "template_id": inst_q.get("template_id"),
        })

        if len(matched) >= top_k:
            break

    return matched


# =====================================================================
# NIVO 3: RAG FALLBACK
# =====================================================================

def search_rag(query: str, intent: str,
               top_k: int = RAG_TOP_K) -> list[dict]:
    """
    Pretraga u FAISS indeksu chunkova (RAG).
    Ako intent ima definisane kljucne reci, filtriraj po section_path.
    """
    if _state["faiss_index"].ntotal == 0:
        return []

    q_emb = embed_query(query)
    D, I = _state["faiss_index"].search(q_emb, k=top_k * 3)

    results = []
    for dist, idx in zip(D[0], I[0]):
        if dist < RAG_THRESHOLD:
            continue

        chunk = _state["chunks"][idx]

        # Ako intent ima filter, primeni ga i na RAG
        if not section_matches_intent(chunk.get("section_path", []), intent):
            continue

        results.append({
            "chunk_id": chunk["chunk_id"],
            "source": chunk.get("source"),
            "pdf_page": chunk.get("pdf_page"),
            "section_path": chunk.get("section_path", []),
            "chunk_type": chunk.get("chunk_type"),
            "text": chunk.get("text", ""),
            "match_score": float(dist),
            "matched_query": None,
            "template_id": None,
        })

        if len(results) >= top_k:
            break

    return results


# =====================================================================
# GLAVNI TOK
# =====================================================================

def retrieve(query: str) -> dict:
    """
    Glavni retrieval tok:
      1) Prepoznaj intent.
      2) NIVO 1: Instanced kes sa filterom.
      3) Ako nema — NIVO 3: RAG fallback (takodje sa filterom).
    """
    load_indexes()

    # 1) Intent
    intent = detect_intent(query)

    # 2) Nivo 1: instanced
    instanced_results = search_instanced(query, intent, top_k=INSTANCED_TOP_K)

    if instanced_results:
        return {
            "query": query,
            "intent": intent,
            "source": "instanced",
            "chunks": instanced_results,
        }

    # 3) Nivo 3: RAG fallback
    rag_results = search_rag(query, intent, top_k=RAG_TOP_K)

    return {
        "query": query,
        "intent": intent,
        "source": "rag",
        "chunks": rag_results,
    }


# =====================================================================
# TEST
# =====================================================================

def print_result(result: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"Query:  {result['query']!r}")
    print(f"Intent: {result['intent']}")
    print(f"Source: {result['source']}")
    print(f"Chunks: {len(result['chunks'])}")
    print(f"{'=' * 60}")

    for i, c in enumerate(result["chunks"], 1):
        print(f"\n[Chunk {i}]")
        print(f"  chunk_id:      {c['chunk_id']}")
        print(f"  source:        {c.get('source')}")
        print(f"  pdf_page:      {c.get('pdf_page')}")
        print(f"  section_path:  {c.get('section_path')}")
        print(f"  chunk_type:    {c.get('chunk_type')}")
        print(f"  match_score:   {c.get('match_score'):.3f}")
        if c.get("matched_query"):
            print(f"  matched_query: {c['matched_query']!r}")
        if c.get("template_id"):
            print(f"  template_id:   {c['template_id']}")
        text_preview = c.get("text", "")[:200].replace("\n", " ")
        print(f"  text:          {text_preview}...")


def test_retrieval() -> None:
    test_queries = [
        "Kako se leči HOBP?",
        "Koja je doza kortikosteroida?",
        "Da li se astma može izlečiti?",
        "Koji su simptomi HOBP?",
        "Kada se NIMV ne sme dati?",
        "Kako se dijagnostikuje HOBP?",
        "Šta je astma?",
        "Kako se sprečava HOBP?",
        "Zašto nastaje HOBP?",
        "Koji su faktori rizika za astmu?",
    ]

    for q in test_queries:
        result = retrieve(q)
        print_result(result)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="RAG retrieval")
    parser.add_argument("--query", type=str, help="Pojedinacni upit")
    parser.add_argument("--test", action="store_true", help="Pokreni test primere")
    args = parser.parse_args()

    if args.test:
        test_retrieval()
    elif args.query:
        result = retrieve(args.query)
        print_result(result)
    else:
        print("RAG retrieval — interaktivni rezim")
        print("Unesi pitanje (ili 'exit' za izlaz):\n")

        load_indexes()

        while True:
            try:
                q = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q or q.lower() in ("exit", "quit"):
                break
            result = retrieve(q)
            print_result(result)
            print()


if __name__ == "__main__":
    main()