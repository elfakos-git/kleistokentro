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

from . import Event, Tally, get, mentions_athens, norm_greek

last_tally = Tally()

SOURCE = "Διαύγεια (Τροχαία)"
SEARCH_URL = "https://diavgeia.gov.gr/luminapi/opendata/search.json"
DECISION_URL = "https://diavgeia.gov.gr/decision/view/{ada}"

ORG_UID = "100054489"          # Ministry of Citizen Protection (ΕΛ.ΑΣ)

# LESSON FROM PRODUCTION: the API's `q` parameter silently ignored our
# quoted "phrase OR phrase" syntax and returned EVERYTHING from the org
# (fire-extinguisher procurement included). So: treat `q` only as a
# recall-improving prefilter (two simple one-word queries, merged), and
# enforce precision CLIENT-SIDE in _to_event(), which is code we control.
QUERIES = ["κυκλοφοριακές", "κυκλοφορίας"]
TRAFFIC_STEM = "κυκλοφορ"      # matches both words above after norm_greek
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


def _is_relevant(subject: str) -> bool:
    """STRICT, both required: the subject must actually be about traffic
    (κυκλοφορ- stem) AND name Athens or a central road. Server-side
    filtering proved unreliable; this is the filter that counts."""
    return TRAFFIC_STEM in norm_greek(subject) and mentions_athens(subject)


def _search(query: str, from_date: str) -> dict:
    resp = get(SEARCH_URL, params={
        "q": query,
        "org": ORG_UID,
        "from_issue_date": from_date,   # YYYY-MM-DD
        "size": PAGE_SIZE,
        "page": 0,
    }, extra_headers={"Accept": "application/json"})
    return resp.json()


def _to_event(dec: dict, tally: Tally | None = None) -> Event | None:
    """Convert one API decision object to an Event, or None to skip.
    Defensive on every field: the schema was built from the official
    docs but not every corner could be live-verified at design time."""
    tally = tally if tally is not None else Tally()
    ada = (dec.get("ada") or "").strip()
    subject = " ".join((dec.get("subject") or "").split())
    if not ada or not subject:
        tally.hit("χωρίς ΑΔΑ/θέμα")
        return None
    status = (dec.get("status") or "PUBLISHED").upper()
    if status != "PUBLISHED":            # revoked/pending decisions
        tally.hit("μη δημοσιευμένη")
        return None

    issued = _issue_dt(dec.get("issueDate"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    if issued is not None and issued < cutoff:
        tally.hit("εκτός χρονικού παραθύρου")
        return None
    if not _is_relevant(subject):
        tally.hit("εκτός θέματος/Αθήνας")
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
    global last_tally
    last_tally = Tally()
    from_date = (datetime.now(timezone.utc)
                 - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    events, seen_ada = [], set()
    for query in QUERIES:               # two nets, merged and deduped
        data = _search(query, from_date)
        if "decisions" not in data or not isinstance(data["decisions"], list):
            # Missing key must FAIL LOUDLY, not silently report zero —
            # a silent [] would look healthy on the dashboard forever.
            raise RuntimeError("diavgeia: unexpected response shape "
                               "(no 'decisions' list) — API changed?")
        for dec in data["decisions"]:
            if not isinstance(dec, dict):
                continue
            ada = (dec.get("ada") or "").strip()
            if ada and ada in seen_ada:
                continue                 # both nets saw it: count ONCE
            if ada:
                seen_ada.add(ada)        # kept or rejected — processed
            ev = _to_event(dec, last_tally)
            if ev:
                events.append(ev)
            if len(events) >= MAX_EVENTS:
                return events
    return events


if __name__ == "__main__":  # manual check: python -m sources.diavgeia
    import sys
    show_all = "--all" in sys.argv
    from_date = (datetime.now(timezone.utc)
                 - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    for query in QUERIES:
        data = _search(query, from_date)
        decisions = data.get("decisions") or []
        print(f"q={query!r}: {len(decisions)} decision(s) since {from_date}")
        for dec in decisions:
            ev = _to_event(dec) if isinstance(dec, dict) else None
            if ev:
                print(f"  KEEP  {ev.title[:100]}")
            elif show_all and isinstance(dec, dict):
                print(f"  skip  {' '.join((dec.get('subject') or '?').split())[:100]}")
        print()
