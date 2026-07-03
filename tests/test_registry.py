"""Retention is keyed to the EVENT's dates, not the posting date.
Covers the two failure modes: (a) a long closure must outlive its
announcement's presence on the source, (b) an ended event must vanish
from 'active' and never notify. Run: python tests/test_registry.py
"""
import json, shutil, sys, types
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import Event

sent = []
fake = types.ModuleType('notify')
fake.send = lambda t: sent.append(t)
fake.format_event = lambda e: f"{e.source}: {e.title}"
sys.modules['notify'] = fake

import importlib, monitor
importlib.reload(monitor)
STATE, DOCS = Path('t_state.json'), Path('t_docs')
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / 'data.json'

def dash():
    return json.loads((DOCS / 'data.json').read_text())

def run():
    if STATE.exists(): STATE.unlink()
    if DOCS.exists(): shutil.rmtree(DOCS)
    today = date.today()
    fmt = "%d/%m/%Y"
    start = (today + timedelta(days=3)).strftime(fmt)
    end = (today + timedelta(days=40)).strftime(fmt)
    yday = (today - timedelta(days=1)).strftime(fmt)

    src = types.ModuleType('s')
    long_ev = Event('ada-long', 'Διαύγεια (Τροχαία)',
                    f'Ρυθμίσεις στην οδό Σταδίου από {start} έως {end}',
                    'http://x/long')
    over_ev = Event('ada-over', 'Διαύγεια (Τροχαία)',
                    f'Διακοπή κυκλοφορίας στην Ομόνοια στις {yday}',
                    'http://x/over')
    src.fetch = lambda: [long_ev, over_ev]
    monitor.SOURCES = {'diavgeia': src}
    STATE.write_text('{"seeded": ["diavgeia"], "seen": []}')

    # Run 1: long event notifies + enters registry; ENDED event does
    # neither — posting date (today) is irrelevant, its dates passed
    monitor.main([])
    d = dash()
    assert len(sent) == 1 and long_ev.title in sent[0], sent
    assert '📍 Κέντρο' in sent[0]   # Σταδίου → geo tag rides along
    assert [c['title'] for c in d['closures']] == [long_ev.title]
    assert len(d['closures'][0]['days']) == 38
    titles_active = [e['title'] for e in d['active_events']]
    assert over_ev.title not in titles_active, "ended event shown as active!"
    st = json.loads(STATE.read_text())
    assert 'ada-over' in st['seen'], "ended event must still be marked seen"

    # Run 2: the ANNOUNCEMENT disappears from the source (aged out of the
    # fetch window) — the closure must STAY on the calendar regardless
    src.fetch = lambda: []
    monitor.main([])
    d = dash()
    assert d['active_events'] == []                       # feed: source shows nothing
    assert [c['title'] for c in d['closures']] == [long_ev.title], \
        "long closure fell off the calendar when its announcement aged out!"
    monitor.main([])                                      # ...and stays across runs
    assert len(dash()['closures']) == 1 and len(sent) == 1

    # Registry cap: flood of dated events keeps the nearest-ending 300
    flood = [Event(f'c{i}', 'x', f'Ρύθμιση στις '
             f'{(today + timedelta(days=1 + i % 90)).strftime(fmt)}', f'http://x/{i}')
             for i in range(320)]
    src.fetch = lambda: flood
    monitor.main([])
    st = json.loads(STATE.read_text())
    assert len(st['closures']) == 300, len(st['closures'])

    STATE.unlink(); shutil.rmtree(DOCS)
    print("ALL REGISTRY TESTS PASSED (event-date retention, both directions)")

if __name__ == "__main__":
    run()
