"""
Faza 2.6 — mapiranje naslova iz sadrzaja na PDF strane — MULTI-PDF.

Kljucno:
  - Preskacemo TOC strane.
  - Sekvencijalna pretraga po redosledu naslova iz sadrzaja.
  - SKIP LOGIKA: ako target ne prodje MAX_PAGES_PER_TARGET strana
    zaredom, preskacemo ga i idemo na sledeci. Time se sprecava
    blokada celog pipeline-a zbog jednog nenadjenog naslova
    (npr. naslov iz sadrzaja koji u tekstu izgleda drugacije).

Cetiri prolaza pretrage (od najsigurnijeg ka najlabavijem):
  1) TACNO poklapanje
  2) PREFIX
  3) WORD OVERLAP
  4) FUZZY

Izvor:  data/structure/*.toc.json  +  data/extracted/*.jsonl
Izlaz:  data/structure/*.structure.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json
import re
from difflib import SequenceMatcher


# --- Fuzzy pragovi ---
FUZZY_THRESHOLD_SHORT = 0.90
FUZZY_THRESHOLD_LONG = 0.85
SHORT_TITLE_LENGTH = 20

# --- Word overlap pragovi ---
WORD_OVERLAP_THRESHOLD = 0.70
WORD_OVERLAP_MAX_LINE_LEN = 100
SINGLE_WORD_MAX_LINE_LEN = 40

# --- Skip logika ---
# Ako target ne prodje ovoliko strana zaredom, preskacemo ga.
# 10 strana je kompromis: dovoljno da nadjemo naslov koji postoji,
# ali ne previse da blokiramo ceo dokument.
MAX_PAGES_PER_TARGET = 10


# --- Homoglifi ---
_CYR_TO_LAT_MAP = {
    "а": "a", "е": "e", "о": "o", "ј": "j", "с": "c",
    "р": "p", "к": "k", "м": "m", "т": "t", "н": "n",
    "и": "u", "в": "b", "х": "x",
    "А": "A", "Е": "E", "О": "O", "Ј": "J", "С": "C",
    "Р": "P", "К": "K", "М": "M", "Т": "T", "Н": "N",
    "И": "U", "В": "B", "Х": "X",
}
_HOMOGLYPH_TABLE = str.maketrans(_CYR_TO_LAT_MAP)


def unify_homoglyphs(text: str) -> str:
    return text.translate(_HOMOGLYPH_TABLE)


def normalize(text: str) -> str:
    s = text.strip()
    s = re.sub(r"^#+\s*", "", s)
    s = re.sub(r"\.{2,}.*$", "", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^([IVXivx]+|\d+|[a-zA-Z])\.\s+", r"\1 ", s)
    s = re.sub(r"[.,;:!?]+$", "", s)
    s = unify_homoglyphs(s)
    return s.lower().strip()


def variants(norm_text: str):
    yield norm_text
    no_marker = re.sub(
        r"^(i{1,3}|iv|v|vi{0,3}|ix|x|\d{1,3}|[a-z])\s+",
        "", norm_text,
    )
    if no_marker and no_marker != norm_text:
        yield no_marker
    no_poglavlje = re.sub(r"^пoглabљe\s+", "", norm_text)
    if no_poglavlje and no_poglavlje != norm_text:
        yield no_poglavlje


def make_target(sec: dict) -> str:
    marker_text = sec.get("marker_text") or ""
    id_ = sec.get("id") or ""
    title = sec.get("title") or ""
    if marker_text:
        return normalize(f"{marker_text} {title}")
    if id_:
        return normalize(f"{id_}. {title}")
    return normalize(title)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def get_threshold(target: str) -> float:
    if len(target) < SHORT_TITLE_LENGTH:
        return FUZZY_THRESHOLD_SHORT
    return FUZZY_THRESHOLD_LONG


def _is_prefix_match(norm_line: str, target: str) -> bool:
    if len(target) < 10:
        return False
    if not norm_line.startswith(target):
        return False
    if len(norm_line) == len(target):
        return True
    return norm_line[len(target)] == " "


def _words_overlap(target: str, line: str) -> float:
    target_words = set(target.split())
    line_words = set(line.split())
    if not target_words:
        return 0.0
    common = target_words & line_words
    return len(common) / len(target_words)


def _is_word_overlap_match(norm_line: str, target: str) -> bool:
    target_words = target.split()
    line_words = norm_line.split()
    if len(norm_line) > WORD_OVERLAP_MAX_LINE_LEN:
        return False
    if norm_line.rstrip().endswith("."):
        return False
    if len(target_words) == 1:
        if len(norm_line) > SINGLE_WORD_MAX_LINE_LEN:
            return False
        return target_words[0] in line_words
    overlap = _words_overlap(target, norm_line)
    return overlap >= WORD_OVERLAP_THRESHOLD


def find_heading_in_page(lines: list[str], target_norm: str) -> int | None:
    targets = list(variants(target_norm))

    # 1) TACNO
    for i, line in enumerate(lines):
        norm_line = normalize(line)
        if norm_line in targets:
            return i
        if i + 1 < len(lines):
            combined = normalize(line + " " + lines[i + 1])
            if combined in targets:
                return i

    # 2) PREFIX
    for i, line in enumerate(lines):
        norm_line = normalize(line)
        for target in targets:
            if _is_prefix_match(norm_line, target):
                return i
        if i + 1 < len(lines):
            combined = normalize(line + " " + lines[i + 1])
            for target in targets:
                if _is_prefix_match(combined, target):
                    return i

    # 3) WORD OVERLAP
    for i, line in enumerate(lines):
        norm_line = normalize(line)
        for target in targets:
            if _is_word_overlap_match(norm_line, target):
                return i
        if i + 1 < len(lines):
            combined = normalize(line + " " + lines[i + 1])
            for target in targets:
                if _is_word_overlap_match(combined, target):
                    return i

    # 4) FUZZY
    threshold = get_threshold(target_norm)
    for i, line in enumerate(lines):
        norm_line = normalize(line)
        for target in targets:
            if similarity(norm_line, target) >= threshold:
                return i
        if i + 1 < len(lines):
            combined = normalize(line + " " + lines[i + 1])
            for target in targets:
                if similarity(combined, target) >= threshold:
                    return i

    return None


def map_pages(toc_data: dict, pages: list[dict]) -> dict:
    """
    Mapira naslove iz sadrzaja na PDF strane.

    SKIP LOGIKA: ako target ne prodje MAX_PAGES_PER_TARGET strana
    zaredom, preskacemo ga i idemo na sledeci.
    """
    sections = toc_data["sections"]
    toc_page_nums = set(toc_data.get("toc_pages", []))

    targets = []
    for i, sec in enumerate(sections):
        norm = make_target(sec)
        if norm:
            targets.append((norm, i))

    results = {}
    skipped = []                     # (idx, target_norm, pages_tried)
    target_idx = 0
    pages_tried_for_target = 0       # koliko strana smo probali za trenutni target

    for page in pages:
        if target_idx >= len(targets):
            break

        page_num = page["page"]

        if page_num in toc_page_nums:
            continue

        lines = [l.strip() for l in page["text"].split("\n") if l.strip()]

        # Dokle god nalazimo uzastopne targete na ovoj strani
        while target_idx < len(targets):
            target_norm, target_sec_idx = targets[target_idx]
            found = find_heading_in_page(lines, target_norm)

            if found is not None:
                results[target_sec_idx] = page_num
                target_idx += 1
                pages_tried_for_target = 0
            else:
                # Nije nadjen na ovoj strani — broji stranu
                pages_tried_for_target += 1

                if pages_tried_for_target >= MAX_PAGES_PER_TARGET:
                    # Skip: preskoci target
                    skipped.append({
                        "index": target_sec_idx,
                        "title": sections[target_sec_idx].get("title", ""),
                        "target_norm": target_norm,
                        "pages_tried": pages_tried_for_target,
                    })
                    target_idx += 1
                    pages_tried_for_target = 0
                    continue  # probaj sledeci target na istoj strani
                else:
                    break  # predji na sledecu stranu

    not_found = []
    for i, sec in enumerate(sections):
        if i in results:
            sec["pdf_page"] = results[i]
        else:
            sec["pdf_page"] = None
            not_found.append(sec["title"])

    toc_data["sections"] = sections
    toc_data["headings_total"] = len(sections)
    toc_data["headings_found"] = len(results)
    toc_data["headings_not_found"] = not_found
    toc_data["headings_skipped"] = skipped
    return toc_data


def main():
    structure_dir = Path("data/structure")
    extracted_dir = Path("data/extracted")

    toc_files = sorted(structure_dir.glob("*.toc.json"))
    if not toc_files:
        print(f"Nema .toc.json u {structure_dir}. Pokreni prvo toc.py.")
        return

    print(f"Nadjeno {len(toc_files)} toc fajlova.\n")

    for toc_path in toc_files:
        stem = toc_path.name.replace(".toc.json", "")
        extracted_path = extracted_dir / f"{stem}.jsonl"
        out_path = structure_dir / f"{stem}.structure.json"

        if not extracted_path.exists():
            print(f"  PRESKACEM {stem}: nema {extracted_path}")
            continue

        print(f"=== {stem} ===")
        toc_data = json.load(open(toc_path, encoding="utf-8"))
        pages = [json.loads(l) for l in open(extracted_path, encoding="utf-8")]

        result = map_pages(toc_data, pages)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"  Ukupno naslova: {result['headings_total']}")
        print(f"  Pronadjeno:     {result['headings_found']}")
        print(f"  Nije nadjeno:   {len(result['headings_not_found'])}")
        print(f"  Preskoceno:     {len(result['headings_skipped'])}")
        print(f"  Sacuvano:       {out_path}")

        # Prikazi prvih 5 preskocenih
        if result['headings_skipped']:
            print(f"\n  Prvih 5 preskocenih naslova:")
            for s in result['headings_skipped'][:5]:
                print(f"    - {s['title'][:70]!r}")
        print()


if __name__ == "__main__":
    main()