"""iCalendar feed of upcoming closures → docs/closures.ics.

Anyone can subscribe from Google/Apple/Outlook Calendar with the raw
Pages URL (https://<user>.github.io/<repo>/closures.ics); calendar apps
re-poll it periodically, so the feed self-updates as the monitor runs.

DESIGN
  * One all-day VEVENT per CONSECUTIVE run of days. A decision listing
    16 scattered working days becomes 16 one-day entries — exactly how
    it should look on a calendar; a solid 6/7–25/9 range becomes one.
  * DETERMINISTIC OUTPUT: UIDs are hashes of (event id + run start) and
    DTSTAMP is derived from the run start, so an unchanged registry
    produces a byte-identical file — calendar clients see stable
    events, and the git history stays quiet.
  * RFC 5545 details that matter: CRLF line endings, TEXT escaping
    (backslash, semicolon, comma, newline), and 75-OCTET line folding —
    Greek is 2 bytes/char in UTF-8, so folding counts bytes and splits
    only on character boundaries.
  * Failure-tolerant by contract: monitor.py wraps the call, a feed bug
    must never break monitoring.

TESTS  python tests/test_ics.py
"""
import hashlib
import re
from datetime import date, timedelta

from sources.humanize import _runs   # same day-grouping as the summaries

CALNAME = "Κλειστό Κέντρο — Αθήνα"
PRODID = "-//kleistokentro//Athens Traffic Monitor//EL"
MAX_LINE_OCTETS = 75
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _escape(text: str) -> str:
    return (str(text or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> list[str]:
    """RFC 5545 §3.1: physical lines ≤75 octets; continuations start
    with a single space. Split on UTF-8 character boundaries."""
    out, cur, budget = [], "", MAX_LINE_OCTETS
    for ch in line:
        w = len(ch.encode("utf-8"))
        if w > budget:
            out.append(cur)
            cur, budget = " ", MAX_LINE_OCTETS - 1   # continuation space
        cur += ch
        budget -= w
    out.append(cur)
    return out


def _ymd(iso: str) -> str:
    return iso.replace("-", "")


def _event(c: dict, start: str, end: str) -> list[str]:
    cid = str(c.get("id") or c.get("url") or c.get("title") or "?")
    uid = hashlib.sha1(f"{cid}|{start}".encode("utf-8")).hexdigest()[:20]
    day_after = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    summary = c.get("plain") or (c.get("title") or "")[:140]
    desc_bits = [c.get("title") or "", f"Πηγή: {c.get('source', '')}",
                 c.get("url") or ""]
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@kleistokentro",
        f"DTSTAMP:{_ymd(start)}T000000Z",       # deterministic (see docstring)
        f"DTSTART;VALUE=DATE:{_ymd(start)}",
        f"DTEND;VALUE=DATE:{_ymd(day_after)}",  # DTEND is EXCLUSIVE
        f"SUMMARY:{_escape('🚧 ' + summary)}",
        f"DESCRIPTION:{_escape(chr(10).join(b for b in desc_bits if b))}",
        "TRANSP:TRANSPARENT",                    # closures never block free/busy
    ]
    if c.get("area"):
        lines.append(f"LOCATION:{_escape(c['area'] + ', Αθήνα')}")
    if c.get("url"):
        lines.append(f"URL:{_escape(c['url'])}")
    lines.append("END:VEVENT")
    return lines


def build(closures: list[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(CALNAME)}",
        "X-WR-TIMEZONE:Europe/Athens",
        "REFRESH-INTERVAL;VALUE=DURATION:PT4H",
        "X-PUBLISHED-TTL:PT4H",
    ]
    events = []
    for c in closures or []:
        if str(c.get("source", "")).startswith("TomTom"):
            continue   # realtime blips are not PLANNED closures, and
                       # their ever-new ids would churn the calendar
                       # every 30 minutes, defeating determinism
        days = [d for d in (c.get("days") or [])
                if isinstance(d, str) and _ISO_DAY.match(d)]
        if not days:
            continue
        for start, end in _runs(days):
            events.append((start, _event(c, start, end)))
    for _, ev in sorted(events, key=lambda x: x[0]):   # stable order
        lines.extend(ev)
    lines.append("END:VCALENDAR")

    folded = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"


def write_ics(path, closures: list[dict]) -> None:
    path.write_text(build(closures), encoding="utf-8", newline="")
