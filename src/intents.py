"""
Recnici za prepoznavanje namere korisnickog pitanja.

Namere:
  - comprehensive : trazi listu/sve/pregled (nabrajanje)
  - precise       : trazi jednu cinjenicu/definiciju
  - procedural    : trazi korake/proceduru
  - comparison    : trazi poredjenje
  - causal        : trazi uzrok/mehanizam
  - therapeutic   : trazi terapiju/lek/dozu
  - diagnostic    : trazi dijagnostiku/kriterijume
  - definitional  : trazi definiciju pojma
  - reference     : trazi citat/izvor/stranu

Prioritet:
  1. comprehensive (ako ima bilo koju rec, ide u comprehensive rezim)
  2. reference (ako trazi citat)
  3. ostale (po redu pojavljivanja reci u upitu)
"""

# --- COMPREHENSIVE: lista, sve, nabrajanje ---
COMPREHENSIVE_KEYWORDS = [
    # Nabrajanje
    "nabroji", "nabroj", "nabrojati", "nabrojim",
    "pobroji", "pobroj", "pobrojati", "pobrojim",
    "enumeriši", "enumerisati",
    "izlistaj", "izlistati", "izlistaj mi",
    "navedi", "navesti", "navodim",
    "pobrojanje",
    # Sve / svi / sva
    "koje sve", "koji sve", "koja sve", "ko sve",
    "sve", "svi", "sva",
    "sve o", "svi o", "sve vezano",
    # Lista / spisak
    "lista", "spisak", "popis", "pregled",
    "lista svega", "kompletan spisak",
    # Sažetak
    "sumiraj", "sumirati", "sažmi", "sažeti",
    "rezimiraj", "rezimirati",
    "pregledaj", "pregled",
    # Koliko
    "koliko ima", "koliko postoji", "koliko ukupno",
    # Engleski
    "list", "enumerate", "all", "every",
    "summarize", "summary", "overview",
    "how many", "which", "what are all",
]


# --- PRECISE: jedna cinjenica/definicija ---
PRECISE_KEYWORDS = [
    # Pitanja
    "šta je", "šta su", "šta znači", "šta se",
    "koja je", "koji je", "koje je",
    "kada", "kada se", "kada je",
    "gde", "gde se", "gde je",
    "kako", "kako se", "kako je",
    "kolika", "koliki", "koliko iznosi",
    "zašto", "zbog čega",
    "da li", "da li je",
    # Engleski
    "what is", "what are", "when", "where", "how",
    "which is", "is there",
]


# --- PROCEDURAL: koraci, procedura ---
PROCEDURAL_KEYWORDS = [
    "koraci", "korak", "koraka",
    "prvi korak", "drugi korak", "sledeći korak",
    "procedura", "protokol", "algoritam",
    "postupak", "postupci",
    "kako se sprovodi", "kako se izvodi",
    "kako se radi", "kako se primenjuje",
    "redosled", "faze", "etape",
    "vodič", "uputstvo", "uputstva",
    # Engleski
    "steps", "procedure", "protocol", "algorithm",
    "how to", "guide",
]


# --- COMPARISON: poredjenje ---
COMPARISON_KEYWORDS = [
    "razlika", "razlike", "različitost", "razlikuje",
    "sličnost", "sličnosti", "slično",
    "uporedi", "uporediti", "poređenje", "poredi",
    "bolje", "gore", "bolji", "gori",
    "umesto", "alternativa", "alternativno",
    "vs", "versus",
    "koja je razlika",
    # Engleski
    "difference", "compare", "similarity",
    "better", "worse", "instead", "alternative",
]


# --- CAUSAL: uzrok, mehanizam ---
CAUSAL_KEYWORDS = [
    "zašto", "zbog čega", "zbog",
    "uzrok", "uzroci", "uzrokuje", "uzrokuju",
    "izaziva", "izazivaju", "dovodi do", "dovode do",
    "posledica", "posledice", "efekat", "efekti",
    "uticaj", "utiče",
    "mehanizam", "mehanizmi",
    "kako nastaje", "kako se razvija", "kako se javlja",
    # Engleski
    "why", "cause", "causes", "mechanism",
    "leads to", "results in",
]


