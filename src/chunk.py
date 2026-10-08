"""
Faza 3 — chunking sa hijerarhijskim povezivanjem — MULTI-PDF.

CILJ:
  - Chunkovi sadrze CELE misli (recenice).
  - Ciljna duzina ~700 znakova, ali NIJE tvrda granica.
  - Omoguciti tacne i sveobuhvatne odgovore.
  - Za svaki PDF: data/chunks/<stem>.jsonl
  - Zajednicki fajl: data/chunks/_all_chunks.jsonl (za FAISS)

MULTI-PDF:
  - source (ime PDF-a) se dodaje kao prvi element u section_ids:
      section_ids = ["hobp_vodic_2025::I", "hobp_vodic_2025::I.1"]
    Time section_ids postaje globalno jedinstven kroz sve PDF-ove.
  - related_recommendations, related_tables, related_lists se racunaju
    samo unutar istog source-a (ne mesaju se PDF-ovi).

TIPOVI:
  - Preporuka ("Препорука X.Y.") — uvod + stavke ili cela.
  - Lista (bullet van preporuke) — stavke ili cela.
  - Tabela ("Табела X.") — cela tabela = jedan chunk.
  - Paragraf (ostalo) — grupisanje recenica do ~700 znakova.
  - Reference ("Литература") — PRESKACEMO.

ZBIRNI PREGLED:
  Preporuke iz "ЗБИРНИ ПРЕГЛЕД ПРЕПОРУКА" nose is_summary=True i
  imaju prazne related_recommendations (nisu u poglavlju).

Izvor:  data/structure/*.structure.json  +  data/extracted/*.jsonl
Izlaz:  data/chunks/*.jsonl  +  data/chunks/_all_chunks.jsonl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json
import re
from collections import defaultdict


# --- Parametri ---
PARAGRAPH_TARGET_SIZE = 700
PARAGRAPH_MIN_SIZE = 200
RECOMMENDATION_SINGLE_MAX = 700
LIST_SINGLE_MAX = 500
LIST_MIN_ITEMS_FOR_SPLIT = 5

# --- Regex ---
RE_RECOMMENDATION = re.compile(r"^Препорука\s+(\d+\.\d+)\.?\s*$", re.UNICODE)
RE_TABLE = re.compile(r"^Табела\s+(\d+)\.\s*(.+)$", re.UNICODE)
RE_LITERATURA = re.compile(r"^\s*Литература\s*[:.]?\s*$", re.UNICODE)
RE_PAGE_NUMBER = re.compile(r"^\d{1,3}$", re.UNICODE)
RE_BULLET = re.compile(r"^\s*[–—•\-▪]\s+(.+)$", re.UNICODE)
RE_NUMBERED_ITEM = re.compile(r"^\s*(\d+)[.)]\s+(.+)$", re.UNICODE)
RE_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+", re.UNICODE)


# =====================================================================
# 1) HIJERARHIJSKI ID-EVI
# =====================================================================

def _slugify(text: str, max_len: int = 30) -> str:
    s = text.lower()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s)
    return s[:max_len].strip("_")


def build_section_ids(sections: list[dict], source: str) -> dict[int, list[str]]:
    """
    Gradi hijerarhijske ID-eve sa source-om kao prefiksom.
    Npr: ["hobp_vodic_2025::I", "hobp_vodic_2025::I.1"]
    """
    result = {}
    stack = []   # (level, full_id)

    for i, sec in enumerate(sections):
        level = sec.get("level", 1)
        id_ = sec.get("id")
        if not id_:
            id_ = _slugify(sec.get("title", "")) or f"S{i}"

        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            parent_id = stack[-1][1]
            full_id = f"{parent_id}.{id_}"
        else:
            full_id = f"{source}::{id_}"

        path = [s[1] for s in stack] + [full_id]
        result[i] = path

        stack.append((level, full_id))

    return result


def build_sibling_map(sections: list[dict],
                      section_ids: dict[int, list[str]]) -> dict[int, list[str]]:
    by_parent = defaultdict(list)
    for i, sec in enumerate(sections):
        path = section_ids.get(i, [])
        if not path:
            continue
        parent = path[-2] if len(path) >= 2 else None
        full_id = path[-1]
        by_parent[parent].append((i, full_id))

    result = {}
    for parent, items in by_parent.items():
        ids = [full_id for _, full_id in items]
        for i, full_id in items:
            result[i] = [sib for sib in ids if sib != full_id]

    return result


def build_full_section_path(sec_idx: int,
                            sections: list[dict],
                            section_ids: dict[int, list[str]]) -> list[str]:
    path_ids = section_ids.get(sec_idx, [])
    if not path_ids:
        return [sections[sec_idx].get("title", "")]

    result_titles = []
    for pid in path_ids:
        for i, sec in enumerate(sections):
            if pid in section_ids.get(i, []):
                result_titles.append(sec.get("title", ""))
                break
    return result_titles


def is_summary_section(section_title: str) -> bool:
    t = section_title.lower()
    return "збирни преглед" in t or "zbirni pregled" in t


# =====================================================================
# 2) DETEKCIJA TIPOVA
# =====================================================================

def detect_recommendations(lines: list[str]) -> list[dict]:
    recs = []
    current = None
    for i, line in enumerate(lines):
        s = line.strip()
        m = RE_RECOMMENDATION.match(s)
        if m:
            if current is not None:
                current["end_line"] = i - 1
                recs.append(current)
            current = {"id": m.group(1), "start_line": i, "end_line": None}
            continue
        if current is not None:
            if (RE_TABLE.match(s) or RE_LITERATURA.match(s)
                or re.match(r"^(I{1,3}|IV|V|VI{0,3}|IX|X{1,3})\.?\s+\S", s)
                or re.match(r"^\d{1,2}\.\s+[А-ШЂЈЉЊЋЏ]", s)):
                current["end_line"] = i - 1
                recs.append(current)
                current = None

    if current is not None:
        current["end_line"] = len(lines) - 1
        recs.append(current)

    for rec in recs:
        rec["text"] = "\n".join(lines[rec["start_line"]:rec["end_line"] + 1]).strip()
    return recs


def detect_tables(lines: list[str]) -> list[dict]:
    tables = []
    current = None
    for i, line in enumerate(lines):
        s = line.strip()
        m = RE_TABLE.match(s)
        if m:
            if current is not None:
                current["end_line"] = i - 1
                tables.append(current)
            current = {
                "id": m.group(1),
                "title": m.group(2).strip(),
                "start_line": i,
                "end_line": None,
            }
            continue
        if current is not None:
            if (RE_RECOMMENDATION.match(s)
                or re.match(r"^(I{1,3}|IV|V|VI{0,3}|IX|X{1,3})\.?\s+\S", s)
                or re.match(r"^\d{1,2}\.\s+[А-ШЂЈЉЊЋЏ]", s)):
                current["end_line"] = i - 1
                tables.append(current)
                current = None

    if current is not None:
        current["end_line"] = len(lines) - 1
        tables.append(current)

    for t in tables:
        t["text"] = "\n".join(lines[t["start_line"]:t["end_line"] + 1]).strip()
    return tables


def detect_lists(lines: list[str]) -> list[dict]:
    lists = []
    current = None
    for i, line in enumerate(lines):
        s = line.strip()
        is_bullet = bool(RE_BULLET.match(s))
        if is_bullet:
            if current is None:
                current = {"start_line": i, "end_line": i, "items": [s]}
            else:
                prev = lines[i - 1].strip() if i > 0 else ""
                if prev and not RE_BULLET.match(prev):
                    current["end_line"] = i - 1
                    lists.append(current)
                    current = {"start_line": i, "end_line": i, "items": [s]}
                else:
                    current["items"].append(s)
                    current["end_line"] = i
        else:
            if current is not None:
                current["end_line"] = i - 1
                lists.append(current)
                current = None

    if current is not None:
        current["end_line"] = len(lines) - 1
        lists.append(current)

    lists = [l for l in lists if len(l["items"]) >= 2]
    for l in lists:
        l["text"] = "\n".join(lines[l["start_line"]:l["end_line"] + 1]).strip()
        l["list_type"] = "bullet"
    return lists


# =====================================================================# 3) CHUNKING PO TIPU
# =====================================================================

def split_into_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    parts = RE_SENTENCE_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def chunk_paragraphs_by_sentences(text: str,
                                   target_size: int = PARAGRAPH_TARGET_SIZE,
                                   min_size: int = PARAGRAPH_MIN_SIZE) -> list[str]:
    sentences = split_into_sentences(text)
    if not sentences:
        return []

    chunks = []
    current = []
    current_len = 0
    for sent in sentences:
        sent_len = len(sent)
        if current and current_len + sent_len + 1 > target_size:
            if current_len >= min_size:
                chunks.append(" ".join(current))
                current = [sent]
                current_len = sent_len
            else:
                current.append(sent)
                current_len += sent_len + 1
                chunks.append(" ".join(current))
                current = []
                current_len = 0
        else:
            current.append(sent)
            current_len += sent_len + 1

    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_recommendation(rec, section_path, section_ids, pdf_page,
                          source, is_summary):
    rec_text = rec["text"].strip()
    rec_id = rec["id"]
    lines = rec_text.split("\n")
    sec_id = section_ids[-1] if section_ids else "unknown"

    if len(rec_text) <= RECOMMENDATION_SINGLE_MAX:
        return [{
            "chunk_id": f"{source}::{sec_id}::p{pdf_page}::rec::{rec_id}::c0",
            "source": source,
            "pdf_page": pdf_page,
            "section_path": section_path,
            "section_ids": section_ids,
            "section_level": len(section_ids),
            "chunk_type": "recommendation",
            "recommendation_id": rec_id,
            "is_summary": is_summary,
            "chunk_index": 0,
            "chunk_total": 1,
            "text": rec_text,
        }]

    chunks = []
    intro_lines, items = [], []
    current_item = None
    for line in lines:
        s = line.strip()
        if RE_BULLET.match(s) or RE_NUMBERED_ITEM.match(s):
            if current_item is not None:
                items.append(current_item)
            current_item = s
        else:
            if current_item is not None:
                current_item += "\n" + line
            else:
                intro_lines.append(line)
    if current_item is not None:
        items.append(current_item)

    intro_text = "\n".join(intro_lines).strip()
    all_texts = []
    if intro_text:
        all_texts.append(intro_text)
    all_texts.extend(items)

    for idx, txt in enumerate(all_texts):
        chunks.append({
            "chunk_id": f"{source}::{sec_id}::p{pdf_page}::rec::{rec_id}::c{idx}",
            "source": source,
            "pdf_page": pdf_page,
            "section_path": section_path,
            "section_ids": section_ids,
            "section_level": len(section_ids),
            "chunk_type": "recommendation",
            "recommendation_id": rec_id,
            "is_summary": is_summary,
            "chunk_index": idx,
            "chunk_total": len(all_texts),
            "text": txt.strip(),
        })
    return chunks


def chunk_list(lst, section_path, section_ids, pdf_page, source,
                list_counter, is_summary):
    sec_id = section_ids[-1] if section_ids else "unknown"
    list_id = f"{source}::{sec_id}::p{pdf_page}::list::{list_counter}"
    items = lst["items"]
    list_text = lst["text"]

    if len(list_text) <= LIST_SINGLE_MAX or len(items) < LIST_MIN_ITEMS_FOR_SPLIT:
        return [{
            "chunk_id": f"{list_id}::whole",
            "source": source,
            "pdf_page": pdf_page,
            "section_path": section_path,
            "section_ids": section_ids,
            "section_level": len(section_ids),
            "chunk_type": "list_item",
            "list_id": list_id,
            "list_index": 0,
            "list_total": 1,
            "list_type": lst.get("list_type", "bullet"),
            "is_summary": is_summary,
            "text": list_text,
        }]

    chunks = []
    for idx, item in enumerate(items):
        chunks.append({
            "chunk_id": f"{list_id}::item{idx}",
            "source": source,
            "pdf_page": pdf_page,
            "section_path": section_path,
            "section_ids": section_ids,
            "section_level": len(section_ids),
            "chunk_type": "list_item",
            "list_id": list_id,
            "list_index": idx,
            "list_total": len(items),
            "list_type": lst.get("list_type", "bullet"),
            "is_summary": is_summary,
            "text": item.strip(),
        })
    return chunks


def chunk_table(tbl, section_path, section_ids, pdf_page, source, is_summary):
    sec_id = section_ids[-1] if section_ids else "unknown"
    return [{
        "chunk_id": f"{source}::{sec_id}::p{pdf_page}::tbl::{tbl['id']}",
        "source": source,
        "pdf_page": pdf_page,
        "section_path": section_path,
        "section_ids": section_ids,
        "section_level": len(section_ids),
        "chunk_type": "table",
        "table_id": tbl["id"],
        "table_title": tbl["title"],
        "is_summary": is_summary,
        "text": tbl["text"],
    }]


# =====================================================================
# 4) GLAVNI TOK
# =====================================================================

def build_page_index(pages):
    return {p["page"]: p["text"] for p in pages}


def collect_section_text(sec_start_page, next_sec_start_page, page_index):
    if next_sec_start_page is None:
        end = max(page_index.keys()) + 1
    else:
        end = next_sec_start_page
    parts = []
    for p in range(sec_start_page, end):
        if p not in page_index:
            continue
        text = page_index[p]
        lines = text.split("\n")
        if lines and RE_PAGE_NUMBER.match(lines[0].strip()):
            lines = lines[1:]
        parts.append("\n".join(lines))
    return "\n".join(parts)


def process_section(sec, sec_idx, sections, section_ids, sibling_map,
                     section_text, source):
    pdf_page = sec.get("pdf_page")
    if pdf_page is None:
        return []

    section_path = build_full_section_path(sec_idx, sections, section_ids)
    current_ids = section_ids.get(sec_idx, [])
    is_summary = is_summary_section(sec.get("title", ""))

    lines = section_text.split("\n")
    if not [l for l in lines if l.strip()]:
        return []

    recs = detect_recommendations(lines)
    tables = detect_tables(lines)
    lists = detect_lists(lines)

    covered = [False] * len(lines)
    for r in recs:
        for i in range(r["start_line"], r["end_line"] + 1):
            covered[i] = True
    for t in tables:
        for i in range(t["start_line"], t["end_line"] + 1):
            covered[i] = True
    for l in lists:
        for i in range(l["start_line"], l["end_line"] + 1):
            if not covered[i]:
                covered[i] = True

    paragraph_lines = [lines[i] for i in range(len(lines)) if not covered[i]]
    paragraph_text = "\n".join(paragraph_lines).strip()

    chunks = []
    for rec in recs:
        chunks.extend(chunk_recommendation(
            rec, section_path, current_ids, pdf_page, source, is_summary))
    for tbl in tables:
        chunks.extend(chunk_table(
            tbl, section_path, current_ids, pdf_page, source, is_summary))
    for li, lst in enumerate(lists):
        chunks.extend(chunk_list(
            lst, section_path, current_ids, pdf_page, source, li + 1, is_summary))

    if paragraph_text:
        para_chunks = chunk_paragraphs_by_sentences(paragraph_text)
        total = len(para_chunks)
        for idx, txt in enumerate(para_chunks):
            chunks.append({
                "chunk_id": f"{source}::{current_ids[-1] if current_ids else 'unknown'}::p{pdf_page}::p::c{idx}",
                "source": source,
                "pdf_page": pdf_page,
                "section_path": section_path,
                "section_ids": current_ids,
                "section_level": len(current_ids),
                "chunk_type": "paragraph",
                "is_summary": is_summary,
                "chunk_index": idx,
                "chunk_total": total,
                "text": txt.strip(),
            })

    parent_id = current_ids[-2] if len(current_ids) >= 2 else None
    siblings = sibling_map.get(sec_idx, [])
    for c in chunks:
        c["parent_section_id"] = parent_id
        c["sibling_sections"] = siblings

    return chunks


def add_related_links(chunks: list[dict]) -> list[dict]:
    """
    Dodaje related_* linkove.
    Grupise po (source, chapter) da ne mesa PDF-ove.
    """
    by_source_chapter = defaultdict(list)
    for c in chunks:
        ids = c.get("section_ids") or []
        # section_ids[0] je "source::chapter" (npr. "hobp_vodic_2025::I")
        chapter_key = ids[0] if ids else "_"
        by_source_chapter[chapter_key].append(c)

    for chapter_key, chapter_chunks in by_source_chapter.items():
        rec_ids = sorted(set(
            c["recommendation_id"] for c in chapter_chunks
            if c.get("recommendation_id") and not c.get("is_summary")
        ))
        tbl_ids = sorted(set(
            c["table_id"] for c in chapter_chunks
            if c.get("table_id") and not c.get("is_summary")
        ))

        for c in chapter_chunks:
            if c.get("is_summary"):
                c["related_recommendations"] = []
                c["related_tables"] = []
                continue

            if c.get("recommendation_id"):
                c["related_recommendations"] = [
                    r for r in rec_ids if r != c["recommendation_id"]
                ]
            else:
                c["related_recommendations"] = rec_ids

            if c.get("table_id"):
                c["related_tables"] = [
                    t for t in tbl_ids if t != c["table_id"]
                ]
            else:
                c["related_tables"] = tbl_ids

    # related_lists — ista sekcija (isti section_ids), isto vazi za sve PDF-ove
    by_section = defaultdict(list)
    for c in chunks:
        key = tuple(c.get("section_ids") or [])
        by_section[key].append(c)

    for key, sec_chunks in by_section.items():
        list_ids = sorted(set(
            c["list_id"] for c in sec_chunks if c.get("list_id")
        ))
        for c in sec_chunks:
            if c.get("list_id"):
                c["related_lists"] = [l for l in list_ids if l != c["list_id"]]
            else:
                c["related_lists"] = list_ids

    return chunks


def process_document(structure_path: Path, extracted_path: Path) -> list[dict]:
    """Obradi jedan dokument i vrati listu chunkova."""
    stem = structure_path.name.replace(".structure.json", "")
    source = stem

    structure = json.load(open(structure_path, encoding="utf-8"))
    pages = [json.loads(l) for l in open(extracted_path, encoding="utf-8")]
    page_index = build_page_index(pages)

    sections = structure["sections"]
    section_ids = build_section_ids(sections, source)
    sibling_map = build_sibling_map(sections, section_ids)

    chunks = []
    for i, sec in enumerate(sections):
        pdf_page = sec.get("pdf_page")
        if pdf_page is None:
            continue

        next_page = None
        for j in range(i + 1, len(sections)):
            if sections[j].get("pdf_page") is not None:
                next_page = sections[j]["pdf_page"]
                break

        text = collect_section_text(pdf_page, next_page, page_index)
        if not text.strip():
            continue

        sec_chunks = process_section(
            sec, i, sections, section_ids, sibling_map, text, source,
        )
        chunks.extend(sec_chunks)

    chunks = add_related_links(chunks)
    return chunks


def main():
    structure_dir = Path("data/structure")
    extracted_dir = Path("data/extracted")
    output_dir = Path("data/chunks")
    output_dir.mkdir(parents=True, exist_ok=True)

    structure_files = sorted(structure_dir.glob("*.structure.json"))
    if not structure_files:
        print(f"Nema .structure.json u {structure_dir}. Pokreni prvo map_pages.py.")
        return

    print(f"Nadjeno {len(structure_files)} dokumenata.\n")

    all_chunks_combined = []

    for structure_path in structure_files:
        stem = structure_path.name.replace(".structure.json", "")
        extracted_path = extracted_dir / f"{stem}.jsonl"
        out_path = output_dir / f"{stem}.jsonl"

        if not extracted_path.exists():
            print(f"  PRESKACEM {stem}: nema {extracted_path}")
            continue

        print(f"=== {stem} ===")
        chunks = process_document(structure_path, extracted_path)

        with open(out_path, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        print(f"  Chunkova: {len(chunks)}")
        print(f"  Sacuvano: {out_path}\n")

        all_chunks_combined.extend(chunks)

    # Zajednicki fajl za FAISS
    combined_path = output_dir / "_all_chunks.jsonl"
    with open(combined_path, "w", encoding="utf-8") as f:
        for c in all_chunks_combined:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Statistika
    print(f"=== UKUPNO ===")
    print(f"Chunkova: {len(all_chunks_combined)}")

    by_type = defaultdict(int)
    by_source = defaultdict(int)
    for c in all_chunks_combined:
        by_type[c["chunk_type"]] += 1
        by_source[c["source"]] += 1

    print("\nPo tipu:")
    for t, n in sorted(by_type.items()):
        print(f"  {t:20s}: {n}")

    print("\nPo dokumentu:")
    for s, n in sorted(by_source.items()):
        print(f"  {s:30s}: {n}")

    summary_count = sum(1 for c in all_chunks_combined if c.get("is_summary"))
    print(f"\nZbirni pregled (is_summary=True): {summary_count}")
    print(f"Originalni (is_summary=False):   {len(all_chunks_combined) - summary_count}")

    print(f"\nZajednicki fajl: {combined_path}")


if __name__ == "__main__":
    main()
