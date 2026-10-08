"""
Regex obrasci i familije markera.
Gradi se iz toc_titles.py i config.py.

Format ALNUM_FAMILIES:
  (ime_familije, regex, id_group, title_group)
    - id_group   : broj regex grupe koja sadrzi ID
    - title_group: broj regex grupe koja sadrzi naslov

detect_marker vraca (marker, id, title, marker_text):
  marker_text = PUNI tekst markera (npr. "ПОГЛАВЉЕ 1.", "1.", "I.", "a.").
  Koristi se u map_pages.py za tacno poklapanje sa tekstom.
"""
import re

from toc_titles import TOC_TITLES, LITERATURA_TITLES


# =====================================================================
# OSNOVNI REGEXI
# =====================================================================

_TOC_PATTERN = "|".join(re.escape(t) for t in TOC_TITLES)
RE_SADRZAJ = re.compile(
    rf"^\s*({_TOC_PATTERN})\s*[:.]?\s*$",
    re.IGNORECASE | re.UNICODE,
)


_LITERATURA_PATTERN = "|".join(re.escape(t) for t in LITERATURA_TITLES)
RE_LITERATURA = re.compile(
    rf"^\s*({_LITERATURA_PATTERN})\s*[:.]?\s*$",
    re.IGNORECASE | re.UNICODE,
)


RE_PAGE_NUMBER = re.compile(r"^\d{1,3}$")


RE_TOC_PAGE_SUFFIX = re.compile(
    r"(\d{1,4})\s*[\].)\-–—]*\s*$",
    re.UNICODE,
)


RE_NONALNUM_MARKER = re.compile(
    r"^([^\w\s]+)\s+(.+)$",
    re.UNICODE,
)


# =====================================================================
# ALFANUMERICNE FAMILIJE MARKERA
# =====================================================================
ALNUM_FAMILIES = [
    ("arapski-3", re.compile(
        r"^(\d{1,2}\.\d{1,2}\.\d{1,2})\.?\s{1,4}(.+)$", re.UNICODE
    ), 1, 2),
    ("arapski-2", re.compile(
        r"^(\d{1,2}\.\d{1,2})\.?\s{1,4}(.+)$", re.UNICODE
    ), 1, 2),
    ("rimski", re.compile(
        r"^(I{1,3}|IV|V|VI{0,3}|IX|X{1,3})\.?\s{1,6}(.+)$", re.UNICODE
    ), 1, 2),
    ("arapski-1", re.compile(
        r"^(\d{1,2})\.\s{1,4}(.+)$", re.UNICODE
    ), 1, 2),
    ("veliko", re.compile(
        r"^([A-ZА-ШЂЈЉЊЋЏ])\.\s{1,3}(.+)$", re.UNICODE
    ), 1, 2),
    ("malo", re.compile(
        r"^([a-zа-шђјљњћџ])\.\s{1,3}(.+)$", re.UNICODE
    ), 1, 2),
    ("poglavlje", re.compile(
        r"^(ПОГЛАВЉЕ|POGLAVLJE|Poglavlje|Поглавље)\s+(\d+)\.\s*(.+)$",
        re.UNICODE | re.IGNORECASE,
    ), 2, 3),
]


# =====================================================================
# DETEKCIJA MARKERA (sa marker_text)
# =====================================================================

def detect_marker(text: str, nonalnum_registry: dict | None = None
                   ) -> tuple[str | None, str | None, str, str]:
    """
    Vraca (marker, id, naslov, marker_text).

    marker_text = PUNI tekst markera na pocetku reda (npr. "ПОГЛАВЉЕ 1.",
    "1.", "I.", "a."). Koristi se za tacno poklapanje u map_pages.py.
    Ako nema markera, marker_text je "".
    """
    for fam_name, pattern, id_group, title_group in ALNUM_FAMILIES:
        m = pattern.match(text)
        if m:
            id_ = m.group(id_group) if id_group else None
            title = m.group(title_group).strip() if title_group else text
            # marker_text = deo pre naslova
            if title_group:
                marker_end = m.start(title_group)
                marker_text = text[:marker_end].strip()
            else:
                marker_text = ""
            return fam_name, id_, title, marker_text

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
        return fam_name, None, title, marker

    return None, None, text, ""


# =====================================================================
# DETEKCIJA STILA
# =====================================================================

_WORD_STRIP = ".,;:!?()[]\"'«»„“"

_RE_MARKER_PREFIX = re.compile(
    r"^\s*("
    r"\d{1,2}\.\d{1,2}\.\d{1,2}\.?"
    r"|\d{1,2}\.\d{1,2}\.?"
    r"|[IVX]{1,4}\.?"
    r"|\d{1,2}\."
    r"|[a-zA-Zа-шђјљњћџА-ШЂЈЉЊЋЏ]\."
    r"|ПОГЛАВЉЕ\s+\d+\."
    r"|Poglavlje\s+\d+\."
    r")\s*",
    re.IGNORECASE | re.UNICODE,
)


def detect_style_family(text: str) -> str | None:
    """
    Vraca stilsku familiju: 'upper', 'mixed', ili None.
    """
    s = text.strip()
    if len(s) < 3:
        return None

    s_no_marker = _RE_MARKER_PREFIX.sub("", s).strip()
    if not s_no_marker:
        return None

    first = s_no_marker[0]
    if not first.isalpha() or not first.isupper():
        return None

    words = [w for w in s_no_marker.split() if any(c.isalpha() for c in w)]
    if not words:
        return None

    upper_words = 0
    other_words = 0
    for w in words:
        w_clean = w.strip(_WORD_STRIP)
        if len(w_clean) < 2:
            continue
        if w_clean.isupper():
            upper_words += 1
        else:
            other_words += 1

    total = upper_words + other_words
    if total < 1:
        if s_no_marker.isupper():
            return "upper"
        return "mixed"

    if upper_words / total >= 0.9:
        return "upper"
    return "mixed"