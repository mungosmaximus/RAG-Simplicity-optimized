"""
Faza 2.5 — ekstrakcija hijerarhijske strukture dokumenta.

Pristup:
  - Naslov prihvatamo samo ako POSLE njega dolazi pravi paragraf
    (red koji lici na recenicu: veliko slovo, tekst, tacka).
  - Reference u literaturi nemaju tu strukturu (nastavljaju se u sledeci
    red bez tacke), pa se odbacuju.
  - Nivo 1 mora biti VELIKIM SLOVIMA (da ne bismo hvatali nivoe dokaza
    tipa "I. Доказано је...").
  - Nivo 2 i 3 unutar preporuke su liste, ne naslovi.

Izvor: data/extracted/<ime>.jsonl
Izlaz: data/structure/<ime>.json
"""
from pathlib import Path
import json
import re


# --- Regex obrasci ---

RE_LEVEL1 = re.compile(
    r"^(I{1,3}|IV|V|VI{0,3}|IX|X{1,3})\.\s{1,6}([А-ШЂЈЉЊЋЏA-Z][^\n]+)$",
    re.UNICODE,
)
RE_LEVEL2 = re.compile(
    r"^(\d{1,2})\.\s{1,4}([А-ШЂЈЉЊЋЏA-Z][^\n]+)$",
    re.UNICODE,
)
RE_LEVEL3 = re.compile(
    r"^([а-шђјљњћџa-z])\.\s{1,3}([А-ШЂЈЉЊЋЏA-Z][^\n]+)$",
    re.UNICODE,
)
RE_RECOMMENDATION = re.compile(r"^Препорука\s+(\d+\.\d+)\.?\s*$", re.UNICODE)
RE_PAGE_NUMBER = re.compile(r"^\d{1,3}$")
RE_LITERATURA = re.compile(r"^\s*Литература\s*$", re.UNICODE)
RE_TOC_DOTS = re.compile(r"\.{4,}")
RE_YEAR = re.compile(r"\b(19|20)\d{2}\b")

# Skracenice koje ne racunamo kao kraj recenice
RE_ABBREV = re.compile(
    r"\b(dr|mr|str|sl|npr|itd|tj|v|g|god|sv|nr|br|op|cit|upor|vid|vidi)\.",
    re.IGNORECASE,
)


# --- Pomocne funkcije ---

def strip_page_header(text: str) -> str:
    """Uklanja header strane — prvi red ako je samo broj."""
    lines = text.split("\n")
    if lines and RE_PAGE_NUMBER.match(lines[0].strip()):
        lines = lines[1:]
    return "\n".join(lines)


def is_level1_title(title: str) -> bool:
    """Naslov nivoa 1 je obicno VELIKIM SLOVIMA (bar 70%)."""
    first = title[:40]
    upper = sum(1 for c in first if c.isupper())
    letters = sum(1 for c in first if c.isalpha())
    if letters == 0:
        return False
    return upper / letters >= 0.7


def is_reference(text: str) -> bool:
    """Prepoznaje referencu u literaturi."""
    first_150 = text[:150]

    # "et al" bilo gde
    if "et al" in text.lower():
        return True

    # DOI, PMID, URL
    if any(s in text.lower() for s in ("doi:", "pmid", "http://", "https://")):
        return True

    # Zapeta + godina (autori + godina publikacije)
    if "," in text[:60] and RE_YEAR.search(first_150):
        return True

    # Inicijali autora: "Smith J." ili "Milenković B,"
    if re.search(r"[A-ZА-ШЂЈЉЊЋЏ][a-zа-шђјљњћџ]+\s+[A-ZА-ШЂЈЉЊЋЏ]\.", text[:80]):
        return True

    # Godina u formatu za casopis: "2020;" ili "2020."
    if re.search(r"\b(19|20)\d{2}[;.]", first_150):
        return True

    return False


def is_heading_candidate(line: str) -> tuple[int, str, str] | None:
    """
    Vraca (nivo, id, naslov) ako linija LICI na naslov, inace None.
    Ne proverava da li ima telo — to radi drugi korak.
    """
    stripped = line.strip()

    if RE_TOC_DOTS.search(stripped):
        return None
    if len(stripped) > 120:
        return None

    for pattern, level in ((RE_LEVEL1, 1), (RE_LEVEL2, 2), (RE_LEVEL3, 3)):
        m = pattern.match(stripped)
        if m:
            num = m.group(1)
            title = m.group(2).strip()

            # Za nivo 1: zahtevaj VELIKA SLOVA
            if level == 1 and not is_level1_title(title):
                continue

            return level, num, title
    return None


def is_sentence_line(line: str) -> bool:
    """
    Red lici na recenicu ako:
      - ima bar 50 znakova,
      - pocinje velikim slovom, brojem ili navodnikom,
      - sadrzi bar jednu tacku/upitnik/uzvicnik koji NIJE deo skracenice.
    """
    s = line.strip()
    if len(s) < 50:
        return False

    first = s[0]
    if not (first.isupper() or first.isdigit() or first in "„«(\"'"):
        return False

    # Ukloni skracenice, pa trazi kraj recenice
    cleaned = RE_ABBREV.sub("", s)
    if not re.search(r"[.!?]", cleaned):
        return False

    return True


