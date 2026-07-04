"""Offline tests for the v2 astynomia policy (fixture HTML).
Run: python tests/test_astynomia.py"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import astynomia

ATH = ZoneInfo("Europe/Athens")

def html(bulletin_dt):
    stamp = bulletin_dt.strftime("%d/%m/%Y – %H:%M")
    return f"""<html><body>
    <p>Τελευταία Ενημέρωση: {stamp}</p>
    <table>
      <tr><th>ΟΔΙΚΟΣ ΑΞΟΝΑΣ</th><th>Κίνηση</th><th>ΕΠΙΣΗΜΑΝΣΕΙΣ</th></tr>
      <tr><td>Λ. Συγγρού</td><td><img src="/img/green.png"></td>
          <td>Πορεία διαμαρτυρίας προς Σύνταγμα</td></tr>
      <tr><td>Κηφισός</td><td><img src="/img/red_poli.png"></td>
          <td>ΑΠΟ ΑΧΑΡΝΩΝ ΕΩΣ ΦΙΛΑΔΕΛΦΕΙΑ</td></tr>
      <tr><td>Λ. Αλεξάνδρας</td><td><img src="/img/orange.png"></td>
          <td>ΑΠΟ ΓΗΠΕΔΟ ΕΩΣ ΠΑΤΗΣΙΩΝ</td></tr>
      <tr><td>Πατησίων</td><td><img src="/img/green.png"></td><td></td></tr>
      <tr><td>Λ. Ποσειδώνος</td><td><img src="/img/red_poli.png"></td>
          <td></td></tr>
    </table></body></html>"""

def run_at(dt, page):
    resp = MagicMock(); resp.text = page
    with patch.object(astynomia, "get", return_value=resp), \
         patch.object(astynomia, "_athens_now", return_value=dt):
        return astynomia.fetch()

def run():
    # Tue 14:00 (OFF-peak): keyword event + 2 Πολύ-Αυξημένη anomalies
    tue_off = datetime(2026, 7, 7, 14, 0, tzinfo=ATH)
    evs = run_at(tue_off, html(tue_off))
    by = {e.title: e for e in evs}
    assert set(by) == {"Λ. Συγγρού", "Κηφισός", "Λ. Ποσειδώνος"}, set(by)
    assert "Πορεία" in by["Λ. Συγγρού"].details            # keyword event
    assert "εκτός ωρών αιχμής" in by["Κηφισός"].details    # anomaly
    assert "ΑΠΟ ΑΧΑΡΝΩΝ" in by["Κηφισός"].details          # extent = detail
    # Same road, same day → same anomaly id (once/day)...
    id1 = by["Κηφισός"].id
    assert run_at(tue_off, html(tue_off))[1].id == id1
    # ...different day → new id (can fire again)
    wed = datetime(2026, 7, 8, 14, 0, tzinfo=ATH)
    assert run_at(wed, html(wed))[1].id != id1

    # Tue 08:30 (rush): anomalies suppressed, keyword event survives
    tue_rush = datetime(2026, 7, 7, 8, 30, tzinfo=ATH)
    evs = run_at(tue_rush, html(tue_rush))
    assert [e.title for e in evs] == ["Λ. Συγγρού"], [e.title for e in evs]

    # Sunday 08:30: no expected rush → anomalies fire even at 08:30
    sun = datetime(2026, 7, 12, 8, 30, tzinfo=ATH)
    evs = run_at(sun, html(sun))
    assert {e.title for e in evs} == {"Λ. Συγγρού", "Κηφισός", "Λ. Ποσειδώνος"}

    # Stale bulletin (13h old) → no events at all
    now = datetime(2026, 7, 7, 14, 0, tzinfo=ATH)
    old = datetime(2026, 7, 7, 0, 30, tzinfo=ATH)
    assert run_at(now, html(old)) == []

    # Missing timestamp → loud failure
    resp = MagicMock(); resp.text = "<html><body><table></table></body></html>"
    with patch.object(astynomia, "get", return_value=resp):
        try:
            astynomia.fetch(); raise AssertionError("should have raised")
        except RuntimeError as e:
            assert "layout changed" in str(e)
    print("ALL ASTYNOMIA TESTS PASSED (keywords, rush gating, weekend, ids)")

if __name__ == "__main__":
    run()
