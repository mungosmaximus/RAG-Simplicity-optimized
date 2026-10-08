"""
Liste naslova za "sadrzaj" i "literaturu".
Ovo je JEDINI fajl koji treba menjadi kada dodajes nove jezike ili varijante.

Pravila:
  - Jedan string po varijanti.
  - Ne treba unositi velika/mala slova — poredjenje je case-insensitive.
  - Ne treba unositi tacku/dvotacku na kraju — regex to dozvoljava opciono.
"""

# --- Naslovi za "sadrzaj" ---
TOC_TITLES = [
    # Srpski (cirilica)
    "САДРЖАЈ", "САДРЖAJ", "Садржај", "Садржаj", "садржај",
    "Садржај књиге", "Садржај документа",
    # Srpski (latinica)
    "SADRŽAJ", "SADRZAJ", "Sadržaj", "Sadrzaj", "sadržaj", "sadrzaj",
    "Sadržaj knjige", "Sadrzaj knjige",
    # Engleski
    "CONTENTS", "Contents", "contents",
    "TABLE OF CONTENTS", "Table of Contents", "Table of contents",
    "TABLE OF CONTENT", "Table of content", "TOC",
    # Nemacki
    "INHALT", "Inhalt", "inhalt",
    "INHALTSVERZEICHNIS", "Inhaltsverzeichnis",
    # Francuski
    "TABLE DES MATIÈRES", "Table des matières",
    "TABLE DES MATIERES", "Table des matieres",
    "SOMMAIRE", "Sommaire",
    # Italijanski
    "INDICE", "Indice", "indice", "SOMMARIO", "Sommario",
    # Spanski
    "ÍNDICE", "Índice", "TABLA DE CONTENIDOS", "Tabla de contenidos",
]


# --- Naslovi za "literaturu" ---
LITERATURA_TITLES = [
    # Srpski (cirilica)
    "Литература", "ЛИТЕРАТУРА", "литература",
    "Референце", "РЕФЕРЕНЦЕ", "референце", "Референца",
    "Извори", "ИЗВОРИ", "извори",
    # Srpski (latinica)
    "Literatura", "LITERATURA", "literatura",
    "Reference", "REFERENCE", "reference", "Referenca",
    "Izvori", "IZVORI", "izvori",
    # Engleski
    "References", "REFERENCES", "references",
    "Bibliography", "BIBLIOGRAPHY", "bibliography",
    "Literature", "LITERATURE", "literature",
    "Sources", "SOURCES", "sources",
    "Works Cited", "WORKS CITED",
    "Further Reading", "FURTHER READING",
    # Nemacki
    "LITERATUR", "Literatur", "literatur",
    "LITERATURVERZEICHNIS", "Literaturverzeichnis",
    "QUELLEN", "Quellen",
    # Francuski
    "BIBLIOGRAPHIE", "Bibliographie", "bibliographie",
    "RÉFÉRENCES", "Références", "REFERENCES", "References",
    # Italijanski
    "BIBLIOGRAFIA", "Bibliografia", "bibliografia",
    "RIFERIMENTI", "Riferimenti",
]
