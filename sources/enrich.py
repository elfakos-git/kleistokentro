"""Event enrichment: closure dates + geographic area.

CLOSURE DATES — extract_days(text)
  Parses the dates a closure is IN EFFECT from Greek text. Handles the
  three patterns observed in real Diavgeia subjects plus news style:
    * range:    "από 06/07/2026 έως 25/09/2026" → every day expanded
    * day list: "στις 07, 08, 09 ... και 31-07-2026" → each day, that month
    * single:   "στις 05.07.2026"
    * no year:  "την Τρίτη 23/6" (news style) → NEAREST occurrence; if
      the nearest reading is already past (beyond a short grace), the
      event is OVER and yields no days at all — see _resolve_no_year.

  IMPORTANT: call this on the event TITLE only. The details field can
  carry the PUBLICATION date (e.g. Diavgeia's "(03/07/2026)"), which is
  exactly what the calendar must NOT show.

  Time-of-day strings ("ώρες 19.00΄ έως 07.00΄") can't false-match:
  every pattern requires a 4-digit year except the no-year one, which
  requires "/" (times use dots).

GEOGRAPHY — classify_area(text, url="")
  Tags an event Κέντρο (inside/near the δακτύλιος), Βόρεια, Δυτικά,
  Νότια or Ανατολικά by keyword lookup (municipalities, big roads,
  landmarks). First match wins, Κέντρο checked first. Events with
  coordinates in a Google-Maps url (TomTom) fall back to bearing from
  Syntagma when no keyword matches. Unknown → "" (shown untagged).
"""
import re
from datetime import date, timedelta

from . import norm_greek

# ---------------------------------------------------------------- dates
_D = r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})"

# Greek month names (genitive stems, accent-stripped — "5 Ιουλίου 2026").
# Stems chosen to avoid non-date words: "μαρτι" matches Μαρτίου but not
# μάρτυρες; "μαι" matches Μαΐου.
_MONTHS = {"ιανουαρι": 1, "φεβρουαρι": 2, "μαρτι": 3, "απριλι": 4,
           "μαι": 5, "ιουνι": 6, "ιουλι": 7, "αυγουστ": 8,
           "σεπτεμβρι": 9, "οκτωβρι": 10, "νοεμβρι": 11, "δεκεμβρι": 12}
_M = "(" + "|".join(_MONTHS) + r")\w*"
_DAYNUM = r"(\d{1,2})(?:ης|ας|α|η)?"

NAMED_RANGE_RE = re.compile(
    r"απο\s+(?:τις\s+|την\s+)?" + _DAYNUM +
    r"\s*(?:εως|μεχρι)\s*(?:και\s+)?(?:τις\s+|την\s+)?" + _DAYNUM +
    r"\s+" + _M + r"(?:\s+(\d{4}))?")
NAMED_PAIR_RE = re.compile(
    _DAYNUM + r"\s+και\s+(?:τη[νς]?\s+)?(?:[α-ωϊϋ]{3,12}\s+)?"
    + _DAYNUM + r"\s+" + _M + r"(?:\s+(\d{4}))?")
NAMED_DAY_RE = re.compile(_DAYNUM + r"\s+" + _M + r"(?:\s+(\d{4}))?")

RANGE_RE = re.compile(r"απο\s+" + _D +
                      r"\s*(?:εως|μεχρι)\s+(?:και\s+)?(?:τις\s+|την\s+)?" + _D)
DAYLIST_RE = re.compile(r"((?:\d{1,2}\s*,\s*)+\d{1,2})\s+και\s+"
                        r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})")
FULL_RE = re.compile(_D)
NOYEAR_RE = re.compile(r"(?<![\d/.\-])(\d{1,2})/(\d{1,2})(?![\d/.\-])")

MAX_RANGE_DAYS = 120   # a "range" longer than this is a parse error

# Traffic announcements are about the future or the very-recent past
# (an ongoing multi-day closure). So the window is asymmetric: a short
# past grace (a closure that began a few days ago is still live) and a
# long future horizon.
PAST_GRACE_DAYS, FUTURE_DAYS = 4, 300


def _month_no(stem_match: str) -> int:
    for stem, num in _MONTHS.items():
        if stem_match.startswith(stem):
            return num
    return 0


