"""
Faza 2.6 — mapiranje naslova iz sadrzaja na PDF strane — MULTI-PDF.

Za svaki .toc.json u data/structure/, trazi naslove u tekstu (extracted/*.jsonl)
i upisuje pdf_page. Rezultat: .structure.json po dokumentu.

PRETRAGA (sekvencijalna, po redosledu naslova iz sadrzaja):
  - Preskacemo TOC strane.
  - CETIRI PROLAZA:
      1) TACNO poklapanje.
      2) PREFIX poklapanje.
      3) WORD OVERLAP.
      4) FUZZY.

NORMALIZACIJA:
  - Uklanja markdown zaglavlja, tackice, visak razmaka.
  - Uklanja tacku posle markera.
  - UNIFIKUJE homoglife (cirilica/latinica).

Izvor:  data/structure/*.toc.json  +  data/extracted/*.jsonl
Izlaz:  data/structure/*.structure.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json
import re
from difflib import SequenceMatcher


FUZZY_THRESHOLD_SHORT = 0.90
FUZZY_THRESHOLD_LONG = 0.85
SHORT_TITLE_LENGTH = 20

WORD_OVERLAP_THRESHOLD = 0.70
WORD_OVERLAP_MAX_LINE_LEN = 100
SINGLE_WORD_MAX_LINE_LEN = 40


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


def make_target(sec: dict) -> str:
    id_ = sec.get("id") or ""
    title = sec.get("title") or ""
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
    sections = toc_data["sections"]
    toc_page_nums = set(toc_data.get("toc_pages", []))

    targets = []
    for i, sec in enumerate(sections):
        norm = make_target(sec)
        if norm:
            targets.append((norm, i))

    results = {}
    target_idx = 0

    for page in pages:
        if target_idx >= len(targets):
            break
        page_num = page["page"]
        if page_num in toc_page_nums:
            continue
        lines = [l.strip() for l in page["text"].split("\n") if l.strip()]
        while target_idx < len(targets):
            target_norm, target_sec_idx = targets[target_idx]
            found = find_heading_in_page(lines, target_norm)
            if found is not None:
                results[target_sec_idx] = page_num
                target_idx += 1
            else:
                break

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
    return toc_data


# --- Main: prolaz kroz sve ---

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
        print(f"  Sacuvano:       {out_path}\n")


if __name__ == "__main__":
    main()
