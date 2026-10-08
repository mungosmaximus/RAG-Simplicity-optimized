"""
Faza 2 — ekstrakcija teksta iz PDF-a, po stranama.

Za svaki PDF u `pdfs/`:
  - Ekstraktuje tekst po stranama.
  - Cuva metadata (source, page, n_chars).
  - Preskace prazne i prekratke strane.

Konvencija imena PDF-a:
  <ime>_toc_X-Y.pdf   -> TOC na stranama X do Y
  <ime>_toc_X.pdf     -> TOC na strani X
  <ime>.pdf           -> bez eksplicitne TOC lokacije

OBAVEZNE ZAVISNOSTI:
  - pypdf             — parser PDF-a
  - fonttools         — OBAVEZNO za PDF-ove sa CFF Type1 fontovima
                        (bez njega, cirilica moze biti pogresno citana)
  - tqdm              — progress bar

Izvor:  pdfs/*.pdf
Izlaz:  data/extracted/*.jsonl  (jedan po PDF-u)
"""
from pathlib import Path
from pypdf import PdfReader
from tqdm import tqdm
import json
import re
from collections import Counter


# =====================================================================
# PROVERA ZAVISNOSTI
# =====================================================================

try:
    import fontTools
    _HAS_FONTTOOLS = True
    _FONTTOOLS_VERSION = fontTools.version
except ImportError:
    _HAS_FONTTOOLS = False
    _FONTTOOLS_VERSION = None


def _check_dependencies() -> None:
    """
    Proverava da li su sve obavezne zavisnosti instalirane.
    Ispisuje upozorenje ako fontTools nije prisutan.
    """
    if not _HAS_FONTTOOLS:
        print("=" * 70)
        print("UPOZORENJE: fontTools nije instaliran.")
        print()
        print("fontTools je OBAVEZAN za ispravno citanje PDF-ova koji")
        print("koriste CFF Type1 fontove (cesta pojava u PDF-ovima iz")
        print("LaTeX-a, Adobe InDesign-a, i dr.).")
        print()
        print("Bez fontTools, ovakvi PDF-ovi daju POGRE\u010cNE znakove")
        print("(npr. cirilica se cita kao kineski znakovi).")
        print()
        print("Instaliraj sa:")
        print("    pip install fonttools")
        print("=" * 70)
        print()


# Regex za TOC lokaciju u imenu fajla
RE_TOC_SUFFIX = re.compile(r"_toc_(\d+(?:-\d+)?)\.pdf$", re.IGNORECASE)


def parse_toc_location_from_name(filename: str) -> list[int] | None:
    """Parsira TOC lokaciju iz imena fajla."""
    match = RE_TOC_SUFFIX.search(filename)
    if not match:
        return None
    spec = match.group(1)
    if "-" in spec:
        start, end = spec.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(spec)]


def extract_pages(pdf_dir: str = "pdfs",
                  min_chars: int = 100) -> dict[str, list[dict]]:
    """
    Prolazi kroz sve PDF-ove u folderu.
    Vraca dict {stem: [records]} gde je svaki record jedna strana.
    """
    pdf_dir = Path(pdf_dir)
    pdf_files = sorted(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(f"Nema PDF-ova u folderu: {pdf_dir.resolve()}")

    results = {}

    for pdf_path in pdf_files:
        stem = pdf_path.stem
        clean_stem = RE_TOC_SUFFIX.sub(".pdf", pdf_path.name).replace(".pdf", "")

        reader = PdfReader(pdf_path)
        records = []
        skipped_empty = 0
        skipped_short = 0

        for i, page in enumerate(tqdm(reader.pages,
                                      desc=f"{clean_stem[:40]}",
                                      unit="str")):
            text = page.extract_text() or ""
            lines = [line.rstrip() for line in text.split("\n")]
            text = "\n".join(lines).strip()

            if not text:
                skipped_empty += 1
                continue

            if len(text) < min_chars:
                skipped_short += 1
                continue

            records.append({
                "source": clean_stem,
                "page": i + 1,
                "text": text,
                "n_chars": len(text),
            })

        if skipped_empty or skipped_short:
            print(f"  [{clean_stem}] preskoceno: "
                  f"{skipped_empty} praznih, {skipped_short} kratkih")

        results[clean_stem] = records

    return results


def save_by_document(results: dict[str, list[dict]],
                     output_dir: str = "data/extracted") -> None:
    """Cuva svaki dokument u svoj .jsonl fajl."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for stem, records in results.items():
        out_path = output_dir / f"{stem}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for item in records:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Sačuvano: {out_path}  ({len(records)} strana)")


def main():
    _check_dependencies()

    results = extract_pages()
    save_by_document(results)

    print(f"\nUkupno dokumenata: {len(results)}")
    total_pages = sum(len(r) for r in results.values())
    print(f"Ukupno strana: {total_pages}")

    print("\nStrane po dokumentu:")
    for stem, records in results.items():
        print(f"  {len(records):4d}  {stem}")

    print("\nStatistika duzine strana (po dokumentu):")
    for stem, records in results.items():
        if not records:
            continue
        lengths = [r["n_chars"] for r in records]
        print(f"  {stem}:")
        print(f"    min:    {min(lengths)}")
        print(f"    max:    {max(lengths)}")
        print(f"    prosek: {sum(lengths) // len(lengths)}")

    # Status zavisnosti
    print()
    if _HAS_FONTTOOLS:
        print(f"fontTools:  aktivan (verzija {_FONTTOOLS_VERSION})")
    else:
        print(f"fontTools:  NIJE AKTIVAN")
        print(f"            PDF-ovi sa CFF fontovima mogu dati pogresne znakove")
        print(f"            Instaliraj: pip install fonttools")


if __name__ == "__main__":
    main()