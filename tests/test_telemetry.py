"""Recall visibility: filter drop-counts flow from sources through
source_status into data.json, and the diavgeia fixture's known noise
is ACCOUNTED FOR, not silently gone. Run: python tests/test_telemetry.py"""
import json, shutil, sys, types
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notify
notify.send = lambda t, chat_id=None: None
import importlib, monitor
importlib.reload(monitor)
notify.send = lambda t, chat_id=None: None
from sources import diavgeia
from tests.test_diavgeia import FIXTURE

STATE, DOCS, SUBS = Path('t_state.json'), Path('t_docs'), Path('t_subs.json')
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / 'data.json'
monitor.SUBSCRIBERS_FILE = SUBS

def run():
    if STATE.exists(): STATE.unlink()
    if DOCS.exists(): shutil.rmtree(DOCS)
    SUBS.write_text('[{"chat_id": "x", "digest_hour": null}]')
    STATE.write_text('{"seeded": ["diavgeia"], "seen": []}')
    mock = MagicMock(); mock.json.return_value = FIXTURE
    monitor.SOURCES = {'diavgeia': diavgeia}
    with patch.object(diavgeia, "get", return_value=mock):
        monitor.main([])
    st = json.loads((DOCS / 'data.json').read_text())
    s = [x for x in st['sources'] if x['name'] == 'diavgeia'][0]
    assert s['items'] == 3
    assert s['fetched'] > s['items'], s          # drops are counted
    dropped = s['dropped']
    assert dropped.get("εκτός θέματος/Αθήνας") == 3, dropped     # procurement×2 + Karditsa
    assert dropped.get("μη δημοσιευμένη") == 1, dropped           # revoked
    assert dropped.get("εκτός χρονικού παραθύρου") == 1, dropped  # too old
    assert sum(dropped.values()) + s['items'] == s['fetched']     # books balance
    STATE.unlink(); SUBS.unlink(); shutil.rmtree(DOCS)
    print("ALL TELEMETRY TESTS PASSED (drops counted, books balance)")

if __name__ == "__main__":
    run()