def has_paragraph_after(lines: list[str], start_idx: int,
                        lookahead: int = 8) -> bool:
    """
    Gleda sledecih `lookahead` linija posle naslova.
    Vraca True ako medju njima ima bar JEDNA linija koja lici na recenicu,
    PRE nego sto naidjemo na sledeci kandidat za naslov.
    """
    for j in range(start_idx + 1, min(start_idx + 1 + lookahead, len(lines))):
        line = lines[j]
        if not line.strip():
            continue
        if is_heading_candidate(line):
            return False
        if is_sentence_line(line):
            return True
    return False


def parse_document(extracted_path: Path) -> dict:
    """Cita .jsonl i vraca strukturu sa sekcijama i preporukama."""
    pages = []
    with open(extracted_path, encoding="utf-8") as f:
        for line in f:
            pages.append(json.loads(line))

    if not pages:
        return {"source": extracted_path.stem, "sections": [], "recommendations": []}

    source = pages[0]["source"]

    # Spoji sve linije u jedan niz, pamtimo stranu za svaku liniju
    all_lines = []
    for page_data in pages:
        text = strip_page_header(page_data["text"])
        for line in text.split("\n"):
            all_lines.append((page_data["page"], line))

    lines_only = [l for _, l in all_lines]

    sections_flat = []
    recommendations = []
    current_rec = None

    i = 0
    while i < len(all_lines):
        page_num, raw_line = all_lines[i]
        stripped = raw_line.strip()

        if not stripped:
            i += 1
            continue

        # 1) Preporuka?
        m = RE_RECOMMENDATION.match(stripped)
        if m:
            if current_rec:
                current_rec["text"] = current_rec["text"].strip()
                recommendations.append(current_rec)
            current_rec = {
                "id": m.group(1),
                "page": page_num,
                "section_id": None,
                "text": "",
            }
            i += 1
            continue

        # 2) Kandidat za naslov?
        cand = is_heading_candidate(stripped)
        if cand:
            level, num, title = cand

            # Ako naslov izgleda kao referenca — odbaci
            if is_reference(title):
                i += 1
                continue

            # Ako smo unutar preporuke, prihvati samo nivo 1.
            # Nivo 2 i 3 unutar preporuke su liste, ne naslovi.
            if current_rec and level > 1:
                i += 1
                continue

            # Da li ima pravi paragraf ispod?
            if not has_paragraph_after(lines_only, i):
                i += 1
                continue

            # Zatvori prethodnu preporuku ako postoji
            if current_rec:
                current_rec["text"] = current_rec["text"].strip()
                recommendations.append(current_rec)
                current_rec = None

            sections_flat.append({
                "id": num,
                "title": title,
                "level": level,
                "page": page_num,
            })
            i += 1
            continue

        # 3) Literatura — zatvori preporuku
        if RE_LITERATURA.match(raw_line):
            if current_rec:
                current_rec["text"] = current_rec["text"].strip()
                recommendations.append(current_rec)
                current_rec = None
            i += 1
            continue

        # 4) Obican tekst — dodaj u tekucu preporuku
        if current_rec:
            current_rec["text"] += raw_line + "\n"

        i += 1

    if current_rec:
        current_rec["text"] = current_rec["text"].strip()
        recommendations.append(current_rec)

    sections_tree = build_hierarchy(sections_flat)
    assign_sections_to_recommendations(recommendations, sections_flat)

    return {
        "source": source,
        "sections": sections_tree,
        "recommendations": recommendations,
    }


def build_hierarchy(flat: list[dict]) -> list[dict]:
    """Pretvara ravnu listu sekcija u drvo po nivoima."""
    root = []
    stack = []

    for sec in flat:
        node = {**sec, "children": []}
        level = sec["level"]

        while stack and stack[-1][0] >= level:
            stack.pop()

        if not stack:
            root.append(node)
        else:
            stack[-1][1]["children"].append(node)

        stack.append((level, node))

    return root


def assign_sections_to_recommendations(recommendations: list[dict],
                                        sections_flat: list[dict]) -> None:
    """Za svaku preporuku nadji najblizu prethodnu sekciju (po strani)."""
    sorted_secs = sorted(sections_flat, key=lambda s: s["page"])

    for rec in recommendations:
        candidate = None
        for sec in sorted_secs:
            if sec["page"] <= rec["page"]:
                candidate = sec
            else:
                break
        if candidate:
            rec["section_id"] = candidate["id"]


def count_sections(tree: list[dict]) -> int:
    total = 0
    for node in tree:
        total += 1 + count_sections(node.get("children", []))
    return total


def main():
    extracted_dir = Path("data/extracted")
    output_dir = Path("data/structure")
    output_dir.mkdir(parents=True, exist_ok=True)

    for jsonl_path in sorted(extracted_dir.glob("*.jsonl")):
        print(f"Obradjujem: {jsonl_path.name}")
        doc = parse_document(jsonl_path)

        out_path = output_dir / f"{jsonl_path.stem}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

        n_sec = count_sections(doc["sections"])
        n_rec = len(doc["recommendations"])
        print(f"  -> {out_path}")
        print(f"     sekcija: {n_sec}, preporuka: {n_rec}")


if __name__ == "__main__":
    main()
