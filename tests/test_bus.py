"""Bus diversions are dashboard-only — offline suite.
Run with:  python tests/test_bus.py

PRODUCT RULE: a rerouted bus line matters to the people who ride it,
not to everyone, so bus notices never message anyone. They stay in the
registry, the calendar and the ICS feed, behind a website toggle.

THE TRAP THIS GUARDS: ΟΑΣΑ publishes bus diversions AND rail closures
(Μετρό/ΗΣΑΠ/Τραμ) on ONE feed, so silencing the source would also mute
a Metro line shutting early — which is exactly what people want to
know. The test is therefore per-EVENT, and rail must keep alerting.

Also covered: headlines datelined to another city ("Ξάνθη: …") are
dropped, with the drop visible in telemetry.
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
fake_notify.format_digest = lambda entries, s, l, t: (
    "🗓 " + " | ".join(c["title"] for c in entries))
sys.modules["notify"] = fake_notify

import importlib, monitor
importlib.reload(monitor)
STATE, DOCS = Path("t_bus_state.json"), Path("t_bus_docs")
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / "data.json"

TOMORROW = f"{date.today() + timedelta(days=1):%d.%m.%Y}"

BUS = ("Μερική προσωρινή τροποποίηση της λεωφορειακής γραμμής 838, λόγω "
       f"εργασιών στην οδό Αγίων Αναργύρων στον Δήμο Πειραιά, στις {TOMORROW}")
RAIL = ("Κυκλοφοριακές ρυθμίσεις στη Γραμμή 3 Μετρό, λόγω εργασιών "
        f"αντικατάστασης σιδηροτροχιών, στις {TOMORROW}")
BUS_UNDATED = ("Προσωρινή τροποποίηση της διαδρομής των λεωφορειακών "
               "γραμμών 750, 806 λόγω εργασιών ασφαλτόστρωσης")
XANTHI = "Ξάνθη: Στις φλόγες νταλίκα στην Εγνατία Οδό – Κυκλοφοριακές ρυθμίσεις"


def mk(name, label, evts):
    m = types.ModuleType(name)
    m.SOURCE = label
    m.fetch = lambda: list(evts)
    return m


def state():
    return json.loads(STATE.read_text())


def dash():
    return json.loads((DOCS / "data.json").read_text())


def run():
    os.environ["TELEGRAM_CHAT_ID"] = "42"
    os.environ.pop("SUBSCRIBERS_JSON", None)
    if STATE.exists():
        STATE.unlink()
    if DOCS.exists():
        shutil.rmtree(DOCS)
    sent.clear()

    bus = Event(id="oasa-bus", source="ΟΑΣΑ", title=BUS, url="http://o/1")
    rail = Event(id="oasa-rail", source="ΟΑΣΑ", title=RAIL, url="http://o/2")
    bus2 = Event(id="oasa-bus2", source="ΟΑΣΑ", title=BUS_UNDATED,
                 url="http://o/3")
    xan = Event(id="kath-xan", source="kathimerini", title=XANTHI,
                url="http://k/1")

    # seed empty, then everything arrives at once
    monitor.SOURCES = {"oasa": mk("oasa", "ΟΑΣΑ", []),
                       "kathimerini": mk("kathimerini", "kathimerini", [])}
    monitor.main([])
    monitor.SOURCES["oasa"].fetch = lambda: [bus, rail, bus2]
    monitor.SOURCES["kathimerini"].fetch = lambda: [xan]
    sent.clear()
    monitor.main([])

    # --- notifications: RAIL yes, BUS never ---
    alerts = [t for t in sent if t.startswith(("🚨", "🚧"))]
    assert len(alerts) == 1, f"exactly the rail closure should alert: {alerts}"
    assert "Γραμμή 3 Μετρό" in alerts[0], alerts[0]
    assert not any("838" in t or "750" in t for t in sent), \
        f"bus diversions must never message anyone: {sent}"

    # --- but they are fully present for the website ---
    d = dash()
    ids = {e["id"] for e in d["active_events"]}
    assert {"oasa-bus", "oasa-bus2", "oasa-rail"} <= ids, ids
    cat = {e["id"]: e["category"] for e in d["active_events"]}
    assert cat["oasa-bus"] == "bus" and cat["oasa-bus2"] == "bus"
    assert cat["oasa-rail"] == "", "rail must NOT be categorised as bus"
    reg = {c["id"]: c for c in d["closures"]}
    assert reg["oasa-bus"]["category"] == "bus", "dated bus stays in registry"

    # --- the undated bus event is seen, so it is never retried ---
    assert "oasa-bus2" in state()["seen"]

    # --- digest excludes bus, keeps rail ---
    digests = [t for t in sent if t.startswith("🗓")]
    if digests:                       # only when the digest hour matched
        assert "838" not in digests[0], digests[0]

    # --- dateline veto: the Xanthi headline is gone + counted ---
    assert "kath-xan" not in ids, "another city's headline must be dropped"
    kath = next(x for x in d["sources"] if x["name"] == "kathimerini")
    assert kath["dropped"].get("άλλη πόλη (τίτλος)") == 1, kath["dropped"]
    oasa = next(x for x in d["sources"] if x["name"] == "oasa")
    assert oasa["dropped"].get("λεωφορεία (χωρίς ειδοποίηση)") == 2, \
        oasa["dropped"]

    # --- a later run must not suddenly alert the bus events ---
    sent.clear()
    monitor.main([])
    assert not any("838" in t or "750" in t for t in sent), sent

    STATE.unlink()
    shutil.rmtree(DOCS)
    print("ALL BUS TESTS PASSED (bus silent everywhere, rail still alerts, "
          "records intact, dateline veto counted)")


if __name__ == "__main__":
    run()
