"""Diavgeia (Δι@ύγεια) — official traffic-regulation decisions.

WHY THIS SOURCE
  Every planned regulation (roadworks, events, announced demonstrations)
  becomes a formal decision by a police directorate, and Greek law
  requires publishing it on Diavgeia — usually BEFORE it takes effect
  and before any news article. This is the upstream source the news
  sites write from.

HOW IT WORKS
  We call the official OpenData search API (verified alive; base URL and
  organizationUid query syntax confirmed against the live service):

    GET https://diavgeia.gov.gr/luminapi/opendata/search.json
        ?q=<subject keywords> &org=<Hellenic Police org uid>
        &from_issue_date=<N days ago> &size=... &page=0

  ORG_UID 100054489 = Ministry of Citizen Protection (all police
  directorates publish under it; Διεύθυνση Τροχαίας Αττικής is a unit).

RELEVANCE POLICY — DELIBERATELY STRICTER THAN THE NEWS MODULES
  This API covers every police directorate in Greece, so unlike the news
  sources (which keep ambiguous titles), a decision is kept ONLY if its
  subject names central Athens / a known central road. Rationale: for a
  nationwide firehose, a missed obscure decision is cheaper than daily
  false alarms from other cities — and big Athens events are still
  caught by the news sources as a second net.

  Event identity = the ΑΔΑ (Diavgeia's own unique decision number):
  the perfect dedup key, assigned by the state, never reused.

DEBUG
  python -m sources.diavgeia          # show kept decisions
  python -m sources.diavgeia --all    # also show what was filtered out
                                      # (run this once to tune keywords)
"""
from datetime import datetime, timedelta, timezone

from . import HEADERS, TIMEOUT, Event, mentions_athens

import requests

SOURCE = "Διαύγεια (Τροχαία)"
SEARCH_URL = "https://diavgeia.gov.gr/luminapi/opendata/search.json"
DECISION_URL = "https://diavgeia.gov.gr/decision/view/{ada}"

ORG_UID = "100054489"          # Ministry of Citizen Protection (ΕΛ.ΑΣ)
QUERY = '"κυκλοφοριακές ρυθμίσεις" OR "διακοπή κυκλοφορίας"'
MAX_AGE_DAYS = 3               # matches the news modules' date guard
PAGE_SIZE = 100
MAX_EVENTS = 15                # this source can never flood a run


def _issue_dt(raw):
    """issueDate arrives as epoch milliseconds; tolerate ISO strings too.
    Returns an aware datetime, or None if unparseable."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
    try:  # e.g. "2026-07-02T09:30:00+03:00" or "2026-07-02"
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_central_athens(subject: str) -> bool:
    """STRICT: keep only if the subject names Athens or a central road."""
    return mentions_athens(subject)


def _search(from_date: str) -> dict:
    resp = requests.get(
        SEARCH_URL,
        params={
            "q": QUERY,
            "org": ORG_UID,
            "from_issue_date": from_date,   # YYYY-MM-DD
            "size": PAGE_SIZE,
            "page": 0,
        },
        headers={**HEADERS, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _to_event(dec: dict) -> Event | None:
    """Convert one API decision object to an Event, or None to skip.
    Defensive on every field: the schema was built from the official
    docs but not every corner could be live-verified at design time."""
    ada = (dec.get("ada") or "").strip()
    subject = " ".join((dec.get("subject") or "").split())
    if not ada or not subject:
        return None
    status = (dec.get("status") or "PUBLISHED").upper()
    if status != "PUBLISHED":            # revoked/pending decisions
        return None

    issued = _issue_dt(dec.get("issueDate"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    if issued is not None and issued < cutoff:
        return None                      # server-side filter backstop
    if not _is_central_athens(subject):
        return None

    details = "Επίσημη απόφαση Τροχαίας"
    if issued is not None:
        details += f" ({issued.astimezone().strftime('%d/%m/%Y')})"
    return Event(
        id=ada,                          # ΑΔΑ: state-issued, unique
        source=SOURCE,
        title=subject[:300],
        url=DECISION_URL.format(ada=ada),
        details=details,
    )


def fetch() -> list[Event]:
    from_date = (datetime.now(timezone.utc)
                 - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    data = _search(from_date)
    if "decisions" not in data or not isinstance(data["decisions"], list):
        # Missing key must FAIL LOUDLY, not silently report zero events —
        # a silent [] here would look healthy on the dashboard forever.
        raise RuntimeError("diavgeia: unexpected response shape "
                           "(no 'decisions' list) — API changed?")
    decisions = data["decisions"]
    events = []
    for dec in decisions:
        if not isinstance(dec, dict):
            continue
        ev = _to_event(dec)
        if ev:
            events.append(ev)
        if len(events) >= MAX_EVENTS:
            break
    return events


if __name__ == "__main__":  # manual check: python -m sources.diavgeia
    import sys
    show_all = "--all" in sys.argv
    from_date = (datetime.now(timezone.utc)
                 - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    data = _search(from_date)
    decisions = data.get("decisions") or []
    print(f"API returned {len(decisions)} decision(s) since {from_date}\n")
    for dec in decisions:
        ev = _to_event(dec) if isinstance(dec, dict) else None
        if ev:
            print(f"KEEP  {ev.title}\n      {ev.url}\n")
        elif show_all and isinstance(dec, dict):
            print(f"skip  {' '.join((dec.get('subject') or '?').split())[:110]}")
