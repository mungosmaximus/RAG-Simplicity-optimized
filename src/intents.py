"""
Recnici za prepoznavanje namere korisnickog pitanja.

Namere:
  - curability      : izlecivost, trajnost
  - dosage          : doza leka, doziranje
  - symptoms        : simptomi, znaci, klinicka slika
  - prevention      : prevencija, sprečavanje
  - risk_factors    : faktori rizika, uzroci
  - comprehensive   : lista, sve, nabrajanje
  - reference       : citat, izvor, strana
  - procedural      : koraci, procedura
  - comparison      : poredjenje
  - causal          : uzrok, mehanizam
  - therapeutic     : terapija, lečenje, lek
  - diagnostic      : dijagnostika, kriterijumi
  - definitional    : definicija pojma
  - precise         : default (ako nista ne match-uje)

Prioritet:
  1. curability
  2. dosage
  3. symptoms
  4. prevention
  5. risk_factors
  6. comprehensive
  7. reference
  8. procedural
  9. comparison
  10. causal
  11. therapeutic
  12. diagnostic
  13. definitional
  14. precise
"""

import re


# =====================================================================
# 1) CURABILITY — izlecivost, trajnost
# =====================================================================
CURABILITY_KEYWORDS = [
    "izlečiti", "izlečiv", "izlečenje", "izlečiva",
    "da li se može izlečiti", "da li je izlečivo",
    "da li se izleči", "da li će proći",
    "hronično stanje", "hronična bolest", "trajno stanje",
    "trajno", "kura", "lek protiv",
    "cure", "curable", "curability",
    "is it curable", "can it be cured",
    "is it chronic", "is it permanent",
]


# =====================================================================
# 2) DOSAGE — doza leka
# =====================================================================
DOSAGE_KEYWORDS = [
    "doza", "doze", "doziranje", "dozirati", "dozira",
    "koliko mg", "koliko ml", "koliko grama", "koliko mikrograma",
    "maksimalna doza", "minimalna doza",
    "dnevna doza", "dnevne doze",
    "jedna doza", "jednu dozu", "dve doze",
    "dose", "dosage", "how much",
    "how many mg", "how many ml",
    "maximum dose", "daily dose",
]


# =====================================================================
# 3) SYMPTOMS — simptomi, znaci
# =====================================================================
SYMPTOMS_KEYWORDS = [
    "simptom", "simptomi", "simptoma", "simptome",
    "znak", "znaci", "znakova", "znake",
    "klinička slika", "kliničke slike",
    "manifestacija", "manifestacije",
    "kako se manifestuje", "kako se ispoljava",
    "kako se pokazuje",
    "symptoms", "signs",
    "clinical presentation", "manifestations",
]


# =====================================================================
# 4) PREVENTION — prevencija
# =====================================================================
PREVENTION_KEYWORDS = [
    "prevencija", "prevencije", "prevenciju",
    "preventivni", "preventivne", "preventivna",
    "sprečava", "sprečavanje", "sprečiti", "sprečimo",
    "kako se sprečava", "kako sprečiti",
    "mere prevencije", "mera prevencije",
    "vakcinacija", "vakcinacije", "imunizacija",
    "prevention", "prevent",
    "how to prevent", "preventive measures",
]


# =====================================================================
# 5) RISK_FACTORS — faktori rizika, uzroci
# =====================================================================
RISK_FACTORS_KEYWORDS = [
    "faktor rizika", "faktori rizika", "faktora rizika",
    "faktore rizika", "faktorima rizika",
    "rizični faktor", "rizični faktori",
    "šta izaziva", "šta dovodi do", "šta prouzrokuje",
    "uzrok", "uzroci", "uzroka",
    "risk factor", "risk factors",
    "what causes", "what leads to",
]


# =====================================================================
# 6) COMPREHENSIVE — lista, sve, nabrajanje
# =====================================================================
COMPREHENSIVE_KEYWORDS = [
    "nabroji", "nabroj", "nabrojati", "nabrojim",
    "pobroji", "pobroj", "pobrojati", "pobrojim",
    "enumeriši", "enumerisati",
    "izlistaj", "izlistati", "izlistaj mi",
    "navedi", "navesti", "navodim",
    "pobrojanje",
    "koje sve", "koji sve", "koja sve", "ko sve",
    "sve", "svi", "sva",
    "sve o", "svi o", "sve vezano",
    "lista", "spisak", "popis", "pregled",
    "lista svega", "kompletan spisak",
    "sumiraj", "sumirati", "sažmi", "sažeti",
    "rezimiraj", "rezimirati",
    "pregledaj", "pregled",
    "koliko ima", "koliko postoji", "koliko ukupno",
    "list", "enumerate", "all", "every",
    "summarize", "summary", "overview",
    "how many", "which", "what are all",
]