def _valid(d: int, m: int, y: int, today: date):
    """Validate an EXPLICIT-year date against the window of interest."""
    try:
        dt = date(y, m, d)
    except ValueError:
        return None
    lo = today - timedelta(days=PAST_GRACE_DAYS)
    hi = today + timedelta(days=FUTURE_DAYS)
    return dt if lo <= dt <= hi else None


def _resolve_no_year(d: int, m: int, today: date):
    """Year-less date ("23/6", "5 Ιουλίου"): the announcement means the
    occurrence NEAREST to today — that is how a human reader resolves
    it. Rank every candidate year by distance (ties broken toward the
    future), and only THEN judge the winner:
      * nearest is in the future, or in the past within the grace
        window → keep it (a closure that began days ago is still live);
      * nearest is past BEYOND the grace window → the event is OVER:
        return None, so it contributes no in-effect days at all.
    THE BUG THIS REPLACES: the old version discarded beyond-grace past
    candidates BEFORE ranking, so a finished closure ("Τρίτη 23/6"
    re-read on 03/07 from a stale tag page) fell through to NEXT YEAR
    and haunted the calendar as a ghost 2027 closure for a year.
    Dec/Jan boundary behaviour is unchanged: "3/1" read on 30/12 still
    resolves to January 3rd of the coming year — that IS the nearest
    occurrence. Nearest can never exceed ~183 days into the future, so
    no separate future cap is needed here."""
    best = None
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            cand = date(y, m, d)
        except ValueError:
            continue                     # e.g. 29/2 on a non-leap year
        delta = (cand - today).days
        rank = (abs(delta), delta < 0)   # distance first, then future
        if best is None or rank < best[0]:
            best = (rank, cand, delta)
    if best is None:
        return None
    _, cand, delta = best
    if delta < -PAST_GRACE_DAYS:
        return None      # nearest reading is already over → no days
    return cand


def extract_days(text: str, today: date | None = None) -> list[str]:
    """All in-effect days found in text, as sorted ISO strings."""
    today = today or date.today()
    t = norm_greek(text or "")
    days: set[date] = set()
    blank = lambda m: " " * len(m.group(0))   # consume matched spans

    def take_range(m):
        d1, m1, y1, d2, m2, y2 = (int(g) for g in m.groups())
        try:
            start, end = date(y1, m1, d1), date(y2, m2, d2)
        except ValueError:
            return blank(m)
        if start <= end and (end - start).days <= MAX_RANGE_DAYS:
            cur = start
            while cur <= end:
                if _valid(cur.day, cur.month, cur.year, today):
                    days.add(cur)
                cur += timedelta(days=1)
        else:   # weird range: keep endpoints only
            for x in (_valid(d1, m1, y1, today), _valid(d2, m2, y2, today)):
                if x:
                    days.add(x)
        return blank(m)

    def take_daylist(m):
        mo, yr = int(m.group(3)), int(m.group(4))
        for dd in re.findall(r"\d{1,2}", m.group(1)) + [m.group(2)]:
            x = _valid(int(dd), mo, yr, today)
            if x:
                days.add(x)
        return blank(m)

    def take_full(m):
        x = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)), today)
        if x:
            days.add(x)
        return blank(m)

    def _year(d, m, y):
        """Explicit year → validate it; year omitted → resolve to the
        nearest occurrence (news routinely drops the year); a nearest
        occurrence that is already past-beyond-grace means the event
        is over and yields nothing."""
        if y:
            return _valid(d, m, int(y), today)
        return _resolve_no_year(d, m, today)

    def take_named_range(m):
        d1, d2, mo = int(m.group(1)), int(m.group(2)), _month_no(m.group(3))
        a, b = _year(d1, mo, m.group(4)), _year(d2, mo, m.group(4))
        if a and b and a <= b and (b - a).days <= MAX_RANGE_DAYS:
            cur = a
            while cur <= b:
                days.add(cur)
                cur += timedelta(days=1)
        else:
            for x in (a, b):
                if x:
                    days.add(x)
        return blank(m)

    def take_named_pair(m):
        mo = _month_no(m.group(3))
        for dd in (m.group(1), m.group(2)):
            x = _year(int(dd), mo, m.group(4))
            if x:
                days.add(x)
        return blank(m)

    def take_named_day(m):
        x = _year(int(m.group(1)), _month_no(m.group(2)), m.group(3))
        if x:
            days.add(x)
        return blank(m)

    t = RANGE_RE.sub(take_range, t)
    t = DAYLIST_RE.sub(take_daylist, t)
    t = FULL_RE.sub(take_full, t)
    t = NAMED_RANGE_RE.sub(take_named_range, t)
    t = NAMED_PAIR_RE.sub(take_named_pair, t)
    t = NAMED_DAY_RE.sub(take_named_day, t)

    for m in NOYEAR_RE.finditer(t):   # "23/6" news style
        d_, mo = int(m.group(1)), int(m.group(2))
        x = _resolve_no_year(d_, mo, today)
        if x:
            days.add(x)

    return sorted(d.isoformat() for d in days)


