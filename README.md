"""Offline tests for monitor.py orchestration guarantees.
Run with:  python tests/test_monitor.py
Covers: per-source silent seeding, exactly-once delivery, confirmed-
delivery persistence (Telegram-down retry), flood cap, failure alerts,
--only subsets, dashboard merge, state pruning.
"""
import json, shutil, sys, types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import Event

sent, broken = [], {"down": False}
fake = types.ModuleType('notify')
def _send(t):
    if broken["down"]:
        raise RuntimeError("telegram down")
    sent.append(t)
fake.send = _send
fake.format_event = lambda e: f"{e.source}: {e.title}"
sys.modules['notify'] = fake

def mk(evts):
    m = types.ModuleType('m'); m.fetch = lambda: list(evts); return m
def boom():
    raise RuntimeError("blocked")

import importlib, monitor
importlib.reload(monitor)
STATE, DOCS = Path('t_state.json'), Path('t_docs')
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / 'data.json'

def state():
    return json.loads(STATE.read_text())
def dash():
    return json.loads((DOCS / 'data.json').read_text())

def run():
    if STATE.exists(): STATE.unlink()
    if DOCS.exists(): shutil.rmtree(DOCS)
    news = mk([Event('n1', 'iefimerida', 'Άρθρο 1', 'http://x/1')])
    wz = mk([])
    bad = types.ModuleType('b'); bad.fetch = boom
    monitor.SOURCES = {'iefimerida': news, 'waze': wz, 'bad': bad}

    # 1. Waze-only runs FIRST (the old footgun): must seed only waze
    monitor.main(['--only', 'waze'])
    assert state()['seeded'] == ['waze'] and sent == []

    # 2. Full run: iefimerida seeds silently despite waze already seeded
    monitor.main([])
    assert sent == [] and set(state()['seeded']) == {'iefimerida', 'waze'}
    assert 'n1' in state()['seen']
    assert {s['name'] for s in dash()['sources']} == {'iefimerida', 'waze', 'bad'}
    assert not any(e['new_this_run'] for e in dash()['active_events'])

    # 3. New article + Telegram DOWN: not delivered, NOT marked seen
    news.fetch = lambda: [Event('n1','iefimerida','Άρθρο 1','http://x/1'),
                          Event('n2','iefimerida','Άρθρο 2','http://x/2')]
    broken["down"] = True
    monitor.main([])
    assert sent == [] and 'n2' not in state()['seen'], "lost event on outage!"

    # 4. Telegram back: SAME event delivered exactly once, then persisted
    broken["down"] = False
    monitor.main([])
    assert sent == ['iefimerida: Άρθρο 2'] and 'n2' in state()['seen']
    monitor.main([])
    assert len(sent) == 1, "duplicate notification"

    # 5. Failure alert exactly at threshold: 'bad' has failed in the 4
    #    full runs so far (the --only waze run correctly excluded it);
    #    two more full runs reach 6 -> exactly one alert
    monitor.main([])
    monitor.main([])
    alerts = [m for m in sent if 'bad' in m]
    assert len(alerts) == 1, alerts
    assert state()['source_status']['bad']['consecutive_failures'] == 6

    # 6. Flood cap: 12 new -> 8 delivered + 1 summary; the 4 skipped are
    #    persisted (deliberate skip, no retry storm next run)
    sent.clear()
    news.fetch = lambda: [Event(f'f{i}','iefimerida',f'T{i}',f'http://x/f{i}')
                          for i in range(12)]
    monitor.main(['--only', 'iefimerida'])
    assert len([m for m in sent if m.startswith('iefimerida')]) == 8
    assert any('ακόμη' in m for m in sent)
    assert all(f'f{i}' in state()['seen'] for i in range(12))

    # 7. Removing a source prunes its state
    monitor.SOURCES = {'iefimerida': news, 'waze': wz}
    monitor.main(['--only', 'waze'])
    s = state()
    assert 'bad' not in s['source_status'] and 'bad' not in s['seeded']
    assert {x['name'] for x in dash()['sources']} == {'iefimerida', 'waze'}

    # 8. Legacy state migration: initialized:true -> all sources seeded
    STATE.write_text('{"initialized": true, "seen": [], "failures": {}}')
    st = monitor.load_state()
    assert set(st['seeded']) == set(monitor.SOURCES) and 'failures' not in st

    STATE.unlink(); shutil.rmtree(DOCS)
    print("ALL MONITOR TESTS PASSED (8 scenarios)")

if __name__ == "__main__":
    run()
