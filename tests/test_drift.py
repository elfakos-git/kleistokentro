"""Parser drift must never fake an extension — offline suite.
Run with:  python tests/test_drift.py

Production, 20-26/07: the kathimerini record "Κυκλοφοριακές ρυθμίσεις
στο Ελληνικό την Πέμπτη για το EKO Rally" is dated by WEEKDAY only, so
the resolver's "nearest Thursday" advanced every week. max(days) grew,
which the extension rule read as a re-issued closure — flagging
`extended` and re-arming the urgent tier, i.e. one false 🚨 per week
forever.

RULE UNDER TEST: an extension re-arms alerts, so it needs evidence. The
title is that evidence — a re-issued decision or an updated article
changes its text. An IDENTICAL title whose dates moved is our own
parser drifting: days still update (the dashboard shows the current
reading) but no flag and no re-alert.

Also covered: a migration that changes a record's days must regenerate
its plain-language line, which embeds those dates.
"""
import json, os, shutil, sys, types
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import Event

sent = []
fake_notify = types.ModuleType("notify")
fake_notify.send = lambda text, chat_id=None: sent.append(text)
fake_notify.format_event = lambda e: f"🚧 {e.title}"
fake_notify.format_urgent = lambda c, today: f"🚨 {c['title']}"
fake_notify.format_digest = lambda entries, s, l, t: "🗓 digest"
sys.modules["notify"] = fake_notify

import importlib, monitor
importlib.reload(monitor)
STATE, DOCS = Path("t_drift_state.json"), Path("t_drift_docs")
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / "data.json"

D = lambda off: (date.today() + timedelta(days=off)).isoformat()
DATED = f"{date.today() + timedelta(days=2):%d.%m.%Y}"
# A genuine extension must keep an IMMINENT first day, otherwise the
# subscriber's urgent window (default 2 days) legitimately declines it —
# so the extension is expressed as a range starting on the same day.
DATED_END = f"{date.today() + timedelta(days=4):%d.%m.%Y}"


def mk(name, label, evts):
    m = types.ModuleType(name)
    m.SOURCE = label
    m.fetch = lambda: list(evts)
    return m


def state():
    return json.loads(STATE.read_text())


def urgents():
    return [t for t in sent if t.startswith("🚨")]


def run():
    os.environ["TELEGRAM_CHAT_ID"] = "42"
    os.environ.pop("SUBSCRIBERS_JSON", None)
    if STATE.exists():
        STATE.unlink()
    if DOCS.exists():
        shutil.rmtree(DOCS)
    sent.clear()

    title = ("Προσωρινή διακοπή της κυκλοφορίας στην οδό Σταδίου, περιοχής "
             f"Δήμου Αθηναίων, στις {DATED}")
    ev = Event(id="ΑΔΑ-DRIFT", source="Διαύγεια (Τροχαία)", title=title,
               url="http://d/1")
    monitor.SOURCES = {"diavgeia": mk("diavgeia", "Διαύγεια (Τροχαία)", [])}
    monitor.main([])                                   # seed empty
    monitor.SOURCES["diavgeia"].fetch = lambda: [ev]
    sent.clear()
    monitor.main([])
    assert len(urgents()) == 1, sent                   # first alert
    rec = state()["closures"]["ΑΔΑ-DRIFT"]
    assert rec["extended"] is False and rec["days"] == [D(2)], rec["days"]

    # --- DRIFT: same title, later day (simulating the weekday resolver
    #     advancing) → days update, but NO flag and NO re-alert ---
    monitor.SOURCES["diavgeia"].fetch = lambda: [ev]
    st = state()
    st["closures"]["ΑΔΑ-DRIFT"]["days"] = [D(-1)]      # pretend it read earlier
    STATE.write_text(json.dumps(st, ensure_ascii=False))
    sent.clear()
    monitor.main([])
    rec = state()["closures"]["ΑΔΑ-DRIFT"]
    assert rec["days"] == [D(2)], f"days must still update: {rec['days']}"
    assert rec["extended"] is False, "identical title → drift, not extension"
    assert urgents() == [], f"drift must never re-alert: {urgents()}"

    # --- GENUINE extension: the title itself changed → flag + re-alert ---
    ev2 = Event(id="ΑΔΑ-DRIFT", source="Διαύγεια (Τροχαία)",
                title=title.replace(f"στις {DATED}",
                                    f"από {DATED} έως {DATED_END}"),
                url="http://d/1")
    monitor.SOURCES["diavgeia"].fetch = lambda: [ev2]
    sent.clear()
    monitor.main([])
    rec = state()["closures"]["ΑΔΑ-DRIFT"]
    assert rec["extended"] is True, "a re-issued title IS an extension"
    assert max(rec["days"]) == D(4), rec["days"]
    assert len(urgents()) == 1, f"genuine extension must re-alert once: {sent}"
    sent.clear()
    monitor.main([])
    assert urgents() == [], "…and only once"

    # --- MIGRATION regenerates the plain line when it changes days ---
    st = state()
    st["closures"]["ΑΔΑ-MIG"] = {
        "id": "ΑΔΑ-MIG", "source": "Διαύγεια (Τροχαία)",
        "title": ("Προσωρινή διακοπή της κυκλοφορίας στην οδό Ερμού, "
                  "περιοχής Δήμου Αθηναίων, στις " + DATED),
        "url": "http://d/2", "details": "", "area": "Κέντρο",
        "days": [D(2), D(300)],            # isolated far-future = noise
        "hours": [], "plain": "STALE — να αντικατασταθεί",
        "first_seen": None, "last_seen": None, "extended": False,
        "alerted_chats": ["42"]}
    STATE.write_text(json.dumps(st, ensure_ascii=False))
    monitor.SOURCES["diavgeia"].fetch = lambda: []
    monitor.main([])
    mig = state()["closures"]["ΑΔΑ-MIG"]
    assert mig["days"] == [D(2)], mig["days"]
    assert "STALE" not in mig["plain"], "stale plain must be regenerated"
    # the regenerated line must describe the SURVIVING day, not the noise
    kept = date.fromisoformat(D(2))
    assert f"{kept.day}/{kept.month}" in mig["plain"], mig["plain"]

    STATE.unlink()
    shutil.rmtree(DOCS)
    print("ALL DRIFT TESTS PASSED (no fake extensions, real ones still "
          "alert once, migrated plain regenerated)")


if __name__ == "__main__":
    run()
