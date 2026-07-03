"""Offline tests for sources/diavgeia.py using a realistic API fixture.
Run with:  python tests/test_diavgeia.py
"""
import sys, time
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

now_ms = int(time.time() * 1000)
day = 86_400_000

FIXTURE = {
  "decisions": [
    {"ada": "9ΞΚΛ46ΜΤΛΒ-ΑΒ1", "status": "PUBLISHED",
     "subject": "Προσωρινές  κυκλοφοριακές   ρυθμίσεις επί της Λ. Συγγρού "
                "και της οδού Σταδίου, λόγω αγώνα δρόμου",
     "issueDate": now_ms - day},
    {"ada": "6ΤΡΞ46ΜΤΛΒ-ΓΔ2", "status": "PUBLISHED",   # other city
     "subject": "Προσωρινές κυκλοφοριακές ρυθμίσεις σε οδούς της πόλεως "
                "Καρδίτσας λόγω εργασιών", "issueDate": now_ms - day},
    {"ada": "ΩΠΑΛ46ΜΤΛΒ-ΕΖ3", "status": "PUBLISHED",   # too old
     "subject": "Κυκλοφοριακές ρυθμίσεις στο κέντρο της Αθήνας",
     "issueDate": now_ms - 10*day},
    {"ada": "7ΗΘΙ46ΜΤΛΒ-ΚΛ4", "status": "REVOKED",     # revoked
     "subject": "Διακοπή κυκλοφορίας στην Πανεπιστημίου",
     "issueDate": now_ms - day},
    {"ada": "ΨΩΣΔ46ΜΤΛΒ-ΜΝ5", "status": "PUBLISHED",   # ISO date variant
     "subject": "Διακοπή κυκλοφορίας στη Βασιλίσσης Σοφίας λόγω "
                "επίσημης επίσκεψης",
     "issueDate": "2026-07-01T09:30:00+03:00"},
    {"subject": "Ρυθμίσεις στην Ομόνοια", "issueDate": now_ms},  # no ADA
    {"ada": "ΡΤΥΦ46ΜΤΛΒ-ΞΟ6",                         # minimal but valid
     "subject": "Κυκλοφοριακές ρυθμίσεις πέριξ της Πλατείας Συντάγματος"},
    "garbage-not-a-dict",
  ],
  "info": {"page": 0, "size": 100, "total": 8},
}

from sources import diavgeia

def run():
    mock_resp = MagicMock()
    mock_resp.json.return_value = FIXTURE
    mock_resp.raise_for_status.return_value = None

    with patch.object(diavgeia.requests, "get", return_value=mock_resp) as m:
        events = diavgeia.fetch()
        p = m.call_args.kwargs["params"]
        assert m.call_args.kwargs.get("timeout") == 30
        assert p["org"] == "100054489" and p["page"] == 0 and p["size"] == 100
        assert "κυκλοφοριακές ρυθμίσεις" in p["q"]
        assert len(p["from_issue_date"]) == 10

    ids = [e.id for e in events]
    assert ids == ["9ΞΚΛ46ΜΤΛΒ-ΑΒ1", "ΨΩΣΔ46ΜΤΛΒ-ΜΝ5", "ΡΤΥΦ46ΜΤΛΒ-ΞΟ6"], ids
    for e in events:
        assert e.url == f"https://diavgeia.gov.gr/decision/view/{e.id}"
    assert "  " not in events[0].title
    assert "01/07/2026" in events[1].details

    # Schema drift → loud failure (never a silent healthy-looking zero)
    for bad in ({"error": "gone"}, {"decisions": "nope"}):
        mock_resp.json.return_value = bad
        with patch.object(diavgeia.requests, "get", return_value=mock_resp):
            try:
                diavgeia.fetch(); raise AssertionError("should have raised")
            except RuntimeError as e:
                assert "API changed" in str(e)
    print("ALL DIAVGEIA TESTS PASSED (kept 3/8 fixture decisions)")

if __name__ == "__main__":
    run()
