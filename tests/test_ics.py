"""Offline tests for ics_feed.py — RFC 5545 essentials.
Run with:  python tests/test_ics.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ics_feed import build, write_ics

CLOSURES = [
    {"id": "935Ζ46ΜΤΛΒ-1ΕΦ", "source": "Διαύγεια (Τροχαία)",
     "title": "Ρυθμίσεις, Δήμων Ζωγράφου; και Παπάγου",   # , and ; need escaping
     "plain": "Κυκλοφοριακές ρυθμίσεις — Δήμων Ζωγράφου και Παπάγου-Χολαργού "
              "· 6/7 – 8/7, 19:00–07:00",
     "url": "https://diavgeia.gov.gr/decision/view/935Ζ46ΜΤΛΒ-1ΕΦ",
     "area": "Ανατολικά",
     "days": ["2026-07-06", "2026-07-07", "2026-07-08"]},        # ONE run
    {"id": "63ΠΤ46ΜΤΛΒ-ΔΝ1", "source": "Διαύγεια (Τροχαία)",
     "title": "Πανεπιστημίου, σκόρπιες ημέρες",
     "plain": "", "url": "https://diavgeia.gov.gr/decision/view/63ΠΤ46ΜΤΛΒ-ΔΝ1",
     "area": "Κέντρο",
     "days": ["2026-07-07", "2026-07-08", "2026-07-14", "2026-07-15"]},  # TWO runs
    {"id": "no-days", "source": "x", "title": "χωρίς ημέρες",
     "url": "http://x", "area": "", "days": []},                 # skipped
    {"id": "TTI-abc123", "source": "TomTom (realtime)",          # skipped:
     "title": "Σταδίου → Πλ. Συντάγματος",                       # realtime blips
     "url": "https://www.google.com/maps?q=37.9,23.7",           # are not PLANNED
     "area": "Κέντρο", "days": ["2026-07-06"]},                  # closures
]


def run():
    ics = build(CLOSURES)
    lines = ics.split("\r\n")

    # Envelope + structure
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR"
    assert ics.endswith("\r\n") and "\n" not in ics.replace("\r\n", "")
    assert ics.count("BEGIN:VEVENT") == 3 == ics.count("END:VEVENT"), \
        "1 run + 2 runs = 3 VEVENTs; dayless + TomTom closures contribute none"
    assert "TTI-abc123" not in ics and "Συντάγματος" not in ics, \
        "realtime (TomTom) entries must never enter the planned-closures calendar"

    # All-day semantics: DTEND is EXCLUSIVE (run 6–8/7 ends on the 9th)
    assert "DTSTART;VALUE=DATE:20260706" in ics
    assert "DTEND;VALUE=DATE:20260709" in ics
    # Scattered days split into runs 7–8 and 14–15
    assert "DTSTART;VALUE=DATE:20260707" in ics and "DTEND;VALUE=DATE:20260709" in ics
    assert "DTSTART;VALUE=DATE:20260714" in ics and "DTEND;VALUE=DATE:20260716" in ics

    # 75-OCTET folding (Greek is 2 bytes/char — count bytes, not chars)
    for ln in lines:
        assert len(ln.encode("utf-8")) <= 75, f"line too long: {ln[:40]}…"
    unfolded = ics.replace("\r\n ", "")
    # TEXT escaping survives unfolding: , and ; are backslash-escaped
    assert "Ζωγράφου\\; και" in unfolded and "Ρυθμίσεις\\," in unfolded

    # plain summary preferred; title fallback when plain is empty
    assert "🚧 Κυκλοφοριακές ρυθμίσεις — Δήμων" in unfolded
    assert "🚧 Πανεπιστημίου" in unfolded
    # LOCATION + URL present
    assert "LOCATION:Ανατολικά\\, Αθήνα" in unfolded
    assert "URL:https://diavgeia.gov.gr/decision/view/935Ζ46ΜΤΛΒ-1ΕΦ" in unfolded

    # Determinism: same input → byte-identical output (quiet git history,
    # stable UIDs for calendar clients)
    assert build(CLOSURES) == ics
    uids = [l for l in unfolded.split("\r\n") if l.startswith("UID:")]
    assert len(set(uids)) == 3, "UIDs unique per (event, run)"

    # Robustness: junk shapes never crash the feed
    assert "BEGIN:VCALENDAR" in build([{}, {"days": None}, {"days": ["x", 5]}])
    assert "BEGIN:VCALENDAR" in build([])

    # File round-trip: CRLF must survive on disk (read with newline="")
    p = Path("t_closures.ics")
    write_ics(p, CLOSURES)
    on_disk = p.read_text(encoding="utf-8")   # note: text mode translates
    raw = open(p, encoding="utf-8", newline="").read()
    assert raw == ics and "\r\n" in raw
    p.unlink()

    print("ALL ICS TESTS PASSED (runs, folding, escaping, determinism, file round-trip)")


if __name__ == "__main__":
    run()
