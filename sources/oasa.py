"""ΟΑΣΑ (oasa.gr/blog) — bus-route diversions as a closure sensor.

WHY THIS SOURCE
  Buses get diverted precisely when streets close, and OASA publishes
  every diversion WITH its cause and usually the street and dates in
  the title itself: "τροποποίηση ... λόγω εργασιών επί της οδού
  Αδριανού του Δήμου Κηφισιάς, στις 15/04/2026". Our existing date and
  area extractors work on these directly, and BODY_ENRICH fills in
  whatever the title omits (bodies list the exact street-by-street
  detours).

RELEVANCE POLICY
  OASA's blog also carries pure operations noise (telematics
  maintenance, holiday timetables, "άρση τροποποίησης" = restoration).
  We keep a post only when it signals a road-level disruption:
  either "κυκλοφοριακές ρυθμίσεις" / διακοπή / κλειστ-, or a
  "λόγω <cause>" clause with a disruption cause (works, event, race,
  procession, strike, weather). Everything else is tallied and dropped.

  WordPress site → RSS feed first (same playbook that carried
  kathimerini through its bot protection), HTML listing as fallback.
  Verify once: python -m sources.oasa

Identity = post URL. BODY_ENRICH: yes.
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from . import Event, SOUP_PARSER, Tally, get, norm_greek

SOURCE = "ΟΑΣΑ"
FEED_URL = "https://www.oasa.gr/blog/feed/"
PAGE_URL = "https://www.oasa.gr/blog/"
MAX_AGE_DAYS = 3
BODY_ENRICH = True

last_tally = Tally()

# Road-level disruption signals (normalized, accentless stems).
DIRECT = ("κυκλοφοριακ", "διακοπ", "κλειστ")
CAUSES = ("εργασι", "εκδηλωσ", "εορτ", "αγων", "πορει", "διεξαγωγ",
          "απεργ", "κακοκαιρ", "παρελασ", "επιταφι")
# Operations noise, never road disruptions.
SKIP = ("τηλεματ", "προγραμμα δρομολογ", "αρση τροποποιησ",
        "αρση της τροποποιησ", "εκτελειται κανονικα")


def _is_relevant(title: str) -> bool:
    t = norm_greek(title)
    if any(s in t for s in SKIP):
        return False
    if any(s in t for s in DIRECT):
        return True
    return "λογω" in t and any(c in t for c in CAUSES)


def _tag_relevant(title: str) -> bool:
    ok = _is_relevant(title)
    if not ok:
        last_tally.hit("λειτουργικό/χωρίς οδικό αντίκτυπο")
    return ok


def _from_rss() -> list[Event]:
    root = ET.fromstring(get(FEED_URL).content)
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    events = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        pub_raw = item.findtext("pubDate")
        if pub_raw:
            try:
                if parsedate_to_datetime(pub_raw) < cutoff:
                    last_tally.hit("παλιά ανακοίνωση")
                    continue
            except (TypeError, ValueError):
                pass  # unparseable date → keep; dedup protects us
        if _tag_relevant(title):
            events.append(Event(id=link, source=SOURCE, title=title, url=link))
    return events


def _from_html() -> list[Event]:
    soup = BeautifulSoup(get(PAGE_URL).text, SOUP_PARSER)
    events, seen = [], set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        href = a["href"]
        if not title or len(title) < 25:
            continue
        if href.startswith("/"):
            href = "https://www.oasa.gr" + href
        if "oasa.gr/blog/" not in href or href.rstrip("/") == PAGE_URL.rstrip("/"):
            continue
        if href in seen:
            continue
        seen.add(href)
        if _tag_relevant(title):
            events.append(Event(id=href, source=SOURCE, title=title, url=href))
    # Listing pages carry no reliable dates → rely on dedup; cap so a
    # first fetch can never flood (per-source seeding is silent anyway).
    return events[:12]


def fetch() -> list[Event]:
    global last_tally
    last_tally = Tally()
    try:
        return _from_rss()
    except Exception:
        return _from_html()


if __name__ == "__main__":  # manual check: python -m sources.oasa
    for e in fetch():
        print(f"- {e.title}\n  {e.url}\n")
    print("dropped:", dict(last_tally))
