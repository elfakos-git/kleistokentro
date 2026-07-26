"""Near-duplicate alert suppression — offline suite.
Run with:  python tests/test_dedup_alerts.py

Production, 17-18/07: the Metro Line 3 works produced THREE 🚨 alerts
(iefimerida, ΟΑΣΑ, kathimerini) and iefimerida published the same story
twice under two URLs. Suppression rules verified here:
  * urgent tier: a subscriber already alerted about a similar closure
    on overlapping days is marked alerted, not pinged again;
  * different line numbers are DIFFERENT closures (digit guard);
  * immediate tier: a same-story second URL is suppressed both within
    one run and against the last 48h of notifications;
  * suppressed events remain fully visible on the dashboard.
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
STATE, DOCS = Path("t_dup_state.json"), Path("t_dup_docs")
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / "data.json"

D = lambda off: (date.today() + timedelta(days=off)).isoformat()
TMR = f"{date.today() + timedelta(days=1):%d/%m/%Y}"

IEF = f"Κυκλοφοριακές ρυθμίσεις στη Γραμμή 3 του Μετρό από την Κυριακή {TMR}"
OASA = ("Τροποποίηση της λειτουργίας των γραμμών του Δικτύου μας, λόγω των "
        f"εργασιών στη Γραμμή 3 «ΣΥΝΤΑΓΜΑ» του ΜΕΤΡΟ, από την Κυριακή {TMR}")
LINE2 = f"Εργασίες στη Γραμμή 2 του Μετρό στις {TMR}"


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

    ief = Event(id="http://i/1", source="iefimerida", title=IEF, url="http://i/1")
    oas = Event(id="oasa-1", source="ΟΑΣΑ", title=OASA, url="http://o/1")
    ln2 = Event(id="ΑΔΑ-ΛΝ2", source="Διαύγεια (Τροχαία)", title=LINE2,
                url="http://d/1")

    # ---- URGENT tier -------------------------------------------------
    # Seed EMPTY (seeding pre-alerts what it sees), then the story
    # arrives and fires one urgent.
    monitor.SOURCES = {"iefimerida": mk("iefimerida", "iefimerida", [])}
    monitor.main([])
    monitor.SOURCES["iefimerida"].fetch = lambda: [ief]
    sent.clear()
    monitor.main([])
    assert len(urgents()) == 1 and "Γραμμή 3" in urgents()[0], sent

    # OASA arrives with the SAME story → suppressed
    monitor.SOURCES["oasa"] = mk("oasa", "ΟΑΣΑ", [])
    monitor.main([])
    monitor.SOURCES["oasa"].fetch = lambda: [oas]
    sent.clear()
    monitor.main([])
    assert urgents() == [], f"duplicate story must not re-ping: {urgents()}"
    c = state()["closures"]["oasa-1"]
    assert "42" in c["alerted_chats"], "suppression must mark alerted"
    data = json.loads((DOCS / "data.json").read_text())
    assert any(e["id"] == "oasa-1" for e in data["active_events"])
    assert any(p["id"] == "oasa-1" for p in data["closures"])

    # Digit guard: Line 2 is a DIFFERENT closure and must alert
    monitor.SOURCES["diavgeia"] = mk("diavgeia", "Διαύγεια (Τροχαία)", [])
    monitor.main([])
    monitor.SOURCES["diavgeia"].fetch = lambda: [ln2]
    sent.clear()
    monitor.main([])
    assert len(urgents()) == 1 and "Γραμμή 2" in urgents()[0], sent

    # ---- IMMEDIATE tier ----------------------------------------------
    a = Event(id="http://i/a", source="iefimerida",
              title="Πορεία στο κέντρο: κλειστή η Σταδίου και η Πανεπιστημίου",
              url="http://i/a")
    b = Event(id="http://i/b", source="iefimerida",
              title="Κλειστή η Σταδίου και η Πανεπιστημίου λόγω πορείας",
              url="http://i/b")
    monitor.SOURCES = {"iefimerida": mk("iefimerida", "iefimerida", [a, b])}
    sent.clear()
    monitor.main([])
    imm = [t for t in sent if t.startswith("🚧")]
    assert len(imm) == 1, imm
    s = state()
    assert "http://i/a" in s["seen"] and "http://i/b" in s["seen"], \
        "the suppressed twin must be seen, never retried"

    # Cross-run within 48h: a THIRD URL of the same story next run → quiet
    c3 = Event(id="http://i/c", source="iefimerida",
               title="Σταδίου και Πανεπιστημίου κλειστές λόγω πορείας — live",
               url="http://i/c")
    monitor.SOURCES["iefimerida"].fetch = lambda: [a, b, c3]
    sent.clear()
    monitor.main([])
    assert not [t for t in sent if t.startswith("🚧")], sent
    assert "http://i/c" in state()["seen"]

    STATE.unlink()
    shutil.rmtree(DOCS)
    print("ALL DEDUP-ALERT TESTS PASSED (urgent pair, digit guard, "
          "same-run and 48h immediate twins, dashboard untouched)")


if __name__ == "__main__":
    run()
