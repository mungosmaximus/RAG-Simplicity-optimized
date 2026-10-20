"""
Faza 5 — ekstrakcija entiteta iz chunkova (LLM).

Za svaki chunk iz data/chunks/_all_chunks.jsonl:
  1) Ucitaj tekst.
  2) Posalji LLM-u (LM Studio) prompt za ekstrakciju entiteta.
  3) Parsiraj JSON odgovor.
  4) Sacuvaj u data/questions/entities/<source>.jsonl.

Entiteti koji se traze:
  - disease, drug, dose, procedure, symptom, measure,
    complication, criterion, test, stage, age_group,
    comorbidity, mechanism, effect, cause, risk_factor,
    vaccine, lifestyle, frequency, route, duration,
    classification, differential, prognosis, mortality,
    prevalence, incidence, population, genetic, progression,
    term, referral, followup, treatment_response, monitoring

Jednokratno, ~30 min za 888 chunkova na CPU.

Izvor:  data/chunks/_all_chunks.jsonl
Izlaz:  data/questions/entities/<source>.jsonl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json
import re
from collections import defaultdict
from tqdm import tqdm

from openai import OpenAI


# --- Konfiguracija ---
CHUNKS_PATH = Path("data/chunks/_all_chunks.jsonl")
OUTPUT_DIR = Path("data/questions/entities")

LM_STUDIO_URL = "http://localhost:1234/v1"
LM_STUDIO_KEY = "lm-studio"
MODEL_NAME = "qwen2.5-14b-instruct"   # prilagodi ako je drugacije

# Batch velicina — koliko chunkova pre cuvanja
SAVE_EVERY = 50

# Maksimalna duzina chunka koji saljemo LLM-u (da ne prekoracimo kontekst)
MAX_CHUNK_CHARS = 3000


# --- Lista entiteta koje trazimo ---
ENTITY_TYPES = [
    "disease",         # bolest
    "drug",            # lek
    "dose",            # doza
    "procedure",       # procedura
    "symptom",         # simptom
    "measure",         # mera
    "complication",    # komplikacija
    "criterion",       # kriterijum
    "test",            # test
    "stage",           # stadijum
    "age_group",       # uzrasna grupa
    "comorbidity",     # komorbiditet
    "mechanism",       # mehanizam
    "effect",          # efekat
    "cause",           # uzrok
    "risk_factor",     # faktor rizika
    "vaccine",         # vakcina
    "lifestyle",       # zivotni stil
    "frequency",       # ucestalost
    "route",           # put primene
    "duration",        # trajanje
    "classification",  # klasifikacija
    "differential",    # diferencijalna dijagnoza
    "prognosis",       # prognoza
    "mortality",       # smrtnost
    "prevalence",      # prevalencija
    "incidence",       # incidenca
    "population",      # populacija
    "genetic",         # genetika
    "progression",     # progresija
    "term",            # termin
    "referral",        # upucivanje
    "followup",        # pracenje
    "monitoring",      # monitoring
]


# --- Prompt ---
SYSTEM_PROMPT = """Ti si medicinski asistent koji izvlaci entitete iz srpskog medicinskog teksta.

STROGA PRAVILA:
1. SVE vrednosti entiteta MORAJU biti na SRPSKOM jeziku, LATINICA.
   - NE koristi cirilicu.
   - NE prevodi na engleski.
   - Ako je u tekstu "ХОБП", vrati "hobp".
   - Ako je u tekstu "corticosteroid", vrati "kortikosteroid".
2. NE izvlaci delimicne entitete:
   - "antibiotikom za boljest" -> izvuci samo "antibiotik" ili nista.
   - Ne kombinuj reci koje ne cine entitet.
3. NE mesaj kategorije:
   - "astma" je bolest -> u "disease", NE u "symptom".
   - "fev1" je test -> u "test", NE u "criterion" ili "measure".
   - "500 mg" je doza -> u "dose".
4. IGNORISI nivoe dokaza (A, B, C, D) i stepene preporuka (1a, 1b, 2a, ...).
5. Vrati ISKLJUCIVO validan JSON objekat, bez ikakvog teksta pre ili posle.
6. Svaki kljuc mora biti prisutan, cak i ako je lista prazna.
7. Vrednosti su liste stringova, sve malim slovima.
"""

USER_PROMPT_TEMPLATE = """Iz sledeceg medicinskog teksta izvuci entitete.

Entiteti koje trazimo (kljucevi JSON-a):
{entity_list}

Pravila:
- Vrati ISKLJUCIVO JSON objekat, bez objasnjenja.
- Svaki kljuc mora biti prisutan, cak i ako je lista prazna.
- Vrednosti su liste stringova.
- SVE VREDNOSTI NA SRPSKOM (latinica, ekavica). NE prevodi na engleski.
- Primeri prevoda:
  - "asthma" -> "astma"
  - "corticosteroid" -> "kortikosteroid"
  - "children" -> "deca"
  - "antibiotic a" -> "antibiotik a"
  - "500 mg" -> "500 mg" (doze ostaju iste)
- Ne mesaj kategorije:
  - Ako je "fev1" test, ne ide u "measure" ili "criterion".
  - Ako je "astma" bolest, ne ide u "symptom".
  - Ako je "500 mg" doza, ide u "dose".
