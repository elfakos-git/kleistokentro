"""astynomia.gr — Attica traffic bulletin (live table, not an event log).

POLICY (v2 — retuned on production data)
  The first live weeks proved the ΕΠΙΣΗΜΑΝΣΕΙΣ column is mostly
  congestion-extent text ("ΑΠΟ ΣΚΑΡΑΜΑΓΚΑ ΕΩΣ ΔΙΥΛΙΣΤΗΡΙΑ"), i.e.
  traffic state, not disruption events. The bulletin now feeds two
  DISTINCT kinds of event, everything else is ignored:

  1. GENUINE DISRUPTIONS — a remark containing a disruption keyword
     (closure, demonstration, accident, works, diversion...). Always
     kept, whatever the congestion level.
     Identity: hash(road + remark) → notified once per remark text.

  2. CONGESTION ANOMALIES — a row at "Πολύ Αυξημένη" OUTSIDE typical
     rush windows. Rush-hour heavy traffic on the big arteries is
     weather, not news; the SAME level at 14:00 or on a Sunday means
     something is actually wrong. This is the "verify it's not just
     heavy traffic" test: TIME explains ordinary congestion, so
     congestion that time can't explain is the signal.
       Rush windows (Athens time): weekdays 07:00–10:30 & 16:30–20:30.
       Weekends have no expected rush → any Πολύ Αυξημένη qualifies.
     Identity: hash(road + level + bulletin date) → at most one
     notification per road per day, and it can fire again tomorrow.

  Rows at Ομαλή/Αυξημένη without a disruption keyword: ignored.

  STALENESS GUARD unchanged: bulletins older than MAX_STALENESS_HOURS
  are treated as no data.

VERIFY LOCALLY (the level markers are graphics; detection is best-
effort across text, classes, images and inputs — SELECTOR 1 below):
  python -m sources.astynomia          # decisions per row, with reasons
If levels print as '?' on a fresh bulletin, open the page in Chrome,
inspect a row, and extend _row_level (README: "If a parser breaks").
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re

from bs4 import BeautifulSoup

from . import Event, SOUP_PARSER, Tally, get, norm_greek, stable_id

last_tally = Tally()

SOURCE = "Τροχαία (astynomia.gr)"
URL = "https://www.astynomia.gr/kykloforia-stous-dromous/deltio-kykloforias-attiki/"
MAX_STALENESS_HOURS = 12
ASSUME_TODAY = True   # realtime source: no date in text = happening now
ATHENS_TZ = ZoneInfo("Europe/Athens")

LEVELS = ["Πολύ Αυξημένη", "Αυξημένη", "Ομαλή"]  # order matters (substring!)

# Words that make a remark a real disruption event (stems, accentless).
DISRUPTION_RE = re.compile(
    "|".join(["κλειστ", "διακοπ", "πορει", "συγκεντρωσ", "απεργ",
              "εκδηλωσ", "εργασι", "τροχαι", "ατυχημ", "παρελασ",
              "αγων", "εκτροπ", "απαγορευσ", "καθυστερησ.*λογω"]))

# Pure congestion-extent remarks — state, never a standalone event.
EXTENT_RE = re.compile(r"^απ[οό]\s+\S.*\s+[εέ]ως\s+\S.*$")

# Weekday rush windows, Athens time, as (start_h, start_m, end_h, end_m).
RUSH_WINDOWS = [(7, 0, 10, 30), (16, 30, 20, 30)]

UPDATE_RE = re.compile(
    r"Τελευταία\s+Ενημέρωση[:\s]*"
    r"(\d{2})/(\d{2})/(\d{4})\s*[–—-]\s*(\d{1,2})[:.](\d{2})"
)


def _athens_now() -> datetime:
    """Patchable in tests."""
    return datetime.now(ATHENS_TZ)


def _is_rush(now: datetime) -> bool:
    if now.weekday() >= 5:                    # weekend: no expected rush
        return False
    minutes = now.hour * 60 + now.minute
    return any(sh * 60 + sm <= minutes <= eh * 60 + em
               for sh, sm, eh, em in RUSH_WINDOWS)


def _bulletin_time(text: str):
    m = UPDATE_RE.search(text)
    if not m:
        return None
    d, mo, y, h, mi = (int(g) for g in m.groups())
    return datetime(y, mo, d, h, mi, tzinfo=ATHENS_TZ)


def _row_level(row) -> str:
    """Detect the congestion level of a table row.  <-- SELECTOR 1
    Tries: visible text, class names, image src/alt/title, checked
    inputs, inline style colors."""
    text = row.get_text(" ", strip=True)
    for level in LEVELS:
        if level in text:
            return level
    hints = []
    for tag in row.find_all(True):
        hints.extend(tag.get("class") or [])
        for attr in ("src", "alt", "title", "value", "id", "style"):
            v = tag.get(attr)
            if v:
                hints.append(str(v))
    blob = " ".join(hints).lower()
    if any(k in blob for k in ("red", "kokkino", "poli", "high", "f00",
                               "ff0000", "level3", "level-3")):
        return "Πολύ Αυξημένη"
    if any(k in blob for k in ("orange", "yellow", "portokali", "medium",
                               "level2", "level-2")):
        return "Αυξημένη"
    checked = row.find("input", checked=True)
    if checked and "3" in str(checked.get("value") or checked.get("id") or ""):
        return "Πολύ Αυξημένη"
    return ""


def _classify(road: str, remark: str, level: str, now: datetime):
    """(kind, event|None) for one row. kind is one of
    'disruption' / 'anomaly' / 'skip:<reason>' — the debug runner
    prints it so tuning needs no code-reading."""
    norm_remark = norm_greek(remark)
    meaningful = len(remark) >= 6 and remark not in LEVELS
    if meaningful and DISRUPTION_RE.search(norm_remark) \
            and not EXTENT_RE.match(norm_remark):
        details = remark
        if level:
            details += f"\nΚίνηση αυτή τη στιγμή: {level}"
        return "disruption", Event(id=stable_id(road, remark),
                                   source=SOURCE, title=road,
                                   url=URL, details=details)
    if level == "Πολύ Αυξημένη":
        if _is_rush(now):
            return "skip: rush-hour congestion (expected)", None
        details = "Ασυνήθιστα βεβαρυμένη κίνηση εκτός ωρών αιχμής"
        if meaningful:
            details += f"\n{remark}"
        return "anomaly", Event(
            id=stable_id(road, "πολύ αυξημένη", now.date().isoformat()),
            source=SOURCE, title=road, url=URL, details=details)
    if level:
        return f"skip: level '{level}'", None
    return "skip: no level detected, no disruption keyword", None


def _rows(soup):
    for row in soup.find_all("tr"):                   # <-- SELECTOR 2
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        road = cells[0].get_text(" ", strip=True)
        remark = cells[-1].get_text(" ", strip=True)
        if not road or road.upper().startswith(("ΟΔΙΚ", "ΑΞΟΝ", "ΔΡΟΜ")):
            continue
        yield road, remark, _row_level(row)


def fetch() -> list[Event]:
    soup = BeautifulSoup(get(URL, extra_headers={
        "Accept": ("text/html,application/xhtml+xml,application/xml;"
                   "q=0.9,image/avif,image/webp,*/*;q=0.8"),
        "Referer": "https://www.astynomia.gr/",
    }).text, SOUP_PARSER)
    page_text = soup.get_text(" ", strip=True)

    updated = _bulletin_time(page_text)
    if updated is None:
        raise RuntimeError("astynomia: 'Τελευταία Ενημέρωση' not found — layout changed?")
    now = _athens_now()
    if now - updated > timedelta(hours=MAX_STALENESS_HOURS):
        return []  # stale bulletin: valid situation, report nothing

    global last_tally
    last_tally = Tally()
    events, rows_seen, levels_seen = [], 0, 0
    for road, remark, level in _rows(soup):
        rows_seen += 1
        levels_seen += bool(level)
        kind, ev = _classify(road, remark, level, now)
        if ev:
            events.append(ev)
        else:
            last_tally.hit(kind.replace("skip: ", ""))
    if rows_seen >= 5 and levels_seen == 0:
        # Fresh bulletin, plenty of rows, zero detected levels: the
        # anomaly layer is blind. Not fatal (keyword layer still works)
        # but must be visible in the logs, not silent.
        print("astynomia WARNING: no congestion levels detected on a "
              "fresh bulletin — check SELECTOR 1 (_row_level)")
    return events


if __name__ == "__main__":  # manual check: python -m sources.astynomia
    soup = BeautifulSoup(get(URL, extra_headers={
        "Referer": "https://www.astynomia.gr/"}).text, SOUP_PARSER)
    updated = _bulletin_time(soup.get_text(" ", strip=True))
    now = _athens_now()
    print(f"Bulletin: {updated}   now: {now:%Y-%m-%d %H:%M}   "
          f"rush-hour: {_is_rush(now)}\n")
    for road, remark, level in _rows(soup):
        kind, _ = _classify(road, remark, level, now)
        print(f"[{kind:<45}] {road[:38]:<40} lvl={level or '?':<14} "
              f"{remark[:45]}")
