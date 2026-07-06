"""OASA source: relevance policy on realistic titles, RSS parsing,
HTML fallback, telemetry. Run: python tests/test_oasa.py"""
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import oasa

now = datetime.now(timezone.utc)
def rss(items):
    body = "".join(
        f"<item><title>{t}</title><link>{l}</link>"
        f"<pubDate>{format_datetime(d)}</pubDate></item>"
        for t, l, d in items)
    return f'<?xml version="1.0"?><rss><channel>{body}</channel></rss>'.encode()

ITEMS = [
    # KEEP: works on a named street, dated title (verbatim style)
    ("Προσωρινή μερική τροποποίηση των γραμμών 523, 524 λόγω εργασιών "
     "επί της οδού Αδριανού του Δήμου Κηφισιάς, στις 15/07/2026",
     "http://oasa.gr/blog/1", now - timedelta(days=1)),
    # KEEP: strike-day modifications
    ("Έκτακτες κυκλοφοριακές ρυθμίσεις λόγω απεργίας",
     "http://oasa.gr/blog/2", now - timedelta(hours=3)),
    # SKIP: telematics maintenance (operations noise)
    ("Προγραμματισμένες εργασίες συντήρησης του συστήματος τηλεματικής",
     "http://oasa.gr/blog/3", now),
    # SKIP: holiday timetable post
    ("Πρόγραμμα δρομολογίων λεωφορείων για τις 24-25 Μαρτίου",
     "http://oasa.gr/blog/4", now),
    # SKIP: restoration announcement
    ("Άρση τροποποίησης της διαδρομής της γραμμής 117",
     "http://oasa.gr/blog/5", now),
    # SKIP: too old, despite being relevant
    ("Τροποποίηση λόγω εργασιών επί της οδού Λιοσίων",
     "http://oasa.gr/blog/6", now - timedelta(days=10)),
]

def run():
    resp = MagicMock(); resp.content = rss(ITEMS)
    with patch.object(oasa, "get", return_value=resp):
        events = oasa.fetch()
    assert [e.id for e in events] == ["http://oasa.gr/blog/1",
                                      "http://oasa.gr/blog/2"], [e.id for e in events]
    assert oasa.last_tally.get("λειτουργικό/χωρίς οδικό αντίκτυπο") == 3
    assert oasa.last_tally.get("παλιά ανακοίνωση") == 1

    # RSS dead → HTML fallback still yields relevant links
    html = ('<html><body>'
            '<a href="/blog/works-post/">Τροποποίηση γραμμών λόγω εργασιών '
            'επί της οδού Πατησίων του Δήμου Αθηναίων</a>'
            '<a href="/blog/telematics/">Εργασίες συντήρησης του συστήματος '
            'τηλεματικής την Κυριακή</a>'
            '<a href="/blog/">Πίσω στη λίστα των ανακοινώσεων του οργανισμού</a>'
            '</body></html>')
    bad = MagicMock(); bad.content = b"not xml at all"
    ok = MagicMock(); ok.text = html
    with patch.object(oasa, "get", side_effect=[bad, ok]):
        events = oasa.fetch()
    assert [e.id for e in events] == ["https://www.oasa.gr/blog/works-post/"], \
        [e.id for e in events]
    print("ALL OASA TESTS PASSED (relevance, RSS, fallback, telemetry)")

if __name__ == "__main__":
    run()
