"""iefimerida source — regression guard for the import/Tally crash plus
the real parsing path. Built from the live listing structure.
Run: python tests/test_iefimerida.py"""
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import iefimerida

ATH = ZoneInfo("Europe/Athens")

def listing(rows):
    """rows: list of (href, category, dd/mm/yyyy hh:mm, headline)"""
    cards = ""
    for href, cat, when, head in rows:
        cards += (f'<div class="views-row">'
                  f'<span>{cat}</span> {when}'
                  f'<h3><a href="{href}">{head}</a></h3></div>')
    return f"<html><body>{cards}</body></html>"

def run():
    now = datetime.now(ATH)
    recent = (now - timedelta(days=1)).strftime("%d/%m/%Y %H:%M")
    old = (now - timedelta(days=30)).strftime("%d/%m/%Y %H:%M")

    html = listing([
        # KEEP: recent, Athens-relevant
        ("/ellada/kykloforiakes-rythmiseis-kentro-athinas-kyriaki", "ΕΛΛΑΔΑ",
         recent, "Κυκλοφοριακές ρυθμίσεις στο κέντρο της Αθήνας την Κυριακή"),
        # DROP: another region (Thessaloniki), even if recent
        ("/ellada/kleistos-perifereiakos-thessaloniki-logo-flyover", "ΕΛΛΑΔΑ",
         recent, "Κλειστός ο περιφερειακός στη Θεσσαλονίκη λόγω Flyover"),
        # DROP: too old
        ("/ellada/kykloforiakes-rythmiseis-attikis-odos-aerodromio", "ΕΛΛΑΔΑ",
         old, "Κυκλοφοριακές ρυθμίσεις στην Αττική Οδό κοντά στο αεροδρόμιο"),
    ])
    resp = MagicMock(); resp.text = html
    with patch.object(iefimerida, "get", return_value=resp):
        events = iefimerida.fetch()   # must NOT raise (the original bug)

    ids = [e.url for e in events]
    assert ids == ["https://www.iefimerida.gr/ellada/"
                   "kykloforiakes-rythmiseis-kentro-athinas-kyriaki"], ids
    assert events[0].source == "iefimerida"
    # Telemetry populated => Tally is wired correctly
    assert iefimerida.last_tally.get("άλλη περιοχή") == 1, dict(iefimerida.last_tally)
    assert iefimerida.last_tally.get("χωρίς/παλιά ημερομηνία") == 1, dict(iefimerida.last_tally)

    # Empty listing must return [] cleanly, not crash
    empty = MagicMock(); empty.text = "<html><body></body></html>"
    with patch.object(iefimerida, "get", return_value=empty):
        assert iefimerida.fetch() == []
    print("ALL IEFIMERIDA TESTS PASSED (no crash, relevance, age, telemetry)")

if __name__ == "__main__":
    run()
