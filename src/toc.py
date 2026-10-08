"""
Parsiranje sadrzaja (table of contents) iz PDF-a — MULTI-PDF.

DETEKCIJA TOC LOKACIJE — po prioritetu:

  1) EKSPLICITNO (najvisi prioritet):
     - Iz imena PDF-a: "..._toc_X-Y.pdf" ili "..._toc_X.pdf"
     - Iz src/toc_locations.py (recnik TOC_LOCATIONS)

  2) PRIMARNA (postojeca logika):
     - is_toc_page_with_title:   prvi red je RE_SADRZAJ, bar 70% TOC redova.
     - is_toc_page_without_title: bar 95% TOC redova + bar 2 familije.
     - is_toc_page_continuation:  bar 50% TOC redova (nastavak).

  3) FALLBACK (ako primarna ne nadje nista):
     - is_toc_page_fallback: tackice 4+ u nizu ILI 70% naslova bez tacke.

IZVLACENJE NASLOVA:
  - Uklanjamo tackice i sve posle njih (ako ih ima), sa ili bez broja.
  - Spajamo nastavke naslova u dva reda.
  - Dinamicki dodeljujemo nivoe po redosledu pojavljivanja familija.

Izvor:  data/extracted/*.jsonl
Izlaz:  data/structure/*.toc.json
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
)

try:
    from toc_locations import TOC_LOCATIONS
except ImportError:
    TOC_LOCATIONS = {}


# --- Pragovi za primarnu detekciju ---
TOC_RATIO_CONTINUATION = 0.50
TOC_MIN_FAMILIES_CONTINUATION = 1

# --- Pragovi za fallback ---
FALLBACK_MIN_LINES = 3
FALLBACK_MIN_DOT_LINES = 2
FALLBACK_MIN_HEADING_RATIO = 0.70
FALLBACK_MAX_SENTENCES = 1
FALLBACK_MIN_LINES_WEAK = 40  # za slabi signal (bez tackica)

# --- Regex za TOC lokaciju u imenu fajla ---
RE_TOC_SUFFIX_NAME = re.compile(r"_toc_(\d+(?:-\d+)?)\.pdf$", re.IGNORECASE)
RE_TOC_SUFFIX_STEM = re.compile(r"_toc_\d+(?:-\d+)?$", re.IGNORECASE)


# =====================================================================
# 0) EKSPLICITNA LOKACIJA TOC-a
# =====================================================================

def parse_toc_location_from_name(filename: str) -> list[int] | None:
    """Parsira TOC lokaciju iz imena PDF-a."""
    match = RE_TOC_SUFFIX_NAME.search(filename)
    if not match:
        return None
    spec = match.group(1)
    if "-" in spec:
        start, end = spec.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(spec)]


def get_explicit_toc_pages(stem: str, pdfs_dir: Path = Path("pdfs")) -> list[int] | None:
    """
    Vraca eksplicitnu TOC lokaciju za dokument.

    Prioritet:
      1. Ime PDF-a (_toc_X-Y.pdf)
      2. TOC_LOCATIONS recnik

    Vraca listu strana ili None.
    """
    # 1) Iz imena PDF-a
    for pdf_path in pdfs_dir.glob("*.pdf"):
        # Proveri da li PDF odgovara stem-u (bez _toc_X-Y)
        clean_name = RE_TOC_SUFFIX_NAME.sub(".pdf", pdf_path.name)
        clean_stem = clean_name.replace(".pdf", "")
        if clean_stem == stem:
            loc = parse_toc_location_from_name(pdf_path.name)
            if loc:
                return loc

    # 2) Iz recnika
    if stem in TOC_LOCATIONS:
        return TOC_LOCATIONS[stem]

    return None


# =====================================================================
# 1) DETEKCIJA FAMILIJA
# =====================================================================

def detect_family(text: str, nonalnum_registry: dict | None = None) -> tuple[str | None, str | None, str]:
    """Vraca (familija, id, naslov)."""
    for fam_name, pattern, n_groups in ALNUM_FAMILIES:
        m = pattern.match(text)
        if m:
            if n_groups >= 2:
                return fam_name, m.group(1), m.group(2).strip()
            else:
                return fam_name, None, m.group(1).strip()

    m = RE_NONALNUM_MARKER.match(text)
    if m:
        marker = m.group(1)
        title = m.group(2).strip()
        fam_name = f"nonAlnum_{marker}"
        if nonalnum_registry is not None:
            if marker not in nonalnum_registry:
                nonalnum_registry[marker] = fam_name
            else:
                fam_name = nonalnum_registry[marker]
        return fam_name, None, title

    return None, None, text


# =====================================================================
# 2) OSNOVNE PROVERE
# =====================================================================

def is_toc_line(line: str) -> bool:
    """Vraca True ako red lici na stavku sadrzaja."""
    s = line.strip()
    if not s:
        return False
    if len(s) > MAX_TOC_LINE_LENGTH:
        return False

    for _, pattern, _ in ALNUM_FAMILIES:
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
            fam, _, _ = detect_family(line)
            if fam is not None:
                distinct_families.add(fam)
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
    """
    Broji recenice u tekstu.
    Iskljucuje numeraciju na pocetku reda i tackice (...).
    """
    t = re.sub(r"\.{2,}", "", text)
    # Ukloni numeraciju na pocetku reda (1., I., ПОГЛАВЉЕ 1.)
    t = re.sub(
        r"^\s*(\d+\.|[IVX]+\.|ПОГЛАВЉЕ\s+\d+\.|Поглавље\s+\d+\.)\s*",
        "",
        t, flags=re.MULTILINE | re.IGNORECASE,
    )
    matches = re.findall(r"[.!?]\s+[А-ШЂЈЉЊЋЏA-Z]", t, re.UNICODE)
    return len(matches)


def is_toc_page_fallback(page_text: str) -> bool:
    """
    Rezervna detekcija sadrzaja.

    Jaki signal: bar 2 reda sa 4+ tacke u nizu.
    Slabi signal: bar FALLBACK_MIN_LINES_WEAK redova (40) i 70% naslova.
    """
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    if len(lines) < FALLBACK_MIN_LINES:
        return False
    if _looks_like_impressum(page_text):
        return False

    # Jaki signal: tackice
    dot_lines = sum(1 for l in lines if re.search(r"\.{4,}", l))
    if dot_lines >= FALLBACK_MIN_DOT_LINES:
        if _count_sentences(page_text) > FALLBACK_MAX_SENTENCES:
            return False
        return True

    # Slabi signal: zahteva bar 40 redova
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
    """
    Vraca (toc_pages, gde_je_nadjen).

    Redosled:
      0) Ako explicit_pages — koristi ih direktno.
      1) Primarna: pocetak
      2) Primarna: kraj
      3) Fallback: pocetak
      4) Fallback: kraj
    """
    n = len(pages)
    if n == 0:
        return [], "nije_nadjen"

    # === 0) EKSPLICITNO ===
    if explicit_pages:
        toc_pages = [p for p in pages if p["page"] in explicit_pages]
        if toc_pages:
            return toc_pages, "explicit"

    lookahead = min(MAX_LOOKAHEAD, max(1, n // 3))

    # === 1) PRIMARNA: pocetak ===
    toc_pages = _find_toc_in_slice(
        pages[:lookahead], reversed_order=False, use_fallback=False,
    )
    if toc_pages:
        return toc_pages, "pocetak"

    # === 2) PRIMARNA: kraj ===
    end_slice_start = max(0, n - lookahead)
    end_slice_end = max(0, n - SKIP_END_PAGES)
    end_candidates = pages[end_slice_start:end_slice_end]

    toc_pages = _find_toc_in_slice(
        end_candidates, reversed_order=True, use_fallback=False,
    )
    if toc_pages:
        return toc_pages, "kraj"

    # === 3) FALLBACK: pocetak ===
    print("  Primarna pretraga nije nasla sadrzaj. Pokrecem fallback...")
    toc_pages = _find_toc_in_slice(
        pages[:lookahead], reversed_order=False, use_fallback=True,
    )
    if toc_pages:
        return toc_pages, "pocetak-fallback"

    # === 4) FALLBACK: kraj ===
    toc_pages = _find_toc_in_slice(
        end_candidates, reversed_order=True, use_fallback=True,
    )
    if toc_pages:
        return toc_pages, "kraj-fallback"

    return [], "nije_nadjen"


# =====================================================================
# 6) CISCENJE I SPAJANJE REDOVA
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


def _should_merge(prev_text, text, prev_fam, fam, max_line_len):
    if fam is not None:
        return False
    if prev_text.rstrip().endswith("."):
        return False
    if text and text[0].islower():
        return True
    if prev_text.rstrip().endswith(","):
        return True

    prev_is_upper = prev_text.isupper()
    cur_is_upper = text.isupper()
    if prev_is_upper != cur_is_upper:
        return False

    prev_len = len(prev_text)
    cur_len = len(text)
    prev_free_space = max_line_len - prev_len
    could_fit = (cur_len + 1) <= prev_free_space
    return not could_fit


def merge_continuation_lines(lines, max_line_len):
    merged = []
    for text, printed_page, pdf_page in lines:
        if merged:
            prev_text, prev_page, prev_pdf = merged[-1]
            prev_fam, _, _ = detect_family(prev_text)
            fam, _, _ = detect_family(text)
            if _should_merge(prev_text, text, prev_fam, fam, max_line_len):
                merged[-1] = (
                    prev_text + " " + text,
                    printed_page if printed_page is not None else prev_page,
                    prev_pdf,
                )
                continue
        merged.append((text, printed_page, pdf_page))
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

    if cleaned_lines:
        max_line_len = max(len(t) for t, _, _ in cleaned_lines)
    else:
        max_line_len = 80

    cleaned_lines = merge_continuation_lines(cleaned_lines, max_line_len)

    nonalnum_registry = {}
    seen_families = []
    entries = []

    for text, printed_page, pdf_page in cleaned_lines:
        fam, id_, title = detect_family(text, nonalnum_registry)
        if fam not in seen_families:
            seen_families.append(fam)
        fam_str = fam if fam is not None else "bez-markera"
        entries.append({
            "family": fam_str,
            "id": id_,
            "title": title,
            "printed_page": printed_page,
        })

    family_to_level = {}
    if None in seen_families:
        family_to_level["bez-markera"] = 1

    numeric_index = 1
    for fam in seen_families:
        if fam is None:
            continue
        family_to_level[fam] = numeric_index
        numeric_index += 1

    for e in entries:
        e["level"] = family_to_level.get(e["family"], 1)

    families_order = [
        (f if f is not None else "bez-markera") for f in seen_families
    ]

    return {
        "toc_location": location,
        "toc_pages": [p["page"] for p in toc_pages],
        "families_order": families_order,
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

        print(f"  Location:   {result['toc_location']}")
        print(f"  TOC strane: {result['toc_pages']}")
        print(f"  Sekcija:    {len(result['sections'])}")
        print(f"  Sacuvano:   {out_path}\n")


if __name__ == "__main__":
    main()