# =====================================================================
# 7) REFERENCE — citat, izvor
# =====================================================================
REFERENCE_KEYWORDS = [
    "gde piše", "gde se navodi", "gde je navedeno",
    "prema", "citat", "citiraj", "citiraj mi",
    "izvor", "izvori", "izvora",
    "referenca", "reference", "referenci",
    "strana", "na strani", "koja strana",
    "where is", "cite", "citation", "source", "reference",
    "page", "on page",
]


# =====================================================================
# 8) PROCEDURAL — koraci, procedura
# =====================================================================
PROCEDURAL_KEYWORDS = [
    "koraci", "korak", "koraka", "koracima",
    "prvi korak", "drugi korak", "sledeći korak",
    "procedura", "procedure", "proceduru",
    "protokol", "protokoli", "protokola",
    "algoritam", "algoritmi", "algoritma",
    "postupak", "postupci", "postupka",
    "kako se sprovodi", "kako se izvodi",
    "kako se radi", "kako se primenjuje",
    "redosled", "faze", "etape",
    "vodič", "uputstvo", "uputstva",
    "steps", "procedure", "protocol", "algorithm",
    "how to", "guide",
]


# =====================================================================
# 9) COMPARISON — poredjenje
# =====================================================================
COMPARISON_KEYWORDS = [
    "razlika", "razlike", "različitost", "razlikuje",
    "razlikuju", "razlika između",
    "sličnost", "sličnosti", "slično",
    "uporedi", "uporediti", "poređenje", "poredi",
    "bolje", "gore", "bolji", "gori",
    "umesto", "alternativa", "alternativno",
    "vs", "versus",
    "koja je razlika",
    "difference", "compare", "similarity",
    "better", "worse", "instead", "alternative",
]


# =====================================================================
# 10) CAUSAL — uzrok, mehanizam
# =====================================================================
CAUSAL_KEYWORDS = [
    "zašto", "zbog čega", "zbog",
    "uzrokuje", "uzrokuju", "izaziva", "izazivaju",
    "dovodi do", "dovode do",
    "posledica", "posledice", "efekat", "efekti",
    "uticaj", "utiče",
    "mehanizam", "mehanizmi", "mehanizma",
    "kako nastaje", "kako se razvija", "kako se javlja",
    "patogeneza", "patofiziologija",
    "why", "cause", "causes", "mechanism",
    "leads to", "results in",
]


# =====================================================================
# 11) THERAPEUTIC — terapija, lečenje
# =====================================================================
THERAPEUTIC_KEYWORDS = [
    "terapija", "terapije", "terapiju", "terapijski",
    "tretman", "tretmani", "tretmana",
    "lečenje", "lečenja", "lečiti", "leči", "leče",
    "lek", "lekovi", "lekova", "lekovima",
    "preparat", "preparati", "medikament",
    "režim", "režimi", "režima",
    "kako lečiti", "čime lečiti",
    "indikacija", "indikacije",
    "therapy", "treatment", "drug", "medication",
    "indication",
]


# =====================================================================
# 12) DIAGNOSTIC — dijagnostika
# =====================================================================
DIAGNOSTIC_KEYWORDS = [
    "dijagnoza", "dijagnoze", "dijagnozu", "dijagnozi",
    "dijagnostika", "dijagnostike",
    "dijagnostički", "dijagnostikovati",
    "kriterijum", "kriterijumi", "kriterijuma",
    "test", "testovi", "testova", "testiranje",
    "pregled", "pregledi", "pregleda",
    "analiza", "analize", "analiza",
    "potvrda", "potvrditi",
    "kako se dijagnostikuje",
    "spirometrija", "spirometrijski",
    "fev1", "fvc",
    "merenje", "merenja",
    "diagnosis", "diagnostic", "criteria",
    "test", "exam", "measurement",
]


# =====================================================================
# 13) DEFINITIONAL — definicija pojma
# =====================================================================
DEFINITIONAL_KEYWORDS = [
    "definicija", "definicije", "definiciju",
    "definiši", "definiši mi",
    "šta znači", "značenje",
    "objašnjenje", "objasni", "objasniti",
    "termin", "termini", "termina",
    "pojam", "pojmovi", "pojma",
    "definition", "define", "meaning", "explain",
]


# =====================================================================
# 14) PRECISE — default (ako nista ne match-uje)
# =====================================================================
PRECISE_KEYWORDS = [
    "šta je", "šta su", "šta se",
    "koja je", "koji je", "koje je",
    "kada", "kada se", "kada je",
    "gde", "gde se", "gde je",
    "kako", "kako se", "kako je",
    "kolika", "koliki", "koliko iznosi",
    "da li", "da li je",
    "what is", "what are", "when", "where", "how",
    "which is", "is there",
]


