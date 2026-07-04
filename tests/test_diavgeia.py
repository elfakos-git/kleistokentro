"""Offline tests for sources/diavgeia.py using a realistic API fixture.
Run with:  python tests/test_diavgeia.py
"""
import sys, time
from datetime import datetime, timedelta, timezone
iso_yday = (datetime.now(timezone(timedelta(hours=3))) - timedelta(days=1))
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
     "issueDate": iso_yday.strftime("%Y-%m-%dT09:30:00+03:00")},
    {"subject": "Διακοπή κυκλοφορίας στην Ομόνοια", "issueDate": now_ms},  # no ADA
    # PRODUCTION NOISE (verbatim category from the first live run):
    # procurement decisions that mention Αττικής but aren't about traffic
    {"ada": "ΝΟΙΣ46ΜΤΛΒ-ΠΡ7", "status": "PUBLISHED",
     "subject": "Ανάθεση προμήθειας χημικών υλικών για την αναγόμωση "
                "πυροσβεστήρων, για την κάλυψη αναγκών της Διεύθυνσης "
                "Δίωξης και Εξιχνίασης Εγκλημάτων Αττικής",
     "issueDate": now_ms - day},
    {"ada": "ΝΟΙΣ46ΜΤΛΒ-ΠΡ8", "status": "PUBLISHED",
     "subject": "Ανάθεση της εργασίας εκκένωσης λυμάτων βόθρου, προς "
                "κάλυψη αναγκών του Τ.Δ.Ε.Ε. Ωρωπού/Αττικής",
     "issueDate": now_ms - day},
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

    with patch.object(diavgeia, "get", return_value=mock_resp) as m:
        events = diavgeia.fetch()
        assert m.call_count == len(diavgeia.QUERIES)   # two-net recall
        p = m.call_args.kwargs["params"]
        assert p["org"] == "100054489" and p["page"] == 0 and p["size"] == 100
        assert len(p["from_issue_date"]) == 10

    ids = [e.id for e in events]
    assert ids == ["9ΞΚΛ46ΜΤΛΒ-ΑΒ1", "ΨΩΣΔ46ΜΤΛΒ-ΜΝ5", "ΡΤΥΦ46ΜΤΛΒ-ΞΟ6"], ids
    for e in events:
        assert e.url == f"https://diavgeia.gov.gr/decision/view/{e.id}"
    assert "  " not in events[0].title
    assert iso_yday.strftime("%d/%m/%Y") in events[1].details

    # Both nets returning the same decisions must not duplicate events
    assert len({e.id for e in events}) == len(events)

    # Schema drift → loud failure (never a silent healthy-looking zero)
    for bad in ({"error": "gone"}, {"decisions": "nope"}):
        mock_resp.json.return_value = bad
        with patch.object(diavgeia, "get", return_value=mock_resp):
            try:
                diavgeia.fetch(); raise AssertionError("should have raised")
            except RuntimeError as e:
                assert "API changed" in str(e)
    print(f"ALL DIAVGEIA TESTS PASSED (kept {len(events)}/10 — procurement noise rejected)")

if __name__ == "__main__":
    run()
