"""
Parsiranje sadrzaja (table of contents) iz PDF-a — MULTI-PDF.

Cuva se i `marker_text` (npr. "ПОГЛАВЉЕ 1.", "1.", "I.") za tacno
poklapanje u map_pages.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json
import re

from config import (
    MAX_LOOKAHEAD,
    SKIP_END_PAGES,
    MIN_TOC_LINES,
    TOC_RATIO_WITH_TITLE,
    TOC_RATIO_WITHOUT_TITLE,
    MAX_TOC_LINE_LENGTH,
)

from patterns import (
    RE_SADRZAJ,
    RE_LITERATURA,
    RE_PAGE_NUMBER,
    RE_NONALNUM_MARKER,
    ALNUM_FAMILIES,
    detect_marker,
    detect_style_family,
)

try:
    from toc_locations import TOC_LOCATIONS
except ImportError:
    TOC_LOCATIONS = {}


TOC_RATIO_CONTINUATION = 0.50
TOC_MIN_FAMILIES_CONTINUATION = 1

FALLBACK_MIN_LINES = 3
FALLBACK_MIN_DOT_LINES = 2
FALLBACK_MIN_HEADING_RATIO = 0.70
FALLBACK_MAX_SENTENCES = 1
FALLBACK_MIN_LINES_WEAK = 40

RE_TOC_SUFFIX_NAME = re.compile(r"_toc_(\d+(?:-\d+)?)\.pdf$", re.IGNORECASE)


# =====================================================================
# 0) EKSPLICITNA LOKACIJA TOC-a
# =====================================================================

def parse_toc_location_from_name(filename: str) -> list[int] | None:
    match = RE_TOC_SUFFIX_NAME.search(filename)
    if not match:
        return None
    spec = match.group(1)
    if "-" in spec:
        start, end = spec.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(spec)]


def get_explicit_toc_pages(stem: str, pdfs_dir: Path = Path("pdfs")) -> list[int] | None:
    for pdf_path in pdfs_dir.glob("*.pdf"):
        clean_name = RE_TOC_SUFFIX_NAME.sub(".pdf", pdf_path.name)
        clean_stem = clean_name.replace(".pdf", "")
        if clean_stem == stem:
            loc = parse_toc_location_from_name(pdf_path.name)
            if loc:
                return loc
    if stem in TOC_LOCATIONS:
        return TOC_LOCATIONS[stem]
    return None


# =====================================================================
# 1) DETEKCIJA FAMILIJA
# =====================================================================

def detect_family(text: str, nonalnum_registry: dict | None = None
                   ) -> tuple[str, str | None, str, str | None, str | None, str]:
    """
    Vraca (familija, id, naslov, style, marker, marker_text).
    """
    marker, id_, title, marker_text = detect_marker(text, nonalnum_registry)
    style = detect_style_family(text)

    if style == "upper":
        family = "upper"
    elif style in ("mixed", "lower"):
        if marker:
            family = f"{style}_{marker}"
        else:
            family = style
    else:
        if marker:
            family = marker
        else:
            family = "bez-markera"

    return family, id_, title, style, marker, marker_text


# =====================================================================
# 2) OSNOVNE PROVERE
# =====================================================================

def is_toc_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if len(s) > MAX_TOC_LINE_LENGTH:
        return False

    for _, pattern, _, _ in ALNUM_FAMILIES:
        if pattern.match(s):
            return True

    if RE_NONALNUM_MARKER.match(s):
        return True

    if len(s) < 120 and not s.endswith((".", "!", "?")):
        if not RE_PAGE_NUMBER.match(s):
            return True

    return False


def _looks_like_impressum(page_text: str) -> bool:
    upper = page_text.upper()
    markers = ["ISBN", "CIP -", "COBISS", "ТИРАЖ", "ШТАМПА", "ИЗДАВАЧ", "ЛЕКТОР"]
    return any(m in upper for m in markers)


def _structure_stats(lines: list[str]) -> tuple[float, int]:
    toc_count = 0
    distinct_families = set()
    for line in lines:
        if is_toc_line(line):
            toc_count += 1
            marker, _, _, _ = detect_marker(line)
            if marker:
                distinct_families.add(marker)
    ratio = toc_count / len(lines) if lines else 0.0
    return ratio, len(distinct_families)


# =====================================================================
# 3) PRIMARNA DETEKCIJA
# =====================================================================

def is_toc_page_with_title(page_text: str) -> bool:
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    if len(lines) < MIN_TOC_LINES:
        return False
    if not RE_SADRZAJ.match(lines[0]):
        return False
    ratio, _ = _structure_stats(lines)
    return ratio >= TOC_RATIO_WITH_TITLE


def is_toc_page_without_title(page_text: str) -> bool:
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    if len(lines) < MIN_TOC_LINES:
        return False
    if _looks_like_impressum(page_text):
        return False
    ratio, n_families = _structure_stats(lines)
    return (ratio >= TOC_RATIO_WITHOUT_TITLE and n_families >= 2)


def is_toc_page_continuation(page_text: str) -> bool:
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    if len(lines) < 2:
        return False
    if _looks_like_impressum(page_text):
        return False
    ratio, n_families = _structure_stats(lines)
    return (ratio >= TOC_RATIO_CONTINUATION
            and n_families >= TOC_MIN_FAMILIES_CONTINUATION)


# =====================================================================
# 4) FALLBACK DETEKCIJA
# =====================================================================

def _count_sentences(text: str) -> int:
    t = re.sub(r"\.{2,}", "", text)
    t = re.sub(
        r"^\s*(\d+\.|[IVX]+\.|ПОГЛАВЉЕ\s+\d+\.|Поглавље\s+\d+\.)\s*",
        "", t, flags=re.MULTILINE | re.IGNORECASE,
    )
    matches = re.findall(r"[.!?]\s+[А-ШЂЈЉЊЋЏA-Z]", t, re.UNICODE)
    return len(matches)


def is_toc_page_fallback(page_text: str) -> bool:
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    if len(lines) < FALLBACK_MIN_LINES:
        return False
    if _looks_like_impressum(page_text):
        return False

    dot_lines = sum(1 for l in lines if re.search(r"\.{4,}", l))
    if dot_lines >= FALLBACK_MIN_DOT_LINES:
        if _count_sentences(page_text) > FALLBACK_MAX_SENTENCES:
            return False
        return True

    if len(lines) < FALLBACK_MIN_LINES_WEAK:
        return False

    heading_count = 0
    for l in lines:
        s = l.strip()
        if len(s) > 150:
            continue
        if s.endswith((".", "!", "?")):
            continue
        if re.search(r"[.!?]\s+[А-ШЂЈЉЊЋЏA-Z]", s, re.UNICODE):
            continue
        heading_count += 1

    if (heading_count / len(lines)) < FALLBACK_MIN_HEADING_RATIO:
        return False
    if _count_sentences(page_text) > FALLBACK_MAX_SENTENCES:
        return False
    return True


# =====================================================================
# 5) PRETRAGA TOC STRANA
# =====================================================================

def _find_toc_in_slice(pages_slice: list[dict],
                       reversed_order: bool = False,
                       use_fallback: bool = False) -> list[dict]:
    iterator = reversed(pages_slice) if reversed_order else iter(pages_slice)
    toc_pages = []
    started = False

    for p in iterator:
        text = p["text"]
        if started:
            is_toc = (is_toc_page_continuation(text)
                      or is_toc_page_with_title(text))
        else:
            if use_fallback:
                is_toc = is_toc_page_fallback(text)
            else:
                is_toc = (is_toc_page_with_title(text)
                          or is_toc_page_without_title(text))

        if is_toc:
            if reversed_order:
                toc_pages.insert(0, p)
            else:
                toc_pages.append(p)
            started = True
        else:
            if started:
                break

    return toc_pages


def find_toc_pages(pages: list[dict],
                    explicit_pages: list[int] | None = None) -> tuple[list[dict], str]:
    n = len(pages)
    if n == 0:
        return [], "nije_nadjen"

    if explicit_pages:
        toc_pages = [p for p in pages if p["page"] in explicit_pages]
        if toc_pages:
            return toc_pages, "explicit"

    lookahead = min(MAX_LOOKAHEAD, max(1, n // 3))

    toc_pages = _find_toc_in_slice(pages[:lookahead], False, False)
    if toc_pages:
        return toc_pages, "pocetak"

    end_start = max(0, n - lookahead)
    end_end = max(0, n - SKIP_END_PAGES)
    end_candidates = pages[end_start:end_end]

    toc_pages = _find_toc_in_slice(end_candidates, True, False)
    if toc_pages:
        return toc_pages, "kraj"

    print("  Primarna pretraga nije nasla sadrzaj. Pokrecem fallback...")
    toc_pages = _find_toc_in_slice(pages[:lookahead], False, True)
    if toc_pages:
        return toc_pages, "pocetak-fallback"

    toc_pages = _find_toc_in_slice(end_candidates, True, True)
    if toc_pages:
        return toc_pages, "kraj-fallback"

    return [], "nije_nadjen"


# =====================================================================
# 6) CISCENJE I SPAJANJE
# =====================================================================

def clean_toc_line(line: str) -> tuple[str, int | None]:
    stripped = line.strip()

    m = re.search(r"\.{2,}\s*(\d{1,4})?\s*$", stripped)
    if m:
        text = stripped[:m.start()].rstrip()
        page = int(m.group(1)) if m.group(1) else None
        return text, page

    m = re.search(r"\s{2,}(\d{1,4})\s*$", stripped)
    if m:
        text = stripped[:m.start()].rstrip()
        return text, int(m.group(1))

    return stripped, None


def _should_merge(prev_text: str, text: str,
                  prev_marker: str | None, cur_marker: str | None) -> bool:
    if cur_marker is not None:
        return False
    if prev_text.rstrip().endswith((".", "!", "?")):
        return False
    if text and text[0].islower():
        return True
    if prev_text.rstrip().endswith((",", ";", ":")):
        return True

    prev_style = detect_style_family(prev_text)
    cur_style = detect_style_family(text)
    if prev_style and cur_style and prev_style != cur_style:
        return False

    return False


def _should_merge_context(prev_text: str, text: str,
                           all_lines: list[tuple],
                           idx: int) -> bool:
    prev_marker, _, _, _ = detect_marker(prev_text)
    cur_marker, _, _, _ = detect_marker(text)

    if prev_marker is None:
        return False
    if cur_marker is not None:
        return False
    if idx + 1 >= len(all_lines):
        return False

    next_text, _, _ = all_lines[idx + 1]
    next_marker, _, _, _ = detect_marker(next_text)

    if next_marker != prev_marker:
        return False

    if prev_text.rstrip().endswith((".", "!", "?")):
        return False

    if text and text[0].islower():
        return True
    if prev_text.rstrip().endswith((",", ";", ":")):
        return True
    if prev_marker == "rimski":
        cur_style = detect_style_family(text)
        if cur_style == "upper" and len(text) < 60:
            return True

    return False


def merge_continuation_lines(lines: list[tuple]) -> list[tuple]:
    merged = []
    i = 0
    n = len(lines)

    while i < n:
        text, printed_page, pdf_page = lines[i]

        if merged:
            prev_text, prev_page, prev_pdf = merged[-1]

            if _should_merge_context(prev_text, text, lines, i):
                merged[-1] = (
                    prev_text + " " + text,
                    printed_page if printed_page is not None else prev_page,
                    prev_pdf,
                )
                i += 1
                continue

            prev_marker, _, _, _ = detect_marker(prev_text)
            cur_marker, _, _, _ = detect_marker(text)
            if _should_merge(prev_text, text, prev_marker, cur_marker):
                merged[-1] = (
                    prev_text + " " + text,
                    printed_page if printed_page is not None else prev_page,
                    prev_pdf,
                )
                i += 1
                continue

        merged.append((text, printed_page, pdf_page))
        i += 1

    return merged


# =====================================================================
# 7) GLAVNA FUNKCIJA
# =====================================================================

def parse_toc(pages: list[dict],
              explicit_pages: list[int] | None = None) -> dict:
    toc_pages, location = find_toc_pages(pages, explicit_pages=explicit_pages)

    if not toc_pages:
        return {
            "toc_location": "nije_nadjen",
            "toc_pages": [],
            "families_order": [],
            "family_to_level": {},
            "sections": [],
            "warning": "Sadrzaj nije pronadjen.",
        }

    cleaned_lines = []
    for p in toc_pages:
        for line in p["text"].split("\n"):
            if not line.strip():
                continue
            text, printed_page = clean_toc_line(line)
            if not text:
                continue
            if RE_PAGE_NUMBER.match(text):
                continue
            if RE_SADRZAJ.match(text):
                continue
            if RE_LITERATURA.match(text):
                if printed_page is None:
                    continue
            cleaned_lines.append((text, printed_page, p["page"]))

    cleaned_lines = merge_continuation_lines(cleaned_lines)

    nonalnum_registry = {}
    entries = []

    for text, printed_page, pdf_page in cleaned_lines:
        family, id_, title, style, marker, marker_text = detect_family(
            text, nonalnum_registry
        )
        entries.append({
            "family": family,
            "style": style,
            "marker": marker,
            "marker_text": marker_text,   # ← NOVO
            "id": id_,
            "title": title,
            "printed_page": printed_page,
        })

    family_to_level = {}
    seen_families = []
    next_level = 1

    for e in entries:
        fam = e["family"]
        if fam not in family_to_level:
            family_to_level[fam] = next_level
            seen_families.append(fam)
            next_level += 1
        e["level"] = family_to_level[fam]

    return {
        "toc_location": location,
        "toc_pages": [p["page"] for p in toc_pages],
        "families_order": seen_families,
        "family_to_level": family_to_level,
        "sections": entries,
    }


# =====================================================================
# 8) MAIN
# =====================================================================

def main():
    extracted_dir = Path("data/extracted")
    output_dir = Path("data/structure")
    output_dir.mkdir(parents=True, exist_ok=True)

    jsonl_files = sorted(extracted_dir.glob("*.jsonl"))
    if not jsonl_files:
        print(f"Nema .jsonl fajlova u {extracted_dir}")
        return

    print(f"Nadjeno {len(jsonl_files)} dokumenata.\n")

    for jsonl_path in jsonl_files:
        stem = jsonl_path.stem
        print(f"=== {stem} ===")

        pages = [json.loads(l) for l in open(jsonl_path, encoding="utf-8")]

        explicit = get_explicit_toc_pages(stem)
        if explicit:
            print(f"  Eksplicitna TOC lokacija: {explicit}")

        result = parse_toc(pages, explicit_pages=explicit)

        out_path = output_dir / f"{stem}.toc.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"  Location:       {result['toc_location']}")
        print(f"  TOC strane:     {result['toc_pages']}")
        print(f"  Sekcija:        {len(result['sections'])}")
        print(f"  Familije:       {result['families_order']}")
        print(f"  Familija->nivo: {result['family_to_level']}")
        print(f"  Sacuvano:       {out_path}\n")


if __name__ == "__main__":
    main()