- Ne izvlaci delimicne entitete ("antibiotikom za" nije entitet).
- Ignorisi nivoe dokaza (A, B, C, D) i stepene preporuka (1a, 1b, 2a).
- Izvuci samo ono sto je EKSPLICITNO u tekstu, ne izmisljaj.
- Za doze: ukljuci broj i jedinicu (npr. "500 mg").
- Sve malim slovima.

Tekst:
\"\"\"
{chunk_text}
\"\"\"

JSON:"""


def load_chunks(path: Path) -> list[dict]:
    chunks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    return chunks


def group_by_source(chunks: list[dict]) -> dict[str, list[dict]]:
    by_source = defaultdict(list)
    for c in chunks:
        by_source[c["source"]].append(c)
    return dict(by_source)


def extract_entities_from_chunk(client: OpenAI, chunk_text: str) -> dict:
    """
    Posalji LLM-u chunk i vrati dict {entitet: [vrednosti]}.
    Ako LLM ne vrati validan JSON, vrati prazan dict.
    """
    # Ogranici duzinu chunka
    text = chunk_text[:MAX_CHUNK_CHARS]

    entity_list = "\n".join(f"- {e}" for e in ENTITY_TYPES)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        entity_list=entity_list,
        chunk_text=text,
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=2500,
        )
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  GRESKA pri LLM pozivu: {e}")
        return {}

    # Ocisti markdown code block ako postoji
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # Nadji JSON u tekstu
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        return {}

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return {}

    # Normalizuj: samo kljucevi iz ENTITY_TYPES, sve lowercase
    result = {}
    for entity_type in ENTITY_TYPES:
        values = data.get(entity_type, [])
        if isinstance(values, list):
            cleaned = []
            for v in values:
                if isinstance(v, str) and v.strip():
                    cleaned.append(v.strip().lower())
            # Deduplikacija
            result[entity_type] = sorted(set(cleaned))
        else:
            result[entity_type] = []

    return result


def has_any_entity(entities: dict) -> bool:
    """Vraca True ako barem jedan entitet ima vrednost."""
    return any(len(v) > 0 for v in entities.values())


def save_entities_for_source(source: str,
                              entities_list: list[dict],
                              output_dir: Path) -> None:
    """Cuva entitete za jedan PDF u .jsonl fajl."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{source}.jsonl"

    with open(out_path, "w", encoding="utf-8") as f:
        for item in entities_list:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"  Sacuvano: {out_path}  ({len(entities_list)} chunkova)")


def main():
    if not CHUNKS_PATH.exists():
        print(f"Nema: {CHUNKS_PATH}")
        return

    print(f"Ucitavam chunkove: {CHUNKS_PATH}")
    chunks = load_chunks(CHUNKS_PATH)
    print(f"  Ukupno chunkova: {len(chunks)}")

    by_source = group_by_source(chunks)
    print(f"  Dokumenata: {len(by_source)}")
    for s, lst in by_source.items():
        print(f"    {s:30s}: {len(lst)}")

    # Provera LM Studio veze
    client = OpenAI(base_url=LM_STUDIO_URL, api_key=LM_STUDIO_KEY)
    try:
        models = client.models.list()
        print(f"\nLM Studio modeli: {[m.id for m in models.data]}")
    except Exception as e:
        print(f"\nGRESKA: LM Studio nije dostupan: {e}")
        return

    # Obrada po dokumentu
    for source, source_chunks in by_source.items():
        print(f"\n=== {source} ===")

        # Preskoci ako vec postoji
        out_path = OUTPUT_DIR / f"{source}.jsonl"
        if out_path.exists():
            print(f"  Vec postoji: {out_path}")
            print(f"  Preskacem (obrisi fajl ako zelis ponovnu obradu).")
            continue

        entities_list = []
        skipped_empty = 0

        for chunk in tqdm(source_chunks, desc=f"  {source[:30]}"):
            entities = extract_entities_from_chunk(client, chunk["text"])

            if not has_any_entity(entities):
                skipped_empty += 1
                continue

            entities_list.append({
                "chunk_id": chunk["chunk_id"],
                "source": source,
                "pdf_page": chunk.get("pdf_page"),
                "section_ids": chunk.get("section_ids", []),
                "section_path": chunk.get("section_path", []),
                "chunk_type": chunk.get("chunk_type"),
                "entities": entities,
            })

            # Periodicno cuvanje (za slucaj prekida)
            if len(entities_list) % SAVE_EVERY == 0:
                save_entities_for_source(source, entities_list, OUTPUT_DIR)

        # Finalno cuvanje
        save_entities_for_source(source, entities_list, OUTPUT_DIR)
        print(f"  Preskoceno (bez entiteta): {skipped_empty}")

    # Finalna statistika
    print(f"\n{'=' * 60}")
    print(f"GOTOVO")
    print(f"{'=' * 60}")
    for source in by_source:
        out_path = OUTPUT_DIR / f"{source}.jsonl"
        if out_path.exists():
            with open(out_path, encoding="utf-8") as f:
                n = sum(1 for line in f if line.strip())
            print(f"  {source:30s}: {n} chunkova sa entitetima")


if __name__ == "__main__":
    main()