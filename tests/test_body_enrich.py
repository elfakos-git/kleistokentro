"""Body enrichment: dates/areas recovered from article BODIES when the
title carries none — paragraphs only (the pub-date trap lives in
headers/<time>, never <p>), budgeted, never fatal.
Run: python tests/test_body_enrich.py"""
import json, shutil, sys, types
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import Event
from sources.enrich import from_article_html
import notify
notify.send = lambda t, chat_id=None: None
import importlib, monitor
importlib.reload(monitor)
notify.send = lambda t, chat_id=None: None

STATE, DOCS, SUBS = Path('t_state.json'), Path('t_docs'), Path('t_subs.json')
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / 'data.json'
monitor.SUBSCRIBERS_FILE = SUBS

ARTICLE = """<html><body>
<time datetime="2026-07-03">Δημοσίευση: 03/07/2026 09:15</time>
<p>Διαφημιστικό κείμενο άσχετο με το θέμα του άρθρου εντελώς.</p>
<p>Κυκλοφοριακές ρυθμίσεις θα ισχύσουν στη Γλυφάδα λόγω αγώνα δρόμου,
με διακοπή της κυκλοφορίας από 6 έως 9 Ιουλίου 2026 στην παραλιακή.</p>
<p>Σχετικά άρθρα και προτάσεις για διάβασμα από τη σύνταξη.</p>
</body></html>"""

def run():
    today = date(2026, 7, 3)
    # Pure function: dates from the traffic paragraph ONLY
    days, area = from_article_html(ARTICLE, today)
    assert days == ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"], days
    assert "2026-07-03" not in days, "publication date leaked from <time>!"
    assert area == "Νότια", area
    assert from_article_html("<html><p>Καμία σχέση με δρόμους.</p></html>",
                             today) == ([], "")

    # Monitor path: undated titles get enriched, within the budget
    if STATE.exists(): STATE.unlink()
    if DOCS.exists(): shutil.rmtree(DOCS)
    SUBS.write_text('[{"chat_id": "x", "urgent_days": 0, "digest_hour": null}]')
    STATE.write_text('{"seeded": ["s"], "seen": []}')
    src = types.ModuleType('s')
    src.BODY_ENRICH = True
    src.fetch = lambda: [Event(f'n{i}', 'iefimerida',
                               f'Κυκλοφοριακές ρυθμίσεις το επόμενο διάστημα ({i})',
                               f'http://x/{i}') for i in range(5)]
    monitor.SOURCES = {'s': src}
    calls = []
    resp = MagicMock(); resp.text = ARTICLE
    def fake_get(url, *a, **k):
        calls.append(url); return resp
    with patch.object(monitor, "get", side_effect=fake_get), \
         patch.object(monitor, "_athens_now",
                      return_value=__import__("datetime").datetime(2026, 7, 3, 12, 0)):
        monitor.main([])
    assert len(calls) == 3, f"budget violated: {len(calls)} fetches"
    d = json.loads((DOCS / 'data.json').read_text())
    enriched = [c for c in d['closures'] if c['days']]
    assert len(enriched) == 3 and all(c['area'] == 'Νότια' for c in enriched)
    s = d['sources'][0]
    assert s['body_enriched'] == 3, s
    STATE.unlink(); SUBS.unlink(); shutil.rmtree(DOCS)
    print("ALL BODY-ENRICH TESTS PASSED (paragraphs-only, budget, telemetry)")

if __name__ == "__main__":
    run()
