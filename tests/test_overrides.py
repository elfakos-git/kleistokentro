"""Admin overrides: removals stick (no display, no notify, no return),
edits win over extraction/classification, and system messages ignore
corrupt override files. Run: python tests/test_overrides.py"""
import json, shutil, sys, types
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import Event
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

def dash():
    return json.loads((DOCS / 'data.json').read_text())

def run():
    if STATE.exists(): STATE.unlink()
    if DOCS.exists(): shutil.rmtree(DOCS)
    DOCS.mkdir()
    SUBS.write_text('[{"chat_id": "x", "urgent_days": 3, "digest_hour": null}]')
    STATE.write_text('{"seeded": ["s"], "seen": []}')
    today = monitor._athens_now().date()
    fmt = "%d/%m/%Y"
    d1 = (today + timedelta(days=1)).strftime(fmt)

    src = types.ModuleType('s')
    src.fetch = lambda: [
        Event('keep-1', 'Διαύγεια (Τροχαία)',
              f'Διακοπή στην Πανεπιστημίου στις {d1}', 'http://x/1'),
        Event('kill-1', 'Διαύγεια (Τροχαία)',
              f'Ασήμαντο έργο στη Σταδίου στις {d1}', 'http://x/2'),
    ]
    monitor.SOURCES = {'s': src}

    # 1. REMOVAL: admin removed kill-1 BEFORE it was ever fetched →
    #    never displayed, never notified, marked seen (never returns)
    OV.write_text(json.dumps({"removed": ["kill-1"], "edits": {}}))
    monitor.main([])
    d = dash()
    ids = [c['id'] for c in d['closures']]
    assert ids == ['keep-1'], ids
    assert not any('Σταδίου' in t for t in sent), sent
    assert any('Πανεπιστημίου' in t for t in sent)
    st = json.loads(STATE.read_text())
    assert 'kill-1' in st['seen']

    # 2. LATE REMOVAL: keep-1 removed AFTER registration → purged from
    #    the registry and the dashboard on the very next run
    OV.write_text(json.dumps({"removed": ["kill-1", "keep-1"], "edits": {}}))
    monitor.main([])
    assert dash()['closures'] == [] and dash()['active_events'] == []

    # 3. EDITS: title, area and dates all overridden; urgent alert uses
    #    the EDITED values (admin's dates put it inside the window)
    far = (today + timedelta(days=60)).strftime(fmt)
    src.fetch = lambda: [Event('ed-1', 'Διαύγεια (Τροχαία)',
        f'Ρυθμίσεις στη Γλυφάδα στις {far}', 'http://x/3')]
    OV.write_text(json.dumps({"removed": [], "edits": {"ed-1": {
        "title": "Κλειστή η παραλιακή για αγώνα",
        "area": "Κέντρο",
        "days": [(today + timedelta(days=1)).isoformat()],
    }}}, ensure_ascii=False))
    sent.clear()
    monitor.main([])
    c = dash()['closures'][0]
    assert c['title'] == "Κλειστή η παραλιακή για αγώνα"
    assert c['area'] == "Κέντρο"                       # was Νότια by keyword
    assert c['days'] == [(today + timedelta(days=1)).isoformat()]
    assert len(sent) == 1 and 'παραλιακή' in sent[0] and 'ΑΥΡΙΟ' in sent[0], sent

    # 4. Corrupt overrides file must never break monitoring
    OV.write_text('{{{not json')
    monitor.main([])
    assert dash()['closures'], "corrupt overrides broke the run"

    STATE.unlink(); SUBS.unlink(); shutil.rmtree(DOCS)
    print("ALL OVERRIDES TESTS PASSED (remove/late-remove/edit/corrupt)")

if __name__ == "__main__":
    run()
