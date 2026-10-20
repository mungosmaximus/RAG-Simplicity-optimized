"""
Faza 5.5 — normalizacija entiteta (Python, deterministic).

Za svaki chunk iz data/questions/entities/<source>.jsonl:
  1) Konvertuj cirilicu u latinicu (unutar svih termina).
  2) Prevedi najcesce engleske termine u srpske (prosirena mapa).
  3) Fuzzy correction — ispravi greske u kucanju (boljes -> bolest).
  4) Normalizuj kategorije (primarna kategorija za svaki termin).
  5) Ukloni predugacke termine (> 100 znakova).
  6) Ukloni duplikate i prazne termine.

Izlaz: data/questions/entities_normalized/<source>.jsonl

Izvor:  data/questions/entities/*.jsonl
Izlaz:  data/questions/entities_normalized/*.jsonl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from tqdm import tqdm


# --- Konfiguracija ---
INPUT_DIR = Path("data/questions/entities")
OUTPUT_DIR = Path("data/questions/entities_normalized")

# Fuzzy correction
FUZZY_THRESHOLD = 0.82       # min slicnost za korekciju
FUZZY_MIN_LEN = 5            # ne primenjuj na kratke termine (< 5 znakova)

# Filter za predugacke termine
MAX_TERM_LENGTH = 100


# =====================================================================
# 1) KONVERZIJA CIRILICA -> LATINICA
# =====================================================================

_CYR_TO_LAT = {
    # Mala slova
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'ђ': 'đ',
    'е': 'e', 'ж': 'ž', 'з': 'z', 'и': 'i', 'ј': 'j', 'к': 'k',
    'л': 'l', 'љ': 'lj', 'м': 'm', 'н': 'n', 'њ': 'nj', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'ћ': 'ć', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'č', 'џ': 'dž', 'ш': 'š',
    # Velika slova
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Ђ': 'Đ',
    'Е': 'E', 'Ж': 'Ž', 'З': 'Z', 'И': 'I', 'Ј': 'J', 'К': 'K',
    'Л': 'L', 'Љ': 'Lj', 'М': 'M', 'Н': 'N', 'Њ': 'Nj', 'О': 'O',
    'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'Ћ': 'Ć', 'У': 'U',
    'Ф': 'F', 'Х': 'H', 'Ц': 'C', 'Ч': 'Č', 'Џ': 'Dž', 'Ш': 'Š',
}


def to_latinica(text: str) -> str:
    """Konvertuje cirilicu u latinicu (mesovite termine cisti)."""
    return ''.join(_CYR_TO_LAT.get(c, c) for c in text)


# =====================================================================
# 2) PREVOD ENGLESKIH TERMINA -> SRPSKI
# =====================================================================

_EN_TO_SR = {
    # --- Bolesti ---
    "asthma": "astma",
    "copd": "hobp",
    "chronic obstructive pulmonary disease": "hronična opstruktivna bolest pluća",
    "chronic airway obstruction": "hronična opstrukcija disajnih puteva",
    "emphysema": "emfizem",
    "pneumonia": "pneumonija",
    "atrial fibrillation": "atrijalna fibrilacija",
    "alpha-1-antitrypsin deficiency": "nedostatak alfa-1-antitripsina",
    "pulmonary embolism": "plućna embolija",
    "lung cancer": "karcinom pluća",
    "tuberculosis": "tuberkuloza",
    "bronchiectasis": "bronhiektazije",
    "asthma exacerbation": "egzacerbacija astme",
    "copd exacerbation": "egzacerbacija hobp",
    "abdominal pain": "bol u stomaku",
    "airway obstruction": "opstrukcija disajnih puteva",
    "chronic bronchitis": "hronični bronhitis",
    "respiratory failure": "respiratorna insuficijencija",
    "acute exacerbation": "akutna egzacerbacija",
    "air trapping": "zarobljavanje vazduha",
    "myocardial infarction": "infarkt miokarda",
    "cardiovascular mortality": "kardiovaskularni mortalitet",
    "death": "smrt",
    "hyperinflation": "hiperinflacija",
    "inactivated": "inaktivirana",

    # --- Lekovi ---
    "corticosteroid": "kortikosteroid",
    "oral corticosteroid": "oralni kortikosteroid",
    "inhaled corticosteroid": "inhalacioni kortikosteroid",
    "antibiotic": "antibiotik",
    "antibiotic a": "antibiotik a",
    "bronchodilator": "bronhodilatator",
    "azithromycin": "azitromicin",
    "budesonide": "budezonid",
    "carbocistein": "karbocistein",
    "fluticasone furoate": "flutikazon furoat",
    "anti-inflammatory reliever": "antiinflamatorni reliver",
    "anti-interleukin 5": "anti-interleukin 5",
    "anti-thymic stromal lymphopoietin": "anti-timični stromalni limfopoetin",
    "aclidinium bromide": "aklidinijum bromid",
    "ace-inhibitor": "ace-inhibitor",
    "alcohol": "alkohol",

    # --- Simptomi ---
    "dyspnea": "dispneja",
    "dispnea": "dispneja",
    "cough": "kašalj",
    "sputum": "sputum",
    "wheezing": "zviždanje",
    "symptomatic": "simptomatski",

    # --- Testovi / mere ---
    "forced expiratory volume in 1 second": "forsirani ekspiratorni volumen u prvoj sekundi",
    "forced expiratory volume (1 second)": "forsirani ekspiratorni volumen u prvoj sekundi",
    "forced vital capacity": "forsirani vitalni kapacitet",
    "diffusing capacity in the lung for carbon monoxide": "difuzioni kapacitet pluća za ugljen-monoksid",
    "fractional exhaled nitric oxide": "frakcioni izdahnuti azot-monoksid",
    "asthma control test": "test kontrole astme",
    "asthma control questionnaire": "upitnik kontrole astme",
    "body mass index": "indeks telesne mase",
    "low-dose ct": "niskodozni ct",
    "ct scan": "ct skeniranje",
    "copd assessment test": "cat test",
    "alfa-1 at u serumu": "alfa-1 antitripsin u serumu",

    # --- Ostalo ---
    "mortality": "mortalitet",
    "morbidity": "morbiditet",
    "prevalence": "prevalencija",
    "incidence": "incidenca",
    "children": "deca",
    "adolescents": "adolescenti",
    "adults": "odrasli",
    "pregnancy": "trudnoća",
    "smoking": "pušenje",
    "vaccination": "vakcinacija",
    "immunization": "imunizacija",
    "influenza": "grip",
    "covid-19": "covid-19",
    "pneumococcal": "pneumokokni",
    "anti-pneumococcal vaccination": "antipneumokokna vakcinacija",
    "covid-19 vaccine": "covid-19 vakcina",
    "covid-19 vaccines": "covid-19 vakcine",
    "astrazeneca skbio azd1222-covid-19 vaccine": "astrazeneka covid-19 vakcina",
    "covid-19 vaccine astrazeneca (vaxzevria)": "astrazeneka covid-19 vakcina",
    "covid-19 vaccine moderna": "moderna covid-19 vakcina",
    "comirnaty": "komirnati",
    "chadox1 ncov-19 corona virus vaccine": "astrazeneka covid-19 vakcina",
    "chadox1-s(recombinant)": "astrazeneka covid-19 vakcina",
    "covishield": "kovishild",
    "inhaled": "inhalaciono",
    "oral": "oralno",
    "intravenous": "intravenski",
    "subcutaneous": "subkutano",
    "anxiety": "anksioznost",
    "anxiety symptoms": "simptomi anksioznosti",
    "exacerbation": "egzacerbacija",
    "exacerbations": "egzacerbacije",
    "exacerbations of hobp": "egzacerbacije hobp",
    "influenza vaccine": "vakcina protiv gripa",
}


def translate_term(term: str) -> str:
    """Prevedi engleski termin u srpski (ako postoji u mapi)."""
    t = term.strip().lower()
    return _EN_TO_SR.get(t, t)


# =====================================================================
# 3) FUZZY CORRECTION — ISPRAVI GRESKE U KUCANJU
# =====================================================================

# Lista poznatih termina (za fuzzy match)
# Ovo su termini koji se cesto pojavljuju sa greskama.
_KNOWN_TERMS = {
    # Bolesti
    "bolest", "bolesti", "anemija", "astma", "hobp", "emfizem",
    "pneumonija", "karcinom", "tuberkuloza", "bronhiektazije",
    "hiperinflacija", "komorbiditet", "komorbiditeti",
    "depresija", "anksioznost", "osteoporoza",
    "respiratorna insuficijencija", "akutna respiratorna insuficijencija",
    "akutna hiperkapnijska respiratorna insuficijencija",
    "akutna globalna respiratorna insuficijencija",
    "akutna egzacerbacija", "akutna egzacerbacija hobp", "aehobp",

    # Lekovi
    "antibiotik", "antibiotici", "kortikosteroid", "kortikosteroidi",
    "bronhodilatator", "aklidinijum", "aklidinijum bromid",
    "salbutamol", "budezonid", "prednizon", "azitromicin",
    "karbocistein", "antiholinergik", "ace-inhibitor", "alopurinol",

    # Opsti medicinski
    "lečenje", "bolničko lečenje", "bolničko", "terapija",
    "diagnoza", "dijagnoza", "procedura", "intervencija",
    "simptom", "simptomi", "komplikacija", "komplikacije",
    "vakcinacija", "imunizacija", "infekcija", "infekcije",
    "respiratorna", "insuficijencija", "opstrukcija",
    "dispneja", "kašalj", "sputum", "intervencije",
    "pogoršanje", "češće", "hronična",
    "karcinom", "pogoršanje", "ventrikularne", "aritmije",
    "češće", "intervencije", "bronhogeni karcinom",

    # Mere / testovi
    "spirometrija", "fev1", "fvc", "test", "merenje",
    "bulektomija", "auskultacija", "auskulturna analiza",
    "bode indeks", "cat test", "ct skeniranje",

    # Faktori
    "pušenje", "duvan", "alkohol", "gojaznost",
}


def fuzzy_correct(term: str) -> str:
    """
    Ako je termin > FUZZY_THRESHOLD slican poznatom, zameni ga.
    Ne primenjuj na kratke termine (< FUZZY_MIN_LEN).
    """
    if not term or len(term) < FUZZY_MIN_LEN:
        return term
    if term in _KNOWN_TERMS:
        return term

    best_match = None
    best_ratio = FUZZY_THRESHOLD

    for known in _KNOWN_TERMS:
        # Ako su duzine drasticno razlicite, preskoci
        if abs(len(term) - len(known)) > 3:
            continue
        ratio = SequenceMatcher(None, term, known).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = known

    return best_match if best_match else term


# =====================================================================
# 4) NORMALIZACIJA KATEGORIJA
# =====================================================================

_PRIMARY_CATEGORY = {
    # Bolesti -> samo disease
    "astma": "disease",
    "hobp": "disease",
    "hronična opstruktivna bolest pluća": "disease",
    "emfizem": "disease",
    "pneumonija": "disease",
    "karcinom pluća": "disease",
    "tuberkuloza": "disease",
    "bronhiektazije": "disease",
    "plućna embolija": "disease",
    "atrijalna fibrilacija": "disease",
    "nedostatak alfa-1-antitripsina": "disease",
    "hronična opstrukcija disajnih puteva": "disease",
    "respiratorna insuficijencija": "disease",
    "opstrukcija disajnih puteva": "disease",
    "hiperinflacija": "disease",
    "akutna egzacerbacija": "disease",
    "akutna egzacerbacija hobp": "disease",
    "aehobp": "disease",
    "akutna respiratorna insuficijencija": "disease",
    "akutna hiperkapnijska respiratorna insuficijencija": "disease",
    "akutna globalna respiratorna insuficijencija": "disease",

    # Lekovi -> samo drug
    "kortikosteroid": "drug",
    "oralni kortikosteroid": "drug",
    "inhalacioni kortikosteroid": "drug",
    "antibiotik": "drug",
    "bronhodilatator": "drug",
    "azitromicin": "drug",
    "budezonid": "drug",
    "karbocistein": "drug",
    "flutikazon furoat": "drug",
    "antiinflamatorni reliver": "drug",
    "saba": "drug",
    "laba": "drug",
    "lama": "drug",
    "ics": "drug",
    "salbutamol": "drug",
    "prednizon": "drug",
    "aklidinijum bromid": "drug",
    "aklidinijum": "drug",
    "antiholinergik": "drug",
    "ace-inhibitor": "drug",
    "alopurinol": "drug",
    "ase-inhibitori": "drug",

    # Testovi -> samo test
    "fev1": "test",
    "fvc": "test",
    "spirometrija": "test",
    "cat": "test",
    "mmrc": "test",
    "crp": "test",
    "ct": "test",
    "dlco": "test",
    "6mwd": "test",
    "feno": "test",
    "test kontrole astme": "test",
    "upitnik kontrole astme": "test",
    "niskodozni ct": "test",
    "forsirani ekspiratorni volumen u prvoj sekundi": "test",
    "forsirani vitalni kapacitet": "test",
    "difuzioni kapacitet pluća za ugljen-monoksid": "test",
    "frakcioni izdahnuti azot-monoksid": "test",
    "bulektomija": "test",
    "auskultacija": "test",
    "auskulturna analiza": "test",
    "bode indeks": "test",
    "cat test": "test",
    "ct skeniranje": "test",

    # Simptomi -> samo symptom
    "dispneja": "symptom",
    "kašalj": "symptom",
    "sputum": "symptom",
    "zviždanje": "symptom",
    "bol u stomaku": "symptom",

    # Mere -> samo measure
    "indeks telesne mase": "measure",
    "vršni ekspiratorni protok": "measure",

    # Vakcine -> samo vaccine
    "komirnati": "vaccine",
    "astrazeneka covid-19 vakcina": "vaccine",
    "moderna covid-19 vakcina": "vaccine",
    "antipneumokokna vakcinacija": "vaccine",
    "kovishild": "vaccine",

    # Komplikacije -> samo complication
    "smrt": "complication",
    "infarkt miokarda": "complication",
    "kardiovaskularni mortalitet": "complication",
    "zarobljavanje vazduha": "complication",
    "abnormalan razvoj": "risk_factor",
    "abnormalnosti plućne funkcije": "test",
    "aspergillus": "cause",
    "atopijska konstitucija": "risk_factor",
    "anksioznost": "comorbidity",
    "simptomi anksioznosti": "symptom",
    "egzacerbacija": "complication",
    "egzacerbacije": "complication",
    "egzacerbacije hobp": "complication",
    "bronhogeni karcinom": "disease",
    "vakcina protiv gripa": "vaccine",

    # Procedure -> samo procedure
    "bolničko lečenje": "procedure",
    "kompjuterizovana tomografija": "procedure",

    # Komorbiditeti -> samo comorbidity
    "depresija": "comorbidity",
    "anksioznost": "comorbidity",
    "osteoporoza": "comorbidity",
    "arterijska hipertenzija": "comorbidity",
    "atrijalna fibrilacija": "comorbidity",
}


# =====================================================================
# 5) GLAVNA NORMALIZACIJA TERMINA
# =====================================================================

def normalize_entity(term: str) -> str | None:
    """
    Normalizuje jedan termin:
      1) cirilica -> latinica
      2) engleski -> srpski
      3) fuzzy correction
      4) lowercase, ocisti razmake
      5) filter predugackih
    Vraca None ako termin treba ukloniti.
    """
    if not term or not term.strip():
        return None

    t = term.strip()
    t = to_latinica(t)
    t = translate_term(t)
    t = t.strip().lower()
    t = re.sub(r"\s+", " ", t)

    # Fuzzy correction
    t = fuzzy_correct(t)

    # Filter predugackih
    if len(t) > MAX_TERM_LENGTH:
        return None

    # Filter ako je samo broj ili kratko
    if len(t) < 2:
        return None

    return t


def normalize_entities_dict(entities: dict) -> dict:
    """
    Normalizuje dict entiteta:
      - svaki termin: cirilica->latinica, engleski->srpski, fuzzy
      - normalizacija kategorija (primarna kategorija)
      - deduplikacija
    """
    # 1) Normalizuj sve termine unutar svake kategorije
    normalized = defaultdict(set)
    for cat, terms in entities.items():
        for term in terms:
            norm = normalize_entity(term)
            if norm:
                normalized[cat].add(norm)

    # 2) Normalizuj kategorije (primarna kategorija)
    final = defaultdict(set)
    for cat, terms in normalized.items():
        for term in terms:
            primary = _PRIMARY_CATEGORY.get(term)
            if primary:
                if primary == cat:
                    final[cat].add(term)
                # inace: preskoci
            else:
                final[cat].add(term)

    # 3) Vrati kao dict sa listama, sortirano
    return {
        cat: sorted(list(terms))
        for cat, terms in final.items()
    }


# =====================================================================
# 6) GLAVNI TOK
# =====================================================================

def process_file(input_path: Path, output_path: Path) -> dict:
    """Obradi jedan .jsonl fajl i vrati statistiku."""
    print(f"\n=== {input_path.name} ===")

    stats = {
        "total_chunks": 0,
        "with_entities_before": 0,
        "with_entities_after": 0,
        "terms_before": 0,
        "terms_after": 0,
        "removed_long": 0,
        "fuzzy_corrected": 0,
    }

    results = []

    with open(input_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    for data in tqdm(lines, desc=f"  {input_path.stem[:30]}"):
        stats["total_chunks"] += 1

        entities = data.get("entities", {})
        terms_before = sum(len(v) for v in entities.values() if v)
        if terms_before > 0:
            stats["with_entities_before"] += 1
        stats["terms_before"] += terms_before

        # Broj predugackih pre normalizacije
        for cat_terms in entities.values():
            for t in cat_terms:
                if len(t) > MAX_TERM_LENGTH:
                    stats["removed_long"] += 1

        normalized = normalize_entities_dict(entities)
        terms_after = sum(len(v) for v in normalized.values())
        if terms_after > 0:
            stats["with_entities_after"] += 1
        stats["terms_after"] += terms_after

        data["entities"] = normalized
        results.append(data)

    # Sacuvaj
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"  Sacuvano: {output_path}")
    return stats


def main():
    if not INPUT_DIR.exists():
        print(f"Nema: {INPUT_DIR}")
        return

    input_files = sorted(INPUT_DIR.glob("*.jsonl"))
    if not input_files:
        print(f"Nema .jsonl u {INPUT_DIR}")
        return

    print(f"Nadjeno {len(input_files)} fajlova.")

    all_stats = {}

    for input_path in input_files:
        output_path = OUTPUT_DIR / input_path.name
        stats = process_file(input_path, output_path)
        all_stats[input_path.stem] = stats

    # Finalna statistika
    print(f"\n{'=' * 60}")
    print(f"GOTOVO")
    print(f"{'=' * 60}")

    for source, stats in all_stats.items():
        print(f"\n{source}:")
        print(f"  Ukupno chunkova:          {stats['total_chunks']}")
        print(f"  Sa entitetima (pre):      {stats['with_entities_before']}")
        print(f"  Sa entitetima (posle):    {stats['with_entities_after']}")
        print(f"  Termina (pre):            {stats['terms_before']}")
        print(f"  Termina (posle):          {stats['terms_after']}")
        if stats['terms_before'] > 0:
            reduction = (1 - stats['terms_after'] / stats['terms_before']) * 100
            print(f"  Redukcija:                {reduction:.1f}%")
        print(f"  Uklonjeno predugackih:    {stats['removed_long']}")

    print(f"\nIzlaz: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()