"""Offline tests for sources/humanize.py — plain-language summaries.
Fixture titles are VERBATIM from production data.json.
Run with:  python tests/test_humanize.py
"""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources.humanize import summarize, compact_days, extract_hours

TODAY = date(2026, 7, 6)


def run():
    # 1. The Κυψέλης decision: street + lane + height + hours + reason
    t = ("25403 - Προσωρινές κυκλοφοριακές ρυθμίσεις - Προσωρινή διακοπή "
         "της κυκλοφορίας των οχημάτων στη δεξιά λωρίδα της οδού Κυψέλης, "
         "στο ύψος του ο.α.80, περιοχής Δήμου Αθηναίων, στις 05.07.2026, "
         "κατά τις ώρες 07.00΄ έως 12.00΄, λόγω εκτέλεσης εργασιών "
         "επισκευής των εξωστών του κτιρίου.")
    s = summarize(t, days=["2026-07-05"], today=TODAY)
    assert s.startswith("Διακοπή κυκλοφορίας στην οδό Κυψέλης"), s
    for bit in ("δεξιά λωρίδα", "ύψος αρ. 80", "5/7", "07:00–12:00",
                "λόγω εργασιών επισκευής"):
        assert bit in s, (bit, s)
    assert len(s) < len(t), "summary must be shorter"

    # 2. Μπακογιάννη: section (από/έως) + direction; truncated reason dropped
    t = ("25404 - Προσωρινές κυκλοφοριακές ρυθμίσεις - Προσωρινή διακοπή "
         "της κυκλοφορίας των οχημάτων επί της οδού Παύλου Μπακογιάννη, "
         "(παράδρομος της Λεωφ. Κηφισού), από το ύψος της οδού Νιρβάνα "
         "έως το ύψος της οδού Δερβενίων, στο ρεύμα κυκλοφορίας προς "
         "Λαμία, περιοχής Δήμου Μεταμόρφωσης, στις 07.07.2026, κα")
    s = summarize(t, days=["2026-07-07"], today=TODAY)
    assert "Διακοπή κυκλοφορίας" in s and "Παύλου Μπακογιάννη" in s, s
    assert "από Νιρβάνα έως Δερβενίων" in s, s
    assert "προς Λαμία" in s and "7/7" in s, s
    # the section's "οδού Νιρβάνα" must NOT have been mistaken for the street
    assert "στην οδό Νιρβάνα" not in s, s

    # 3. Range decision, no street named → municipality carries the where
    t = ("25406 - Προσωρινές κυκλοφοριακές ρυθμίσεις - Ακόλουθες "
         "κυκλοφοριακές ρυθμίσεις στα κάτωθι οδικά τμήματα περιοχής Δήμων "
         "Ζωγράφου και Παπάγου-Χολαργού, κατά το χρονικό διάστημα από "
         "06/07/2026 έως 25/09/2026, κατά τις ώρες 19.00΄ έως 07.00΄της "
         "επομένης, με εξαίρεση τις επίσημες Αργίες, λόγω εκτέλεσης α")
    days = [(date(2026, 7, 6).toordinal() + i) for i in range(82)]
    days = [date.fromordinal(o).isoformat() for o in days]
    s = summarize(t, days=days, today=TODAY)
    assert "Δήμων Ζωγράφου και Παπάγου-Χολαργού" in s, s
    assert "6/7 – 25/9" in s and "19:00–07:00" in s, s
    assert "λόγω" not in s, ("truncated 'λόγω εκτέλεσης α' must be dropped", s)

    # 4. The 16-day Πανεπιστημίου list → count + span
    days16 = [f"2026-07-{d:02d}" for d in
              (7, 8, 9, 10, 14, 15, 16, 17, 21, 22, 23, 24, 28, 29, 30, 31)]
    t = ("Προσωρινή διακοπή της κυκλοφορίας των οχημάτων στη δεξιά λωρίδα "
         "της οδού Πανεπιστημίου, στο ύψος του ο.α.48, ρεύμα κυκλοφορίας "
         "προς Ομόνοια, περιοχής Δήμου Αθηναίων, στις 07, 08, 09, 10, 14, "
         "15, 16, 17, 21, 22, 23, 24, 28, 29, 30 και 31-07-2026, κατά τις ")
    s = summarize(t, days=days16, today=TODAY)
    assert "Πανεπιστημίου" in s and "προς Ομόνοια" in s, s
    assert "16 ημέρες, 7/7 – 31/7" in s, s

    # 5. News headlines are already human → NO summary (fall through)
    for headline in (
            "Αθήνα: Κλειστοί δρόμοι την Τρίτη 23/6 λόγω αγώνων δρόμου",
            "Μετρό: Κυκλοφοριακές ρυθμίσεις στη «μπλε» γραμμή – Ποιοι "
            "σταθμοί θα κλείνουν νωρίτερα",
            "Τροποποίηση γραμμής 837"):
        assert summarize(headline, days=[], today=TODAY) == "", headline

    # 6. compact_days corner cases
    assert compact_days(["2026-07-05"], TODAY) == "5/7"
    assert compact_days(["2026-07-06", "2026-07-07", "2026-07-08"], TODAY) == "6/7 – 8/7"
    assert compact_days(["2026-07-07", "2026-07-09", "2026-07-12"], TODAY) == "7/7, 9/7, 12/7"
    assert compact_days(["2027-01-03"], TODAY) == "3/1/27"     # year shown when ≠ ref
    assert compact_days([], TODAY) == ""

    # 7. hours extraction never confuses dates for times
    assert extract_hours("κατά τις ώρες 19.00΄ έως 07.00΄της επομένης") == "19:00–07:00"
    assert extract_hours("στις 05.07.2026 και ξανά στις 06.07.2026") == ""
    assert extract_hours("ώρες 99.00 έως 12.00") == ""          # invalid clock

    # 8. Additive contract: garbage in, empty out — never an exception
    for junk in ("", "   ", "α", "25403 - "):
        assert summarize(junk, days=[], today=TODAY) == ""

    print("ALL HUMANIZE TESTS PASSED (Diavgeia bureaucratese → readable Greek)")


if __name__ == "__main__":
    run()
