# Medical RAG

Sistem za pitanja i odgovore nad medicinskim dokumentima (PDF) koristeći
RAG (Retrieval-Augmented Generation).

## Arhitektura
PDF-ovi (pdfs/)
│
▼
[1] extract.py → tekst po stranama (data/extracted/)
│
▼
[2] toc.py → naslovi iz sadržaja (data/structure/.toc.json)
│
▼
[3] map_pages.py → PDF strane za svaki naslov (data/structure/.structure.json)
│
▼
[4] chunk.py → chunkovi sa metadata (data/chunks/)
│
▼
[5] embed.py → FAISS indeks (data/index/)
│
▼
[6] retrieve.py → pretraga + kontekst
│
▼
[7] chat.py → odgovor (LM Studio API)

## Instalacija

```bash
git clone <repo>
cd Medical_rag
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt

Upotreba
1. Pripremi PDF-ove
Stavi PDF-ove u pdfs/. Ako PDF ima sadržaj na fizičkim stranama X-Y,
preimenuj ga:

text
moj_dokument_toc_10-12.pdf    # sadržaj na stranama 10-12
Bez _toc_X-Y, sistem pokušava sam da nađe sadržaj (radi za većinu PDF-ova).

2. Pokreni pipeline
bash
python src/extract.py      # PDF → tekst
python src/toc.py          # tekst → naslovi
python src/map_pages.py    # naslovi → PDF strane
python src/chunk.py        # naslovi → chunkovi
python src/embed.py        # chunkovi → FAISS indeks
3. Postavi LM Studio
Učitaj chat model (npr. Qwen2.5-3B-Instruct, GGUF Q4_K_M).

Pokreni server na http://localhost:1234.

4. Pitaj
bash
python src/chat.py
Struktura
text
Medical_rag/
├── pdfs/                # originalni PDF-ovi
├── data/
│   ├── extracted/       # tekst po stranama
│   ├── structure/       # naslovi + PDF strane
│   ├── chunks/          # chunkovi sa metadata
│   └── index/           # FAISS indeks
├── src/                 # Python kod
│   ├── config.py
│   ├── toc_titles.py
│   ├── toc_locations.py
│   ├── patterns.py
│   ├── extract.py
│   ├── toc.py
│   ├── map_pages.py
│   ├── chunk.py
│   ├── embed.py
│   ├── intents.py
│   ├── retrieve.py
│   └── chat.py
├── requirements.txt
├── .gitignore
└── README.md
Zahtevi
Python 3.10+

pypdf, fonttools, sentence-transformers, faiss-cpu, openai, tqdm

LM Studio (za chat model)

Napomene
fonttools je OBAVEZAN — bez njega, PDF-ovi sa CFF Type1 fontovima
daju pogrešne znakove (npr. ćirilica → kineski).