"""Single-lane closures are below the notification bar: never notified,
never displayed, marked seen (never return) — but COUNTED in telemetry
and rescuable via an admin title edit. Fixtures are verbatim production
titles. Run: python tests/test_lane_filter.py"""
import json, shutil, sys, types
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import Event
from sources.enrich import is_lane_only
import notify
sent = []
notify.send = lambda t, chat_id=None: sent.append(t)
import importlib, monitor
importlib.reload(monitor)
notify.send = lambda t, chat_id=None: sent.append(t)

STATE, DOCS, SUBS = Path('t_state.json'), Path('t_docs'), Path('t_subs.json')
OV = DOCS / 'overrides.json'
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / 'data.json'
monitor.SUBSCRIBERS_FILE = SUBS
monitor.OVERRIDES_FILE = OV

def run():
    # --- classifier, on verbatim production strings ---
    assert is_lane_only("Προσωρινή διακοπή της κυκλοφορίας των οχημάτων "
                        "στη δεξιά λωρίδα της οδού Κυψέλης, στο ύψος του ο.α.80")
    assert is_lane_only("διακοπή στη δεξιά λωρίδα της οδού Πανεπιστημίου, "
                        "ρεύμα κυκλοφορίας προς Ομόνοια")
    assert is_lane_only("κατάληψη της αριστερής λωρίδας λόγω εργασιών")
    assert is_lane_only("διακοπή κυκλοφορίας στη ΛΕΑ της Αττικής Οδού")
    # Whole-street closures and events must survive:
    assert not is_lane_only("Προσωρινή διακοπή της κυκλοφορίας των οχημάτων "
                            "επί της οδού Παύλου Μπακογιάννη")
    assert not is_lane_only("Κλειστή η δεξιά λωρίδα και ολική διακοπή "
                            "το Σάββατο")                       # major wins
    assert not is_lane_only("διακοπή των δύο λωρίδων της Κηφισίας")
    assert not is_lane_only("πορεία διαμαρτυρίας στη δεξιά λωρίδα")  # event
    assert not is_lane_only("Κλειστό το κέντρο της Αθήνας")

    # --- end-to-end: filtered at ingestion, counted, permanent ---
    if STATE.exists(): STATE.unlink()
    if DOCS.exists(): shutil.rmtree(DOCS)
    DOCS.mkdir()
    SUBS.write_text('[{"chat_id": "x", "urgent_days": 5, "digest_hour": null}]')
    STATE.write_text('{"seeded": ["s"], "seen": []}')
    today = monitor._athens_now().date()
    d1 = (today + timedelta(days=1)).strftime("%d/%m/%Y")
    lane = Event('lane-1', 'Διαύγεια (Τροχαία)',
                 f'Διακοπή στη δεξιά λωρίδα της οδού Κυψέλης στις {d1}', 'http://x/l')
    full = Event('full-1', 'Διαύγεια (Τροχαία)',
                 f'Διακοπή της κυκλοφορίας στην οδό Σταδίου στις {d1}', 'http://x/f')
    src = types.ModuleType('s'); src.fetch = lambda: [lane, full]
    monitor.SOURCES = {'s': src}

    monitor.main([])
    d = json.loads((DOCS / 'data.json').read_text())
    assert [c['id'] for c in d['closures']] == ['full-1']
    assert len(sent) == 1 and 'Σταδίου' in sent[0], sent
    s = d['sources'][0]
    assert s['items'] == 1 and s['dropped'].get('μόνο μία λωρίδα/ΛΕΑ') == 1
    assert s['items'] + sum(s['dropped'].values()) == s['fetched']
    st = json.loads(STATE.read_text())
    assert 'lane-1' in st['seen']                 # never returns, never pings
    monitor.main([])
    assert len(sent) == 1                          # and stays silent

    # --- the escape hatch: an admin title edit rescues a lane event ---
    # Realistic rescue = rename (beats the filter) + set the dates
    # (routes it into the registry/urgent tier, not just the feed)
    OV.write_text(json.dumps({"removed": [], "edits": {"lane-1": {
        "title": "ΣΗΜΑΝΤΙΚΟ: κλειστή ουσιαστικά η Κυψέλης",
        "days": [(today + timedelta(days=1)).isoformat()]}}},
        ensure_ascii=False))
    st['seen'] = []                                # simulate fresh sighting
    STATE.write_text(json.dumps(st))
    monitor.main([])
    d = json.loads((DOCS / 'data.json').read_text())
    assert any(c['id'] == 'lane-1' for c in d['closures']), \
        "admin edit failed to rescue the event"

    STATE.unlink(); SUBS.unlink(); shutil.rmtree(DOCS)
    print("ALL LANE-FILTER TESTS PASSED (classifier, ingestion, telemetry, rescue)")

if __name__ == "__main__":
    run()