# --- THERAPEUTIC: terapija, lek, doza ---
THERAPEUTIC_KEYWORDS = [
    "terapija", "terapije", "terapijski",
    "tretman", "tretmani",
    "lečenje", "lečiti", "leči",
    "lek", "lekovi", "lekova", "lekovima",
    "doza", "doze", "doziranje",
    "preparat", "preparati", "medikament",
    "režim", "režimi",
    "kako lečiti", "čime lečiti",
    "indikacija", "indikacije",
    "kontraindikacija", "kontraindikacije",
    # Engleski
    "therapy", "treatment", "drug", "dose",
    "medication", "indication", "contraindication",
]


# --- DIAGNOSTIC: dijagnostika ---
DIAGNOSTIC_KEYWORDS = [
    "dijagnoza", "dijagnoze", "dijagnostika",
    "dijagnostički", "dijagnostikovati",
    "kriterijum", "kriterijumi",
    "test", "testovi", "testiranje",
    "pregled", "pregledi",
    "analiza", "analize",
    "potvrda", "potvrditi",
    "kako se dijagnostikuje",
    "spirometrija", "spirometrijski",
    "fev1", "fvc",
    "merenje", "merenja",
    # Engleski
    "diagnosis", "diagnostic", "criteria",
    "test", "exam", "measurement",
]


# --- DEFINITIONAL: definicija pojma ---
DEFINITIONAL_KEYWORDS = [
    "definicija", "definicije",
    "definiši", "definiši mi",
    "šta znači", "značenje",
    "objašnjenje", "objasni", "objasniti",
    "termin", "termini", "pojam", "pojmovi",
    # Engleski
    "definition", "define", "meaning", "explain",
]


# --- REFERENCE: citat, izvor ---
REFERENCE_KEYWORDS = [
    "gde piše", "gde se navodi", "gde je navedeno",
    "prema", "citat", "citiraj", "citiraj mi",
    "izvor", "izvori",
    "referenca", "reference",
    "strana", "na strani",
    # Engleski
    "where is", "cite", "citation", "source", "reference",
    "page",
]


# --- Prioritet namera (ako upit sadrzi vise) ---
INTENT_PRIORITY = [
    "comprehensive",   # 1. Najvisi prioritet — ako ima bilo koju rec
    "reference",       # 2. Citat/izvor
    "procedural",      # 3. Koraci
    "comparison",      # 4. Poredjenje
    "causal",          # 5. Uzrok
    "therapeutic",     # 6. Terapija
    "diagnostic",      # 7. Dijagnostika
    "definitional",    # 8. Definicija
    "precise",         # 9. Najnizi prioritet (default)
]


def detect_intent(query: str) -> str:
    """
    Vraca naziv namere za dati upit.
    Ako nista ne match-uje, vraca "precise".
    """
    q = query.lower()
    
    # Grupisi recnike po nameri
    dicts = {
        "comprehensive": COMPREHENSIVE_KEYWORDS,
        "precise": PRECISE_KEYWORDS,
        "procedural": PROCEDURAL_KEYWORDS,
        "comparison": COMPARISON_KEYWORDS,
        "causal": CAUSAL_KEYWORDS,
        "therapeutic": THERAPEUTIC_KEYWORDS,
        "diagnostic": DIAGNOSTIC_KEYWORDS,
        "definitional": DEFINITIONAL_KEYWORDS,
        "reference": REFERENCE_KEYWORDS,
    }
    
    # Nadji sve namere koje se pojavljuju u upitu
    detected = []
    for intent, keywords in dicts.items():
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


if __name__ == "__main__":
    # Test primeri
    test_queries = [
        "Nabroji sve preporuke o vakcinaciji",
        "Šta je FEV1/FVC?",
        "Koji su koraci za prestanak pušenja?",
        "Koja je razlika između HOBP i astme?",
        "Zašto nastaje HOBP?",
        "Koja je terapija za egzacerbaciju?",
        "Kako se dijagnostikuje HOBP?",
        "Definicija HOBP",
        "Gde piše o vakcinaciji?",
    ]
    
    for q in test_queries:
        print(f"{q:55s} -> {detect_intent(q)}")