TRAFFIC_PARA_RE = re.compile(r"κυκλοφορ|κλειστ|διακοπ|ρυθμισ|τροποποι|λογω|οδο[υς ]|λεωφορ")


def from_article_html(html: str, today=None):
    """(days, area) extracted from an article BODY. Reads <p> paragraphs
    only — publication timestamps live in headers/<time> tags, so the
    pub-date trap that forced title-only extraction doesn't apply here —
    and only paragraphs that talk about traffic, so unrelated sidebar
    text can't inject dates."""
    from bs4 import BeautifulSoup
    from . import SOUP_PARSER
    soup = BeautifulSoup(html or "", SOUP_PARSER)
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    relevant = " ".join(t for t in paras
                        if len(t) > 30 and TRAFFIC_PARA_RE.search(norm_greek(t)))[:6000]
    if not relevant:
        return [], ""
    return extract_days(relevant, today), classify_area(relevant)


# ---------------------------------------------------------- severity
# Single-lane restrictions ("στη δεξιά λωρίδα", ΛΕΑ, μία λωρίδα) are
# real decisions but negligible disruptions — below the notification
# bar (product rule). A MAJOR signal anywhere overrides: full closures,
# events and multi-lane restrictions always survive, even when a lane
# is mentioned in passing.
LANE_ONLY_RE = re.compile(
    r"(?:δεξι|αριστερ|μεσαι)\w*\s+λωριδ"   # δεξιά/αριστερή/μεσαία λωρίδα
    r"|μιας?\s+λωριδ"                       # μία λωρίδα / μίας λωρίδας
    r"|λωριδ\w*\s+εκτακτης"                 # λωρίδα έκτακτης ανάγκης
    r"|\bλ\.?ε\.?α\.?\b")                   # ΛΕΑ
MAJOR_RE = re.compile(
    r"κλειστ|ολικ|πληρ(?:ης|ους)|πεζοδρομ|πορει|συγκεντρωσ|παρελασ|αγων"
    r"|(?:δυο|τριων|των)\s+λωριδ")


def is_lane_only(text: str) -> bool:
    """True when the ONLY restriction described is a single lane."""
    t = norm_greek(text or "")
    return bool(LANE_ONLY_RE.search(t)) and not MAJOR_RE.search(t)


DATEISH_RE = re.compile(r"\d{1,2}\s*/\s*\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|"
                        + "|".join(f"\\d{{1,2}}\\S*\\s+{s}" for s in _MONTHS))


def looks_dated(text: str) -> bool:
    """Does the text APPEAR to contain a date? Used as the parser's own
    smoke detector: looks_dated(t) and not extract_days(t) means the
    extractor met a phrasing it can't read — the exact silent failure
    that must be logged, never swallowed. NOTE: since the ghost-closure
    fix, a text whose only date is past-beyond-grace also parses to
    zero days by design; a few extra date_misses from stale articles
    are expected and harmless."""
    return bool(DATEISH_RE.search(norm_greek(text or "")))


