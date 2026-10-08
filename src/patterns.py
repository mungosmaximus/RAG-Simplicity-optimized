"""
Regex obrasci i familije markera.
Gradi se iz toc_titles.py i config.py.
"""
import re

from toc_titles import TOC_TITLES, LITERATURA_TITLES


# --- Naslov sadrzaja ---
_TOC_PATTERN = "|".join(re.escape(t) for t in TOC_TITLES)
RE_SADRZAJ = re.compile(
    rf"^\s*({_TOC_PATTERN})\s*[:.]?\s*$",
    re.IGNORECASE | re.UNICODE,
)


# --- Naslov literature ---
_LITERATURA_PATTERN = "|".join(re.escape(t) for t in LITERATURA_TITLES)
RE_LITERATURA = re.compile(
    rf"^\s*({_LITERATURA_PATTERN})\s*[:.]?\s*$",
    re.IGNORECASE | re.UNICODE,
)


# --- Samo broj (1-3 cifre) ---
RE_PAGE_NUMBER = re.compile(r"^\d{1,3}$")


# --- Sufiks sa brojem strane na kraju reda ---
RE_TOC_PAGE_SUFFIX = re.compile(
    r"(\d{1,4})\s*[\].)\-–—]*\s*$",
    re.UNICODE,
)


# --- Nealfanumericni marker na pocetku reda ---
RE_NONALNUM_MARKER = re.compile(
    r"^([^\w\s]+)\s+(.+)$",
    re.UNICODE,
)


# --- Alfanumericne familije markera ---
# Format: (ime_familije, regex, broj_grupa_u_regexu)
# Redosled je vazan: specificniji prvi.
ALNUM_FAMILIES = [
    # Najdublji arapski nivoi
    ("arapski-3", re.compile(r"^(\d{1,2}\.\d{1,2}\.\d{1,2})\.?\s{1,4}(.+)$", re.UNICODE), 2),
    ("arapski-2", re.compile(r"^(\d{1,2}\.\d{1,2})\.?\s{1,4}(.+)$", re.UNICODE), 2),

    # Rimski brojevi (I, II, ..., X)
    ("rimski",    re.compile(r"^(I{1,3}|IV|V|VI{0,3}|IX|X{1,3})\.?\s{1,6}(.+)$", re.UNICODE), 2),

    # Arapski nivo 1 (1., 2., ...)
    ("arapski-1", re.compile(r"^(\d{1,2})\.\s{1,4}(.+)$", re.UNICODE), 2),

    # Veliko slovo sa tackom (A., B., ...)
    ("veliko",    re.compile(r"^([A-ZА-ШЂЈЉЊЋЏ])\.\s{1,3}(.+)$", re.UNICODE), 2),

    # Malo slovo sa tackom (a., b., ...)
    ("malo",      re.compile(r"^([a-zа-шђјљњћџ])\.\s{1,3}(.+)$", re.UNICODE), 2),

    # "ПОГЛАВЉЕ X." prefiks (case-insensitive)
    ("poglavlje", re.compile(
        r"^(ПОГЛАВЉЕ|POGLAVLJE|Poglavlje|Поглавље)\s+(\d+)\.\s*(.+)$",
        re.UNICODE | re.IGNORECASE,
    ), 2),
]
