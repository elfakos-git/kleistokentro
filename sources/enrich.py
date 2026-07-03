"""Event enrichment: closure dates + geographic area.

CLOSURE DATES — extract_days(text)
  Parses the dates a closure is IN EFFECT from Greek text. Handles the
  three patterns observed in real Diavgeia subjects plus news style:
    * range:    "από 06/07/2026 έως 25/09/2026"     → every day expanded
    * day list: "στις 07, 08, 09 ... και 31-07-2026" → each day, that month
    * single:   "στις 05.07.2026"
    * no year:  "την Τρίτη 23/6" (news style)        → current year
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
RANGE_RE = re.compile(r"απο\s+" + _D +
                      r"\s*(?:εως|μεχρι)\s+(?:και\s+)?(?:τις\s+|την\s+)?" + _D)
DAYLIST_RE = re.compile(r"((?:\d{1,2}\s*,\s*)+\d{1,2})\s+και\s+"
                        r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})")
FULL_RE = re.compile(_D)
NOYEAR_RE = re.compile(r"(?<![\d/.\-])(\d{1,2})/(\d{1,2})(?![\d/.\-])")

MAX_RANGE_DAYS = 120     # a "range" longer than this is a parse error
PAST_DAYS, FUTURE_DAYS = 7, 200   # calendar window of interest


def _valid(d: int, m: int, y: int, today: date):
    try:
        dt = date(y, m, d)
    except ValueError:
        return None
    lo = today - timedelta(days=PAST_DAYS)
    hi = today + timedelta(days=FUTURE_DAYS)
    return dt if lo <= dt <= hi else None


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

    t = RANGE_RE.sub(take_range, t)
    t = DAYLIST_RE.sub(take_daylist, t)
    t = FULL_RE.sub(take_full, t)
    for m in NOYEAR_RE.finditer(t):          # "23/6" news style
        d_, mo = int(m.group(1)), int(m.group(2))
        x = _valid(d_, mo, today.year, today) or _valid(d_, mo, today.year + 1, today)
        if x:
            days.add(x)
    return sorted(d.isoformat() for d in days)


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
CENTER_RADIUS_DEG = 0.018        # ~2 km: inside → Κέντρο
COORD_RE = re.compile(r"maps\?q=([\d.]+),([\d.]+)")


def _by_coords(lat: float, lon: float) -> str:
    dy = lat - SYNTAGMA[0]
    dx = (lon - SYNTAGMA[1]) * 0.79          # ~cos(38°): metres-fair x
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
    m = COORD_RE.search(url or "")           # TomTom events carry coords
    if m:
        try:
            return _by_coords(float(m.group(1)), float(m.group(2)))
        except ValueError:
            pass
    return ""
