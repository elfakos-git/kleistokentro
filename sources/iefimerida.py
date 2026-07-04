"""iefimerida.gr — traffic-regulations tag page (Drupal, static HTML).

Detection logic:
  * Each article card on the tag page has a title, an absolute URL and a
    publication timestamp (DD/MM/YYYY HH:MM).
  * Identity = article URL. Dedup happens centrally in monitor.py.
  * Date guard: ignore anything older than MAX_AGE_DAYS, so a site
    redesign or parser bug can never flood you with old articles.
  * Relevance guard: the tag covers all of Greece. We skip an article
    only when it clearly names another region AND contains no Athens
    signal. When in doubt we keep it (a rare false positive beats a
    missed closure of Συγγρού).

Debug:  python -m sources.iefimerida
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re

from bs4 import BeautifulSoup

from . import Event, canonical_url, get, mentions_athens, mentions_other_region

SOURCE = "iefimerida"
URL = "https://www.iefimerida.gr/tag/kykloforiakes-rythmiseis"
MAX_AGE_DAYS = 3
ATHENS_TZ = ZoneInfo("Europe/Athens")

DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?")


def _is_relevant(title: str) -> bool:
    """Keep unless it clearly names another region with no Athens signal
    (ambiguous → keep: a rare false positive beats a missed closure)."""
    return mentions_athens(title) or not mentions_other_region(title)


def _parse_date(text: str):
    m = DATE_RE.search(text)
    if not m:
        return None
    d, mo, y, h, mi = m.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0),
                        tzinfo=ATHENS_TZ)
    except ValueError:   # regex admits impossible dates like 99/99/2026;
        return None      # one junk string must not kill the whole source


def fetch() -> list[Event]:
    global last_tally
    last_tally = Tally()
    soup = BeautifulSoup(get(URL).text, SOUP_PARSER)
    cutoff = datetime.now(ATHENS_TZ) - timedelta(days=MAX_AGE_DAYS)
    events, seen_urls = [], set()

    # Article links on the tag page point into /node/... or article paths.
    # We look at every link whose surrounding block contains a date.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)
        if not title or len(title) < 25:      # skip nav/menu links
            continue
        if href.startswith("/"):
            href = "https://www.iefimerida.gr" + href
        href = canonical_url(href)
        if "iefimerida.gr" not in href or href in seen_urls:
            continue
        if "/tag/" in href or "/category/" in href:
            continue

        # Find the publication date near the link (same card/container).
        container = a.find_parent(["article", "div", "li"]) or a
        pub = _parse_date(container.get_text(" ", strip=True))
        if pub is None or pub < cutoff:
            last_tally.hit("χωρίς/παλιά ημερομηνία")
            continue
        if not _is_relevant(f"{title} {href}"):   # regions often hide in the URL
            last_tally.hit("άλλη περιοχή")
            continue

        seen_urls.add(href)
        events.append(Event(id=href, source=SOURCE, title=title, url=href))

    return events


if __name__ == "__main__":  # manual check: python -m sources.iefimerida
    for e in fetch():
        print(f"- {e.title}\n  {e.url}\n")
