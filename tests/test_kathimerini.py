"""Offline tests for sources/kathimerini.py — built from the ACTUAL junk
observed in production (subscription buttons, newsletters, promos).
Run with:  python tests/test_kathimerini.py
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Verbatim junk categories from the first live run + real article shapes
HTML = """
<html><body>
<a href="https://www.kathimerini.gr/syndromes/?utm_source=header_blue&utm_medium=button">
  Κάνε συνδρομή με 0,16€/μέρα</a>
<a href="/giati-na-eggrafw/">K Premium γιατί να εγγραφώ τώρα</a>
<a href="https://www.kathimerini.gr/newsletters/">NewslettersΑποκτήστε πλεονέκτημα στην ενημέρωση!</a>
<a href="https://www.kathimerini.gr/reimagine-tourism/el/">Reimagine Tourism in GreeceΜία πρωτοβουλία της Καθημερινής</a>
<a href="https://www.kathimerini.gr/tag/kykloforiakes-rythmiseis/">Κυκλοφοριακές ρυθμίσεις — όλα τα άρθρα της κατηγορίας</a>
<a href="https://www.kathimerini.gr/society/564312118/metro-kykloforiakes-rythmiseis/?utm_campaign=x">
  Μετρό: Κυκλοφοριακές ρυθμίσεις στη «μπλε» γραμμή – Ποιοι σταθμοί κλείνουν</a>
<a href="/society/564276574/thessaloniki-kykloforiakes-rythmiseis-logo-flyover/">
  Θεσσαλονίκη: κυκλοφοριακές ρυθμίσεις λόγω flyover στην πόλη</a>
<a href="https://www.kathimerini.gr/society/564291292/athina-kleistoi-dromoi/">
  Αθήνα: Κλειστοί δρόμοι την Τρίτη λόγω αγώνων δρόμου</a>
</body></html>
"""

from sources import kathimerini

def run():
    # Force the HTML fallback path: first call (RSS) raises, second returns HTML
    rss_fail = RuntimeError("feed blocked")
    html_resp = MagicMock(text=HTML)
    with patch.object(kathimerini, "get",
                      side_effect=[rss_fail, html_resp]) as m:
        events = kathimerini.fetch()
        assert m.call_count == 2   # RSS attempted, then HTML fallback

    urls = [e.url for e in events]
    # ONLY the two genuine, relevant articles survive:
    assert urls == [
        "https://www.kathimerini.gr/society/564312118/metro-kykloforiakes-rythmiseis/",
        "https://www.kathimerini.gr/society/564291292/athina-kleistoi-dromoi/",
    ], urls
    # utm tracking stripped from identity → rotating params can't re-notify
    assert all("utm" not in u and "?" not in u for u in urls)
    # Junk rejected: subscription, premium, newsletters, promo, tag page
    assert not any("syndromes" in u or "newsletters" in u for u in urls)
    # Θεσσαλονίκη-only article rejected by relevance filter
    assert not any("thessaloniki" in u for u in urls)
    print("ALL KATHIMERINI TESTS PASSED (2/8 links kept, production junk rejected)")

if __name__ == "__main__":
    run()
