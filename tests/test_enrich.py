"""Offline tests for sources/enrich.py — date extraction + geo tagging.
Fixture strings are VERBATIM from production data.json (2026-07-03).
Run with:  python tests/test_enrich.py
"""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources.enrich import extract_days, classify_area, looks_dated, extract_hours

TODAY = date(2026, 7, 3)


def run():
    # 1. Range with time-of-day noise: every day expanded, hours ignored
    t1 = ("Ακόλουθες κυκλοφοριακές ρυθμίσεις στα κάτωθι οδικά τμήματα "
          "περιοχής Δήμων Ζωγράφου και Παπάγου-Χολαργού, κατά το χρονικό "
          "διάστημα από 06/07/2026 έως 25/09/2026, κατά τις ώρες 19.00΄ "
          "έως 07.00΄της επομένης")
    d1 = extract_days(t1, TODAY)
    assert d1[0] == "2026-07-06" and d1[-1] == "2026-09-25" and len(d1) == 82, len(d1)

    # 2. Single date + time window ("07.00' έως 12.00'" must not match)
    t2 = ("Προσωρινή διακοπή της κυκλοφορίας στη δεξιά λωρίδα της οδού "
          "Κυψέλης, στις 05.07.2026, κατά τις ώρες 07.00΄ έως 12.00΄")
    assert extract_days(t2, TODAY) == ["2026-07-05"]

    # 3. THE day-list monster (verbatim production title)
    t3 = ("Προσωρινή διακοπή της κυκλοφορίας των οχημάτων στη δεξιά λωρίδα "
          "της οδού Πανεπιστημίου, στις 07, 08, 09, 10, 14, 15, 16, 17, 21, "
          "22, 23, 24, 28, 29, 30 και 31-07-2026, κατά τις")
    d3 = extract_days(t3, TODAY)
    assert len(d3) == 16 and d3[0] == "2026-07-07" and d3[-1] == "2026-07-31", d3

    # 4. Simple single date
    assert extract_days("στις 07.07.2026, κατά τις ώρες", TODAY) == ["2026-07-07"]

    # 5. News style, no year → the NEAREST occurrence, judged AFTER
    #    ranking. A date whose nearest reading is already past (beyond
    #    the grace window) is an event that is OVER — it yields NO days
    #    instead of rolling a year forward. (The "ghost 2027 closures"
    #    production bug: stale tag-page articles like "Τρίτη 23/6",
    #    re-read on 03/07, were resurrected as NEXT June and then kept
    #    alive by the closure registry for a year.)
    assert extract_days("Κλειστοί δρόμοι την Τρίτη 23/6 λόγω αγώνων", TODAY) == []
    assert extract_days("Κλειστοί δρόμοι την Τρίτη 7/7 λόγω αγώνων", TODAY) == ["2026-07-07"]

    # 5b. Year-less resolution across the Dec/Jan boundary and the
    #     grace window (the cases a fixed same-year guess got wrong,
    #     which nearest-occurrence resolution must keep right):
    assert extract_days("στις 30/12", date(2027, 1, 2)) == ["2026-12-30"]   # grace: recent past
    assert extract_days("στις 3/1", date(2026, 12, 30)) == ["2027-01-03"]   # next year IS nearest
    assert extract_days("στις 2 Ιανουαρίου", date(2026, 12, 29)) == ["2027-01-02"]
    assert extract_days("στις 1/7", date(2026, 7, 5)) == ["2026-07-01"]     # 4d past = still live
    assert extract_days("στις 1/7", date(2026, 7, 6)) == []                 # 5d past = OVER (was: 2027 ghost)
    assert extract_days("στις 29/2", date(2027, 3, 1)) == ["2028-02-29"]    # skips non-leap
    # named-month form must expire the same way as the numeric form
    assert extract_days("το Σάββατο 23 Ιουνίου", date(2026, 7, 3)) == []

    # 6. THE TRAP: publication date lives in details — extraction is
    #    title-only by design; verify the date parser alone would have
    #    caught it, proving the title-only rule is what protects us
    assert extract_days("Επίσημη απόφαση Τροχαίας (03/07/2026)", TODAY) == ["2026-07-03"]

    # 7. Weekday-only dates now RESOLVE (nearest occurrence, grace as
    #    numeric): TODAY is Fri 03/07 → "την Πέμπτη" = Thu 02/07.
    assert extract_days("Κυκλοφοριακές ρυθμίσεις στο Ελληνικό την Πέμπτη", TODAY) == ["2026-07-02"]
    assert extract_days("ρυθμίσεις χωρίς καμία ημερομηνία", TODAY) == []

    # 8. Greek month names — the hole named in the design review
    assert extract_days("Διακοπή κυκλοφορίας στις 5 Ιουλίου 2026", TODAY) == ["2026-07-05"]
    assert extract_days("ρυθμίσεις από 6 έως 9 Ιουλίου 2026", TODAY) == [
        "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]
    assert extract_days("το Σάββατο 5 και την Κυριακή 6 Σεπτεμβρίου", TODAY) == [
        "2026-09-05", "2026-09-06"]
    assert extract_days("την 15η Αυγούστου", TODAY) == ["2026-08-15"]   # no year
    assert extract_days("οι 3 μάρτυρες κατέθεσαν στο δικαστήριο", TODAY) == []

    # 9. The parser's smoke detector (looks dated, parsed nothing → flag).
    #    NOTE: since the ghost-closure fix, an expired "23/6" also parses
    #    to zero days ON PURPOSE — looks_dated still fires for it, which
    #    only costs a harmless date_miss count on stale articles.
    assert looks_dated("κλειστοί δρόμοι στις 5 Ιουλίου")
    assert looks_dated("την Τρίτη 23/6")
    assert not looks_dated("Κλειστό το κέντρο λόγω πορείας")

    # 9b. Weekday-only production titles (the live kathimerini/oasa
    #     misses of 17/07) + the guards that keep the fallback honest
    fri = date(2026, 7, 17)
    assert extract_days("Κυκλοφοριακές ρυθμίσεις στη Γραμμή 3 του Μετρό "
                        "από την Κυριακή", fri) == ["2026-07-19"]
    assert extract_days("διακοπή στην τρίτη λωρίδα της Αττικής Οδού", fri) == []
    assert extract_days("την Δευτέρα 20 Ιουλίου", fri) == ["2026-07-20"]  # number wins, once

    # 9c. Long ranges up to 200 days expand fully (production 15.07-18.12)
    dd = extract_days("από 15.07.2026 έως 18.12.2026", fri)
    assert dd[-1] == "2026-12-18" and len(dd) > 150, len(dd)

    # 9d. sane_days: an isolated far-future day is noise (the OASA
    #     2027-01-10 ghost); contiguous ranges pass untouched
    from sources.enrich import sane_days
    assert sane_days(["2026-07-13", "2027-01-10"]) == ["2026-07-13"]
    assert sane_days(dd) == dd

    # 10. Daily time windows ("κατά τις ώρες ...") — start > end means
    #     the window crosses midnight, verbatim production phrasings
    assert extract_hours("κατά τις ώρες 07.00΄ έως 12.00΄, λόγω εργασιών") == ["07:00", "12:00"]
    assert extract_hours("κατά τις ώρες 19.00΄ έως 07.00΄της επομένης") == ["19:00", "07:00"]
    assert extract_hours("κατά τις ώρες 21:00 μέχρι τις 05:30") == ["21:00", "05:30"]
    assert extract_hours("τις πρωινές ώρες αιχμής") == []
    assert extract_hours("κατά τις ώρες 99.00΄ έως 12.00΄") == []   # invalid hour
    assert extract_hours("") == []

    # --- geography (all real production titles) ---
    cases = [
        ("οδού Πανεπιστημίου, ρεύμα προς Ομόνοια, Δήμου Αθηναίων", "", "Κέντρο"),
        ("οδού Κυψέλης, στο ύψος του ο.α.80", "", "Κέντρο"),
        ("Δήμων Ζωγράφου και Παπάγου-Χολαργού", "", "Ανατολικά"),
        ("οδού Παύλου Μπακογιάννη (παράδρομος της Λεωφ. Κηφισού), "
         "περιοχής Δήμου Μεταμόρφωσης", "", "Βόρεια"),
        ("Αθηνών-Κορίνθου/Λ. Αθηνών (έξοδος) ΑΠΌ ΣΚΑΡΑΜΑΓΚΑ", "", "Δυτικά"),
        ("Αττική Οδός ΕΞΟΔΟΙ ΛΑΜΙΑΣ", "", "Βόρεια"),
        ("Κυκλοφοριακές ρυθμίσεις στο Ελληνικό για το Eco Rally", "", "Νότια"),
        ("Κλειστό το κέντρο της Αθήνας έως τις 12:00", "", "Κέντρο"),
        ("Μετρό: ρυθμίσεις στη «μπλε» γραμμή", "", ""),   # untaggable
        ("Σοβαρό τροχαίο", "https://www.google.com/maps?q=37.9792,23.7311", "Κέντρο"),
        ("Σοβαρό τροχαίο", "https://www.google.com/maps?q=38.0300,23.7400", "Βόρεια"),
        ("Κλειστός δρόμος", "https://www.google.com/maps?q=37.9500,23.6500", "Δυτικά"),
    ]
    for text, url, want in cases:
        got = classify_area(text, url)
        assert got == want, f"{text[:40]!r}: want {want!r}, got {got!r}"

    # Κέντρο must win over a suburb mentioned in passing
    assert classify_area("Διακοπή στη Συγγρού, εκτροπή προς Καλλιθέα") == "Κέντρο"

    print("ALL ENRICH TESTS PASSED (numeric+named dates, ghost-closure fix, geo)")


if __name__ == "__main__":
    run()
