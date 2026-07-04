"""kathimerini.gr — traffic-regulations tag (WordPress).

IMPORTANT: kathimerini.gr runs bot protection and blocked automated
fetching during design. Strategy:
  1. Try the WordPress per-tag RSS feed first (feeds usually bypass both
     bot protection and the paywall).
  2. If the feed 404s or is blocked, fall back to the HTML tag page.
  3. If both fail, this module raises — monitor.py isolates the failure,
     the other sources still run, and you get an alert only after
     several consecutive failures.

If it fails consistently for a week: remove "kathimerini" from SOURCES
in monitor.py (one line) and rely on iefimerida, which republishes the
same Traffic Police announcements.

Debug:  python -m sources.kathimerini
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

import re

from . import Event, SOUP_PARSER, Tally, canonical_url, get

last_tally = Tally()
from .iefimerida import _is_relevant  # same keep-ambiguous policy

SOURCE = "kathimerini"
# Real articles look like kathimerini.gr/<section>/<numeric id>/<slug>.
# Everything else on the tag page (subscription buttons, newsletters,
# promos) is site chrome — production showed 4 of 10 scraped items were
# junk before this filter existed.
ARTICLE_RE = re.compile(r"kathimerini\.gr/[a-z-]+/\d{6,}/")
FEED_URL = "https://www.kathimerini.gr/tag/kykloforiakes-rythmiseis/feed/"
PAGE_URL = "https://www.kathimerini.gr/tag/kykloforiakes-rythmiseis/"
MAX_AGE_DAYS = 3

# Real kathimerini articles have a long numeric ID in the path
# (e.g. /society/564312118/...). Promo/nav links (subscriptions,
# newsletters, campaigns) don't — production showed them leaking
# through the old filter and polluting the dashboard.
ARTICLE_RE = re.compile(r"/\d{6,}/")


def _from_rss() -> list[Event]:
    root = ET.fromstring(get(FEED_URL).content)
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    events = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = item.findtext("pubDate")
        if not title or not link:
            continue
        link = canonical_url(link)
        if pub_raw:
            try:
                if parsedate_to_datetime(pub_raw) < cutoff:
                    last_tally.hit("παλιό άρθρο")
                    continue
            except (TypeError, ValueError):
                pass  # unparseable date → keep, dedup protects us anyway
        if _is_relevant(f"{title} {link}"):
            events.append(Event(id=link, source=SOURCE, title=title, url=link))
        else:
            last_tally.hit("άλλη περιοχή")
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
            href = "https://www.kathimerini.gr" + href
        href = canonical_url(href)
        if not ARTICLE_RE.search(href) or href in seen:
            continue
        if _is_relevant(title):
            seen.add(href)
            events.append(Event(id=href, source=SOURCE, title=title, url=href))
    # No date on WP tag cards reliably → rely on dedup; cap to newest few
    # so a first fetch can never flood (first run seeds silently anyway).
    return events[:10]


def fetch() -> list[Event]:
    global last_tally
    last_tally = Tally()
    try:
        return _from_rss()
    except Exception:
        return _from_html()


if __name__ == "__main__":  # manual check: python -m sources.kathimerini
    for e in fetch():
        print(f"- {e.title}\n  {e.url}\n")
