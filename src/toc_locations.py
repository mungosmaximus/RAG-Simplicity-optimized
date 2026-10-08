"""
Mapa eksplicitnih TOC lokacija po dokumentu.

Ovo je FALLBACK ako lokacija nije u imenu PDF-a.
Format: {stem: [lista_strana]}
  - stem je ime PDF-a bez .pdf i bez _toc_X-Y sufiksa.
  - lista_strana je 1-indeksirano.

Prioritet:
  1. Ime PDF-a (npr. astma_toc_10-12.pdf)
  2. Ova mapa
  3. Primarna detekcija (toc.py)
  4. Fallback detekcija (toc.py)

Dodaj nove dokumente ovde ako parser ne uspe da nadje sadrzaj sam.
"""

TOC_LOCATIONS = {
    # "hobp_vodic_2025": [12, 13],   # primer — parser to sam nadje
    # "astma": [10, 11, 12],         # primer — koristi ime fajla umesto ovoga
}
