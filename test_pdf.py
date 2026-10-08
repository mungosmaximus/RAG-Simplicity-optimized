from pypdf import PdfReader
from pathlib import Path

# Nađi prvi PDF u folderu pdfs
pdfs = list(Path("pdfs").glob("*.pdf"))
if not pdfs:
    print("Nema PDF-a u folderu pdfs/")
    exit()

pdf_path = pdfs[0]
print(f"Fajl: {pdf_path.name}")
print(f"Broj strana: {len(PdfReader(pdf_path).pages)}\n")

reader = PdfReader(pdf_path)

# Uzmi nekoliko strana sa različitih mesta u dokumentu
for page_num in [0, 10, 45, 80]:
    if page_num >= len(reader.pages):
        continue
    page = reader.pages[page_num]
    text = page.extract_text()
    print(f"--- Strana {page_num + 1} (prvih 500 znakova) ---")
    print(text[:500])
    print()