# =====================================================================
# MAPA: namera -> lista kljucnih reci
# =====================================================================
INTENT_DICTS = {
    "curability":     CURABILITY_KEYWORDS,
    "dosage":         DOSAGE_KEYWORDS,
    "symptoms":       SYMPTOMS_KEYWORDS,
    "prevention":     PREVENTION_KEYWORDS,
    "risk_factors":   RISK_FACTORS_KEYWORDS,
    "comprehensive":  COMPREHENSIVE_KEYWORDS,
    "reference":      REFERENCE_KEYWORDS,
    "procedural":     PROCEDURAL_KEYWORDS,
    "comparison":     COMPARISON_KEYWORDS,
    "causal":         CAUSAL_KEYWORDS,
    "therapeutic":    THERAPEUTIC_KEYWORDS,
    "diagnostic":     DIAGNOSTIC_KEYWORDS,
    "definitional":   DEFINITIONAL_KEYWORDS,
    "precise":        PRECISE_KEYWORDS,
}


# =====================================================================
# PRIORITET (ako upit match-uje vise namera)
# =====================================================================
INTENT_PRIORITY = [
    "curability",     # 1. Najcesce pitanje
    "dosage",         # 2. Doza leka
    "symptoms",       # 3. Simptomi
    "prevention",     # 4. Prevencija
    "risk_factors",   # 5. Faktori rizika
    "comprehensive",  # 6. Lista/sve
    "reference",      # 7. Citat/izvor
    "procedural",     # 8. Koraci
    "comparison",     # 9. Poredjenje
    "causal",         # 10. Uzrok
    "therapeutic",    # 11. Terapija
    "diagnostic",     # 12. Dijagnostika
    "definitional",   # 13. Definicija
    "precise",        # 14. Default
]


# =====================================================================
# NORMALIZACIJA UPITA
# =====================================================================

def normalize_query(query: str) -> str:
    """Normalizuje upit za prepoznavanje namere."""
    q = query.strip().lower()
    q = re.sub(r"[?!.,;:]+$", "", q)
    q = re.sub(r"\s+", " ", q)
    return q


# =====================================================================
# GLAVNA FUNKCIJA
# =====================================================================

def detect_intent(query: str) -> str:
    """
    Vraca naziv namere za dati upit.
    Ako nista ne match-uje, vraca "precise".
    """
    q = normalize_query(query)

    # Nadji sve namere koje se pojavljuju u upitu
    detected = []
    for intent, keywords in INTENT_DICTS.items():
        for kw in keywords:
            if kw in q:
                detected.append(intent)
                break

    if not detected:
        return "precise"

    # Vrati po prioritetu
    for intent in INTENT_PRIORITY:
        if intent in detected:
            return intent

    return "precise"


def is_comprehensive(query: str) -> bool:
    """Kratka provera da li je namera comprehensive."""
    return detect_intent(query) == "comprehensive"


# =====================================================================
# TEST
# =====================================================================

if __name__ == "__main__":
    test_queries = [
        # Curability
        "Da li se astma može izlečiti?",
        "Da li je HOBP hronično stanje?",
        "Da li se HOBP može izlečiti?",
        # Dosage
        "Koja je doza kortikosteroida?",
        "Koliko mg prednizona?",
        "Koja je maksimalna doza?",
        # Symptoms
        "Koji su simptomi HOBP?",
        "Kako se manifestuje astma?",
        "Koji znaci ukazuju na HOBP?",
        # Prevention
        "Kako se sprečava HOBP?",
        "Koje su mere prevencije?",
        "Da li treba vakcinacija?",
        # Risk factors
        "Koji su faktori rizika za HOBP?",
        "Šta izaziva astmu?",
        # Comprehensive
        "Nabroji sve preporuke o vakcinaciji",
        "Koje su sve mere lečenja?",
        # Reference
        "Gde piše o vakcinaciji?",
        "Citiraj preporuku 9.3",
        # Procedural
        "Koji su koraci za prestanak pušenja?",
        # Comparison
        "Koja je razlika između HOBP i astme?",
        # Causal
        "Zašto nastaje HOBP?",
        # Therapeutic
        "Kako se leči egzacerbacija?",
        # Diagnostic
        "Kako se dijagnostikuje HOBP?",
        # Definitional
        "Definicija HOBP",
        "Šta znači FEV1?",
        # Precise (default)
        "HOBP",
    ]

    print(f"{'Upit':60s} -> Namera")
    print("=" * 80)
    for q in test_queries:
        intent = detect_intent(q)
        print(f"{q:60s} -> {intent}")