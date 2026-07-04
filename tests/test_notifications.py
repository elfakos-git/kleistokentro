"""Multi-subscriber notification model. Uses the REAL formatters
(notify.py), stubbing only the Telegram send. Scenario mirrors the
product spec: User A = Κέντρο+Βόρεια, morning digest 08:00;
User B = Νότια, evening digest 21:00 (covers from tomorrow).
Run: python tests/test_notifications.py
"""
import json, shutil, sys, types
from datetime import date, datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import Event
import notify

sent = []            # (text, chat_id)
fail_chats = set()   # chats whose sends raise (outage simulation)
def fake_send(text, chat_id=None):
    if chat_id in fail_chats:
        raise RuntimeError("telegram down for " + str(chat_id))
    sent.append((text, chat_id))
notify.send = fake_send

import importlib, monitor
importlib.reload(monitor)
notify.send = fake_send            # reload re-imported notify; re-stub
STATE, DOCS, SUBS = Path('t_state.json'), Path('t_docs'), Path('t_subs.json')
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / 'data.json'
monitor.SUBSCRIBERS_FILE = SUBS

TODAY = date(2026, 7, 3)
CLOCK = {"h": 7, "m": 0}
monitor._athens_now = lambda: datetime(TODAY.year, TODAY.month, TODAY.day,
                                       CLOCK["h"], CLOCK["m"])

def msgs_to(chat):
    return [t for t, c in sent if c == chat]

def run():
    if STATE.exists(): STATE.unlink()
    if DOCS.exists(): shutil.rmtree(DOCS)
    SUBS.write_text(json.dumps([
        {"name": "A", "chat_id": "a", "areas": ["Κέντρο", "Βόρεια"],
         "urgent_days": 2, "digest_hour": 8, "digest_lookahead_days": 7},
        {"name": "B", "chat_id": "b", "areas": ["Νότια"],
         "urgent_days": 1, "digest_hour": 21, "digest_lookahead_days": 3},
    ], ensure_ascii=False))
    fmt = "%d/%m/%Y"
    tmrw = (TODAY + timedelta(days=1)).strftime(fmt)
    far1 = (TODAY + timedelta(days=17)).strftime(fmt)
    far2 = (TODAY + timedelta(days=19)).strftime(fmt)

    src = types.ModuleType('s')
    src.fetch = lambda: [
        Event('e1', 'Διαύγεια (Τροχαία)',
              f'Διακοπή κυκλοφορίας στην οδό Σταδίου στις {tmrw}', 'http://x/1'),
        Event('e2', 'Διαύγεια (Τροχαία)',
              f'Ρυθμίσεις στη Γλυφάδα στις {tmrw}', 'http://x/2'),
        Event('e3', 'Διαύγεια (Τροχαία)',
              f'Ρυθμίσεις στην Ομόνοια από {far1} έως {far2}', 'http://x/3'),
    ]
    monitor.SOURCES = {'diavgeia': src}
    STATE.write_text('{"seeded": ["diavgeia"], "seen": []}')

    # 07:00 — urgent tier only. A gets Σταδίου (Κέντρο, tomorrow, ≤2d);
    # B gets Γλυφάδα (Νότια, tomorrow, ≤1d); the far event alerts NOBODY.
    monitor.main([])
    a, b = msgs_to('a'), msgs_to('b')
    assert len(a) == 1 and 'Σταδίου' in a[0] and 'ΑΥΡΙΟ' in a[0], a
    assert len(b) == 1 and 'Γλυφάδα' in b[0] and 'ΑΥΡΙΟ' in b[0], b
    assert not any('Ομόνοια' in t for t, _ in sent)
    assert not any('Γλυφάδα' in t for t in a), "area filter leaked!"

    # Re-run: exactly-once per user
    monitor.main([])
    assert len(sent) == 2, sent

    # 08:30 — A's morning digest fires ONCE; covers Σταδίου (in window),
    # excludes Ομόνοια (day 17 > lookahead 7) and Γλυφάδα (wrong area)
    CLOCK["h"] = 8; CLOCK["m"] = 30
    monitor.main([])
    a = msgs_to('a')
    assert len(a) == 2 and a[1].startswith('🗓'), a
    assert 'Σταδίου' in a[1] and 'Ομόνοια' not in a[1] and 'Γλυφάδα' not in a[1]
    monitor.main([])
    assert len(msgs_to('a')) == 2, "digest repeated same day!"
    assert len(msgs_to('b')) == 1, "B digested before their hour!"

    # 21:30 — B's evening digest: starts from TOMORROW, Νότια only
    CLOCK["h"] = 21; CLOCK["m"] = 30
    monitor.main([])
    b = msgs_to('b')
    assert len(b) == 2 and b[1].startswith('🗓'), b
    assert 'Γλυφάδα' in b[1] and 'Σταδίου' not in b[1]
    assert 'Σήμερα' not in b[1], "evening digest must start from tomorrow"

    # Undated event + partial outage: B's send fails → event NOT marked
    # seen → retried next run; when B recovers, both have it exactly once
    CLOCK["h"] = 22
    # UNTAGGED title (no area keywords) → passes every filter → both users
    src.fetch = lambda: [Event('u1', 'iefimerida',
                               'Έκτακτες κυκλοφοριακές ρυθμίσεις λόγω '
                               'μεγάλου αγώνα δρόμου το Σαββατοκύριακο', 'http://x/u')]
    fail_chats.add('b')
    n_before = len(sent)
    monitor.main([])
    st = json.loads(STATE.read_text())
    assert 'u1' not in st['seen'], "lost undated event on partial outage!"
    fail_chats.clear()
    monitor.main([])
    st = json.loads(STATE.read_text())
    assert 'u1' in st['seen']
    assert sum('Έκτακτες' in t for t, c in sent if c == 'b') == 1

    # New subscriber C: silently onboarded — no backlog blast
    subs = json.loads(SUBS.read_text())
    subs.append({"name": "C", "chat_id": "c", "areas": [],
                 "urgent_days": 5, "digest_hour": None})
    SUBS.write_text(json.dumps(subs, ensure_ascii=False))
    n_before = len(msgs_to('c'))
    monitor.main([])
    assert len(msgs_to('c')) == n_before == 0, "new subscriber got blasted!"
    st = json.loads(STATE.read_text())
    assert all('c' in c['alerted_chats'] for c in st['closures'].values())

    # Dashboard must not leak chat ids
    d = json.loads((DOCS / 'data.json').read_text())
    assert all('alerted_chats' not in c for c in d['closures'])

    STATE.unlink(); SUBS.unlink(); shutil.rmtree(DOCS)
    print("ALL NOTIFICATION TESTS PASSED (A/B scenario, digests, onboarding)")

if __name__ == "__main__":
    run()
