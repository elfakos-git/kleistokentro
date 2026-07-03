"""astynomia.gr — Attica traffic bulletin (live table, not an event log).

Design decisions (see README):
  * We notify on the ΕΠΙΣΗΜΑΝΣΕΙΣ (remarks) column — closures,
    demonstrations, incidents. These are genuine disruptions that
    persist for hours, so a 4-hour poll catches them meaningfully.
  * Congestion level (Ομαλή / Αυξημένη / Πολύ Αυξημένη) is included as
    CONTEXT inside a remark notification, never as a trigger on its own:
    congestion is transient state and would be stale at this cadence.
  * STALENESS GUARD: the page carries a "Τελευταία Ενημέρωση" timestamp
    and has been observed to go a week without updates. If the bulletin
    is older than MAX_STALENESS_HOURS we return nothing — old data is
    worse than no data.
  * Event identity = hash(road + remark text). The same remark seen on
    consecutive runs produces the same ID, so you're notified once.
    If the remark text is edited, that's a new event — acceptable.

VERIFY BEFORE FIRST USE: the exact HTML of the status markers could not
be confirmed at design time. Run `python -m sources.astynomia` locally;
if roads/remarks print correctly you're done. If not, adjust the two
marked selectors below (instructions in README, section "If a parser
breaks").
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re

from bs4 import BeautifulSoup

from . import Event, get, stable_id

SOURCE = "Τροχαία (astynomia.gr)"
URL = "https://www.astynomia.gr/kykloforia-stous-dromous/deltio-kykloforias-attiki/"
MAX_STALENESS_HOURS = 12
ATHENS_TZ = ZoneInfo("Europe/Athens")

LEVELS = ["Πολύ Αυξημένη", "Αυξημένη", "Ομαλή"]  # order matters (substring!)
UPDATE_RE = re.compile(
    r"Τελευταία\s+Ενημέρωση[:\s]*"
    r"(\d{2})/(\d{2})/(\d{4})\s*[–—-]\s*(\d{1,2})[:.](\d{2})"
)


def _bulletin_time(text: str):
    m = UPDATE_RE.search(text)
    if not m:
        return None
    d, mo, y, h, mi = (int(g) for g in m.groups())
    return datetime(y, mo, d, h, mi, tzinfo=ATHENS_TZ)


def _row_level(row) -> str:
    """Detect the congestion level of a table row.  <-- SELECTOR 1
    Tries, in order: visible text, class names, checked inputs."""
    text = row.get_text(" ", strip=True)
    for level in LEVELS:
        if level in text:
            return level
    classes = " ".join(
        c for tag in row.find_all(True) for c in (tag.get("class") or [])
    ).lower()
    if "red" in classes or "poli" in classes or "high" in classes:
        return "Πολύ Αυξημένη"
    if "orange" in classes or "yellow" in classes or "medium" in classes:
        return "Αυξημένη"
    checked = row.find("input", checked=True)
    if checked:
        val = (checked.get("value") or checked.get("id") or "").lower()
        if "poli" in val or "3" in val:
            return "Πολύ Αυξημένη"
    return ""


def fetch() -> list[Event]:
    soup = BeautifulSoup(get(URL, extra_headers={
        "Accept": ("text/html,application/xhtml+xml,application/xml;"
                   "q=0.9,image/avif,image/webp,*/*;q=0.8"),
        "Referer": "https://www.astynomia.gr/",
    }).text, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    updated = _bulletin_time(page_text)
    if updated is None:
        # Timestamp gone → page layout changed. Fail loudly so the
        # consecutive-failure alert fires instead of silently rotting.
        raise RuntimeError("astynomia: 'Τελευταία Ενημέρωση' not found — layout changed?")
    if datetime.now(ATHENS_TZ) - updated > timedelta(hours=MAX_STALENESS_HOURS):
        return []  # stale bulletin: valid situation, report nothing

    events = []
    for row in soup.find_all("tr"):                       # <-- SELECTOR 2
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        road = cells[0].get_text(" ", strip=True)
        remark = cells[-1].get_text(" ", strip=True)
        # Skip header rows and rows without a meaningful remark.
        if not road or road.upper().startswith(("ΟΔΙΚ", "ΑΞΟΝ", "ΔΡΟΜ")):
            continue
        if not remark or remark in LEVELS or len(remark) < 10:
            continue

        level = _row_level(row)
        details = remark if not level else f"{remark}\nΚίνηση αυτή τη στιγμή: {level}"
        events.append(Event(
            id=stable_id(road, remark),
            source=SOURCE,
            title=road,
            url=URL,
            details=details,
        ))
    return events


if __name__ == "__main__":  # manual check: python -m sources.astynomia
    evs = fetch()
    if not evs:
        print("No active remarks (or bulletin is stale). "
              "Check the page in a browser to confirm parsing is correct.")
    for e in evs:
        print(f"- {e.title}\n  {e.details}\n")
