"""Offline tests for sources/enrich.py — date extraction + geo tagging.
Fixture strings are VERBATIM from production data.json (2026-07-03).
Run with:  python tests/test_enrich.py
"""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources.enrich import extract_days, classify_area

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

    # 5. News style, no year → current year
    assert extract_days("Κλειστοί δρόμοι την Τρίτη 23/6 λόγω αγώνων", TODAY) == []  # >7d past
    assert extract_days("Κλειστοί δρόμοι την Τρίτη 7/7 λόγω αγώνων", TODAY) == ["2026-07-07"]

    # 6. THE TRAP: publication date lives in details — extraction is
    #    title-only by design; verify the date parser alone would have
    #    caught it, proving the title-only rule is what protects us
    assert extract_days("Επίσημη απόφαση Τροχαίας (03/07/2026)", TODAY) == ["2026-07-03"]

    # 7. No dates at all
    assert extract_days("Κυκλοφοριακές ρυθμίσεις στο Ελληνικό την Πέμπτη", TODAY) == []

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
        ("Μετρό: ρυθμίσεις στη «μπλε» γραμμή", "", ""),           # untaggable
        ("Σοβαρό τροχαίο", "https://www.google.com/maps?q=37.9792,23.7311", "Κέντρο"),
        ("Σοβαρό τροχαίο", "https://www.google.com/maps?q=38.0300,23.7400", "Βόρεια"),
        ("Κλειστός δρόμος", "https://www.google.com/maps?q=37.9500,23.6500", "Δυτικά"),
    ]
    for text, url, want in cases:
        got = classify_area(text, url)
        assert got == want, f"{text[:40]!r}: want {want!r}, got {got!r}"

    # Κέντρο must win over a suburb mentioned in passing
    assert classify_area("Διακοπή στη Συγγρού, εκτροπή προς Καλλιθέα") == "Κέντρο"

    print("ALL ENRICH TESTS PASSED (dates: ranges/lists/singles/no-year; geo: 13 cases)")

if __name__ == "__main__":
    run()