# ------------------------------------------------------------- geography
# Keywords are accent-stripped lowercase (norm_greek). First match wins;
# Κέντρο is checked first so "Συγγρού" beats a passing mention of a suburb.
CENTER = [
    "συνταγμα", "ομονοια", "μοναστηρακ", "σταδιου", "πανεπιστημιου",
    "ακαδημιας", "ερμου", "πλακα", "ψυρρη", "εξαρχει", "κολωνακ",
    "βασιλισσης σοφιας", "βασ. σοφιας", "αμαλιας", "θησειο", "κεραμεικ",
    "μεταξουργειο", "γκαζι", "κυψελη", "πατησιων", "αλεξανδρας",
    "παγκρατι", "συγγρου", "δακτυλι", "κεντρο της αθηνας", "κεντρο αθηνας",
    "δημου αθηναιων", "ακροπολ", "ζαππει", "καλλιμαρμαρο", "λυκαβηττ",
]
NORTH = [
    "κηφισια", "μαρουσι", "αμαρουσιου", "χαλανδρι", "ψυχικο", "φιλοθεη",
    "πευκη", "λυκοβρυση", "μεταμορφωση", "νεα ιωνια", "ν. ιωνια",
    "γαλατσι", "φιλαδελφεια", "αχαρνες", "μενιδι", "κηφισιας", "οακα",
    "ηρακλειο αττικ", "νεο ηρακλειο", "καλυφτακη", "αττικη οδος",
    "εθνικη οδος αθηνων-λαμιας", "αθηνων-λαμιας", "βαρυμπομπη", "θρακομακεδονες",
]
WEST = [
    "περιστερι", "αιγαλεω", "χαιδαρι", "ιλιον", "πετρουπολη", "καματερο",
    "σκαραμαγκα", "ασπροπυργ", "ελευσιν", "κορυδαλλ", "νικαια", "κηφισου",
    "αθηνων-κορινθου", "λ. αθηνων", "λεωφ. αθηνων", "ιερα οδος",
    "αγιοι αναργυροι", "αγ. αναργυρ", "ανω λιοσια", "μεγαρ", "μανδρα",
]
SOUTH = [
    "καλλιθεα", "νεα σμυρνη", "ν. σμυρνη", "παλαιο φαληρο", "π. φαληρο",
    "φαληρ", "αλιμος", "γλυφαδα", "ελληνικο", "βουλιαγμεν", "ποσειδωνος",
    "πειραι", "μοσχατο", "ταυρος", "ηλιουπολη", "αργυρουπολη", "βουλα",
    "αγιος δημητριος", "αγ. δημητριος", "δαφνη", "λαυρι", "σουνι",
]
EAST = [
    "ζωγραφου", "καισαριαν", "βυρωνας", "χολαργ", "παπαγου",
    "αγια παρασκευη", "αγ. παρασκευη", "μεσογειων", "υμηττ", "γερακα",
    "παλλην", "σπατα", "ραφην", "πικερμι", "παιανια", "κορωπι",
    "μαραθων", "νεα μακρη", "αρτεμιδα", "λουτσα",
]
AREAS = [("Κέντρο", CENTER), ("Βόρεια", NORTH), ("Δυτικά", WEST),
         ("Νότια", SOUTH), ("Ανατολικά", EAST)]

SYNTAGMA = (37.9755, 23.7348)
CENTER_RADIUS_DEG = 0.018   # ~2 km: inside → Κέντρο
COORD_RE = re.compile(r"maps\?q=([\d.]+),([\d.]+)")


def _by_coords(lat: float, lon: float) -> str:
    dy = lat - SYNTAGMA[0]
    dx = (lon - SYNTAGMA[1]) * 0.79   # ~cos(38°): metres-fair x
    if (dx * dx + dy * dy) ** 0.5 <= CENTER_RADIUS_DEG:
        return "Κέντρο"
    if abs(dy) >= abs(dx):
        return "Βόρεια" if dy > 0 else "Νότια"
    return "Ανατολικά" if dx > 0 else "Δυτικά"


def classify_area(text: str, url: str = "") -> str:
    t = norm_greek(text or "")
    for name, keywords in AREAS:
        if any(k in t for k in keywords):
            return name
    m = COORD_RE.search(url or "")   # TomTom events carry coords
    if m:
        try:
            return _by_coords(float(m.group(1)), float(m.group(2)))
        except ValueError:
            pass
    return ""
