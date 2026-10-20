"""
Faza 6 — generisanje instanciranih pitanja iz entiteta.

Za svaki chunk iz data/questions/entities_normalized/<source>.jsonl:
  1) Ucitaj entitete (normalizovane).
  2) Za svaki sablon iz data/questions/templates.jsonl:
     - Proveri da li su svi `requires` entiteti prisutni u chunku.
     - Ako da, instanciraj pitanje (popuni {placeholder}-e).
  3) OPSTA DEDUPLIKACIJA: ukloni duplikate po normalizovanom query-ju
     (lowercase, bez interpunkcije, bez visestrukih razmaka).
     Zadrzi pitanje sa najvise entiteta (bolji kontekst).
  4) Sacuvaj u data/questions/instanced/<source>.jsonl.

Izlaz: data/questions/instanced/<source>.jsonl

Izvor:  data/questions/entities_normalized/*.jsonl
        data/questions/templates.jsonl
Izlaz:  data/questions/instanced/*.jsonl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json
import re
from collections import defaultdict, Counter
from tqdm import tqdm


# --- Konfiguracija ---
ENTITIES_DIR = Path("data/questions/entities_normalized")
TEMPLATES_PATH = Path("data/questions/templates.jsonl")
OUTPUT_DIR = Path("data/questions/instanced")

# Minimalna duzina entiteta
MIN_ENTITY_LEN = 2

# Maksimalan broj instanciranih pitanja po chunku
MAX_QUESTIONS_PER_CHUNK = 10

# Minimalan broj razlicitih tipova entiteta za instanciranje
MIN_ENTITY_TYPES = 2


# =====================================================================
# UCITAVANJE
# =====================================================================

def load_templates(path: Path) -> list[dict]:
    templates = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                templates.append(json.loads(line))
    return templates


def load_entities(path: Path) -> list[dict]:
    entities = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entities.append(json.loads(line))
    return entities


# =====================================================================
# DEDUPLIKACIJA
# =====================================================================

def normalize_query_key(query: str) -> str:
    """
    Normalizuje query za deduplikaciju.
    - lowercase
    - ukloni interpunkciju na kraju
    - ukloni visestruke razmake
    - trim
    """
    q = query.strip().lower()
    q = re.sub(r"[?!.,;:]+$", "", q)
    q = re.sub(r"\s+", " ", q)
    return q.strip()


def deduplicate_questions(questions: list[dict]) -> list[dict]:
    """
    Uklanja duplikate po normalizovanom query-ju.
    Zadrzava pitanje sa NAJVISE entiteta (bolji kontekst).
    """
    seen = {}  # {normalized_key: question}

    for q in questions:
        key = normalize_query_key(q["query"])
        if not key:
            continue

        if key not in seen:
            seen[key] = q
        else:
            # Zadrzi onaj sa vise entiteta
            existing = seen[key]
            if len(q.get("entities", {})) > len(existing.get("entities", {})):
                seen[key] = q

    return list(seen.values())


# =====================================================================
# INSTANCIRANJE
# =====================================================================

def find_placeholders(template: str) -> list[str]:
    return re.findall(r"\{(\w+)\}", template)


def can_instantiate(template: dict, entities: dict) -> bool:
    """Proverava da li chunk ima sve entitete potrebne za sablon."""
    requires = template.get("requires", [])
    if not requires:
        return False

    for req in requires:
        values = entities.get(req, [])
        if not values:
            return False
        has_valid = any(len(v) >= MIN_ENTITY_LEN for v in values)
        if not has_valid:
            return False

    return True


def instantiate_questions_for_chunk(
    chunk: dict,
    templates: list[dict],
) -> list[dict]:
    """Za jedan chunk, generisi sva moguca instancirana pitanja."""
    entities = chunk.get("entities", {})
    if not entities:
        return []

    entity_types_with_values = sum(
        1 for v in entities.values() if v and len(v) > 0
    )
    if entity_types_with_values < MIN_ENTITY_TYPES:
        return []

    questions = []

    for template in templates:
        if not can_instantiate(template, entities):
            continue

        placeholders = find_placeholders(template["template"])
        if not placeholders:
            continue

        placeholder_values = {}
        for ph in placeholders:
            vals = entities.get(ph, [])
            vals = [v for v in vals if v and len(v) >= MIN_ENTITY_LEN]
            if not vals:
                placeholder_values = {}
                break
            placeholder_values[ph] = vals[:3]

        if not placeholder_values:
            continue

        combos = _cartesian_limited(placeholder_values, max_combos=5)

        for combo in combos:
            try:
                query = template["template"].format(**combo)
            except (KeyError, IndexError):
                continue

            query = re.sub(r"\s+", " ", query).strip()

            if len(query) < 10:
                continue

            questions.append({
                "query": query,
                "template_id": template["id"],
                "intent": template["intent"],
                "entities": combo,
                "source": chunk.get("source"),
                "pdf_page": chunk.get("pdf_page"),
                "section_path": chunk.get("section_path", []),
                "section_ids": chunk.get("section_ids", []),
                "source_chunk": chunk.get("chunk_id"),
            })

    return questions[:MAX_QUESTIONS_PER_CHUNK]


def _cartesian_limited(placeholder_values: dict, max_combos: int = 5) -> list[dict]:
    """Ograniceni cartesian product."""
    placeholders = list(placeholder_values.keys())
    if not placeholders:
        return []

    results = []

    def _recurse(idx, current):
        if len(results) >= max_combos:
            return
        if idx == len(placeholders):
            results.append(dict(current))
            return

        ph = placeholders[idx]
        for val in placeholder_values[ph]:
            if len(results) >= max_combos:
                return
            current[ph] = val
            _recurse(idx + 1, current)
            del current[ph]

    _recurse(0, {})
    return results


# =====================================================================
# GLAVNI TOK
# =====================================================================

def process_file(
    entities_path: Path,
    templates: list[dict],
    output_path: Path,
) -> dict:
    """Obradi jedan dokument: generisi pitanja, deduplikuj, sacuvaj."""
    print(f"\n=== {entities_path.name} ===")

    chunks = load_entities(entities_path)
    print(f"  Ucitano chunkova: {len(chunks)}")

    # 1) Generisi sva pitanja
    all_questions = []
    for chunk in tqdm(chunks, desc=f"  {entities_path.stem[:30]}"):
        questions = instantiate_questions_for_chunk(chunk, templates)
        all_questions.extend(questions)

    raw_count = len(all_questions)
    print(f"  Pitanja (pre deduplikacije): {raw_count}")

    # 2) Deduplikacija
    all_questions = deduplicate_questions(all_questions)
    print(f"  Pitanja (posle deduplikacije): {len(all_questions)}")
    print(f"  Uklonjeno duplikata: {raw_count - len(all_questions)}")

    # 3) Sacuvaj
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for q in all_questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    print(f"  Sacuvano: {output_path}")

    # 4) Statistika
    stats = {
        "total_chunks": len(chunks),
        "raw_questions": raw_count,
        "final_questions": len(all_questions),
        "duplicates_removed": raw_count - len(all_questions),
        "by_template": Counter(q["template_id"] for q in all_questions),
    }

    return stats


def main():
    if not TEMPLATES_PATH.exists():
        print(f"Nema: {TEMPLATES_PATH}")
        return

    if not ENTITIES_DIR.exists():
        print(f"Nema: {ENTITIES_DIR}")
        print("Pokreni prvo: python src/normalize_entities.py")
        return

    print(f"Ucitavam sablone: {TEMPLATES_PATH}")
    templates = load_templates(TEMPLATES_PATH)
    print(f"  Sablona: {len(templates)}")

    entity_files = sorted(ENTITIES_DIR.glob("*.jsonl"))
    if not entity_files:
        print(f"Nema .jsonl u {ENTITIES_DIR}")
        return

    print(f"\nNadjeno {len(entity_files)} dokumenata.")

    all_stats = {}

    for entities_path in entity_files:
        output_path = OUTPUT_DIR / entities_path.name
        stats = process_file(entities_path, templates, output_path)
        all_stats[entities_path.stem] = stats

    # Finalna statistika
    print(f"\n{'=' * 60}")
    print(f"GOTOVO")
    print(f"{'=' * 60}")

    total_raw = 0
    total_final = 0
    total_removed = 0
    total_by_template = Counter()

    for source, stats in all_stats.items():
        print(f"\n{source}:")
        print(f"  Chunkova:                  {stats['total_chunks']}")
        print(f"  Pitanja (pre):             {stats['raw_questions']}")
        print(f"  Pitanja (posle):           {stats['final_questions']}")
        print(f"  Uklonjeno duplikata:       {stats['duplicates_removed']}")

        if stats["by_template"]:
            print(f"  Top 5 sablona:")
            for tid, n in stats["by_template"].most_common(5):
                print(f"    {tid:30s}: {n}")
            total_by_template.update(stats["by_template"])

        total_raw += stats["raw_questions"]
        total_final += stats["final_questions"]
        total_removed += stats["duplicates_removed"]

    print(f"\n{'=' * 60}")
    print(f"UKUPNO:")
    print(f"  Pitanja (pre deduplikacije):    {total_raw}")
    print(f"  Pitanja (posle deduplikacije):  {total_final}")
    print(f"  Uklonjeno duplikata:            {total_removed}")
    print(f"{'=' * 60}")

    print(f"\nTop 10 sablona (svi dokumenti):")
    for tid, n in total_by_template.most_common(10):
        print(f"  {tid:35s}: {n}")

    print(f"\nIzlaz: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()