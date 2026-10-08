"""
Parametri ponašanja detekcije sadržaja.
Ovo NISU liste reči — one su u toc_titles.py.
"""

# --- Pretraga sadrzaja ---
MAX_LOOKAHEAD = 50
SKIP_END_PAGES = 5

# --- Pragovi za "strana je sadrzaj" ---
MIN_TOC_LINES = 5
TOC_RATIO_WITH_TITLE = 0.70
TOC_RATIO_WITHOUT_TITLE = 0.95
MAX_TOC_LINE_LENGTH = 150
