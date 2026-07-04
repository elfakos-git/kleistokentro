import json, sys, types
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, '.')
from sources import Event
import notify
notify.send = lambda t, chat_id=None: None
import importlib, monitor
importlib.reload(monitor)
notify.send = lambda t, chat_id=None: None
monitor.STATE_FILE = Path('t_state.json')
monitor.DASHBOARD_FILE = Path('t_docs/data.json')
monitor.SUBSCRIBERS_FILE = Path('t_subs.json')
Path('t_subs.json').write_text('[{"chat_id": "x", "digest_hour": null}]')
Path('t_state.json').write_text('{"seeded": ["s"], "seen": []}')
fmt = "%d/%m/%Y"
today = monitor._athens_now().date()          # ATHENS today, like the system
src = types.ModuleType('s')
src.fetch = lambda: [
    Event('a', 'Διαύγεια (Τροχαία)',
          f'Διακοπή στην Πανεπιστημίου στις {today.strftime(fmt)}', 'http://x/a'),
    Event('b', 'Διαύγεια (Τροχαία)',
          f'Έργα στου Ζωγράφου από {today.strftime(fmt)} έως '
          f'{(today+timedelta(days=30)).strftime(fmt)}', 'http://x/b'),
]
monitor.SOURCES = {'s': src}
monitor.main([])
d = json.loads(Path('t_docs/data.json').read_text())
for key in ('generated_at','sources','active_events','closures',
            'recent_notifications','runs'):
    assert key in d, key
tod = today.isoformat()
today_events = [c for c in d['closures'] if tod in c['days']]
assert len(today_events) == 2, today_events
assert sum(len(c['days']) >= 4 for c in today_events) == 1
print("DATA CONTRACT OK (Athens clock) — ΣΗΜΕΡΑ board, calendar, filters all fed")
import shutil
Path('t_state.json').unlink(); Path('t_subs.json').unlink(); shutil.rmtree('t_docs')
