"""Registry hygiene & precision fixes — offline suite.
Run with:  python tests/test_registry_hygiene.py

Covers the production findings of 18/07:
  1. TomTom uuid rotation: dedup keys on the stable TTR… tail, so a
     model-uuid change can never re-introduce known incidents.
  2. Silent sources never enter the closures registry, and records they
     left behind before this rule are purged on load.
  3. Ghost eviction: a still-fetched event whose title parses to no
     days evicts a registry record claiming only far-future days.
  4. Endpoint-only long ranges (pre-200-day-cap records) re-expand on
     load when the title still describes the same span.
  5. Isolated far-future days are sanitized out of registry records.
  6. Diavgeia other-region veto: "οδό Αθηνών, στην Πάτρα" never leaves
     the pipeline, and the drop is visible in telemetry.
"""
import json, shutil, sys, types
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import Event

sent = []
fake_notify = types.ModuleType("notify")
fake_notify.send = lambda text, chat_id=None: sent.append(text)
fake_notify.format_event = lambda e: f"🚧 {getattr(e, 'plain', '') or e.title}"
fake_notify.format_urgent = lambda c, today: f"🚨 {c['title']}"
fake_notify.format_digest = lambda entries, s, l, t: "🗓 digest"
sys.modules["notify"] = fake_notify

import importlib, monitor
importlib.reload(monitor)
STATE, DOCS = Path("t_hyg_state.json"), Path("t_hyg_docs")
monitor.STATE_FILE = STATE
monitor.DASHBOARD_FILE = DOCS / "data.json"

TODAY = date.today()
D = lambda off: (TODAY + timedelta(days=off)).isoformat()


def mk(name, label, evts):
    m = types.ModuleType(name)
    m.SOURCE = label
    m.fetch = lambda: list(evts)
    return m


def state():
    return json.loads(STATE.read_text())


def run():
    if STATE.exists():
        STATE.unlink()
    if DOCS.exists():
        shutil.rmtree(DOCS)
    sent.clear()

    uuid1 = "358b6ef8-79ba-4e97-a812-e5577805ce49"
    uuid2 = "d877867f-fbae-4ad6-b619-78a2039b3287"
    tt = lambda u: Event(id=f"TTI-{u}-TTR51574092528022000",
                         source="TomTom (realtime)",
                         title="Ιωάννου Βιταλιώτου → Πέτρου Ράλλη",
                         url="https://maps?q=1", details="Κλειστός δρόμος")
    range_title = (f"κατά το χρονικό διάστημα από "
                   f"{TODAY + timedelta(days=5):%d.%m.%Y} έως "
                   f"{TODAY + timedelta(days=160):%d.%m.%Y}")
    dia_ok = Event(id="ΟΚ46ΜΤΛΒ-1", source="Διαύγεια (Τροχαία)",
                   title="Προσωρινή διακοπή της κυκλοφορίας επί της οδού "
                         "Σταδίου, περιοχής Δήμου Αθηναίων",
                   url="http://d/1")
    dia_patra = Event(id="ΠΑ46ΜΤΛΒ-2", source="Διαύγεια (Τροχαία)",
                      title="Κυκλοφοριακές ρυθμίσεις στην οδό Αθηνών, "
                            "στην Πάτρα Ν. Αχαϊας",
                      url="http://d/2")
    ghost_url = "http://k/ghost"
    kat = Event(id=ghost_url, source="kathimerini",
                title="Παλιό άρθρο χωρίς αναγνώσιμη ημερομηνία",
                url=ghost_url)

    monitor.SOURCES = {
        "tomtom": mk("tomtom", "TomTom (realtime)", [tt(uuid1)]),
        "diavgeia": mk("diavgeia", "Διαύγεια (Τροχαία)", [dia_ok, dia_patra]),
        "kathimerini": mk("kathimerini", "kathimerini", [kat]),
    }

    # Pre-seed a state file with the three production pathologies:
    STATE.write_text(json.dumps({
        "seen": [], "seeded": [], "source_status": {}, "active": {},
        "notifications": [], "runs": [],
        "closures": {
            # (2) a TomTom blip that predates the silent-registry rule
            "TTI-old-blip": {"id": "TTI-old-blip",
                             "source": "TomTom (realtime)", "title": "x",
                             "url": "u", "details": "", "area": "",
                             "days": [D(-1)], "alerted_chats": []},
            # (3) a 2027-style ghost on a STILL-FETCHED article
            ghost_url: {"id": ghost_url, "source": "kathimerini",
                        "title": kat.title, "url": ghost_url,
                        "details": "", "area": "", "days": [D(300)],
                        "alerted_chats": []},
            # (4) an endpoint-only long range with a re-expandable title
            "ΕΝΔ46ΜΤΛΒ-3": {"id": "ΕΝΔ46ΜΤΛΒ-3",
                            "source": "Διαύγεια (Τροχαία)",
                            "title": range_title, "url": "http://d/3",
                            "details": "", "area": "",
                            "days": [D(5), D(160)], "alerted_chats": []},
            # (5) the OASA-style isolated far-future day
            "oasa-x": {"id": "oasa-x", "source": "ΟΑΣΑ",
                       "title": "Τροποποίηση γραμμών χωρίς ημερομηνία "
                                "στον τίτλο",
                       "url": "http://o/1", "details": "", "area": "",
                       "days": [D(2), D(200)], "alerted_chats": []},
        }}, ensure_ascii=False))

    monitor.main([])
    s = state()

    # (1) stable-id: only the normalized id is known
    norm_id = "TTI-TTR51574092528022000"
    assert norm_id in s["seen"], "normalized id must be the dedup key"
    assert not any(uuid1 in i for i in s["seen"]), "raw uuid id leaked into seen"

    # (2) registry: TomTom purged on load AND excluded at write
    assert "TTI-old-blip" not in s["closures"], "pre-rule blip must be purged"
    assert not any(c["source"].startswith("TomTom")
                   for c in s["closures"].values()), "silent source in registry"

    # (3) ghost evicted: still fetched, dateless title, far-future record
    assert ghost_url not in s["closures"], "ghost record must be evicted"

    # (4) endpoint-only long range re-expanded from its title
    exp = s["closures"]["ΕΝΔ46ΜΤΛΒ-3"]["days"]
    assert len(exp) > 100 and exp[-1] == D(160), (len(exp), exp[-1] if exp else None)

    # (5) isolated far-future day sanitized away
    assert s["closures"]["oasa-x"]["days"] == [D(2)], s["closures"]["oasa-x"]["days"]

    # (6) diavgeia veto: Patras decision gone everywhere, telemetry shows it
    data = json.loads((DOCS / "data.json").read_text())
    titles = " ".join(e["title"] for e in data["active_events"])
    assert "Πάτρα" not in titles and "Σταδίου" in titles
    assert "ΠΑ46ΜΤΛΒ-2" not in s["seen"], "vetoed events must not be marked seen"
    dia_status = next(x for x in data["sources"] if x["name"] == "diavgeia")
    assert any("veto" in k for k in (dia_status.get("dropped") or {})), \
        dia_status.get("dropped")

    # (1b) uuid ROTATION run: same incident, new uuid → nothing new
    monitor.SOURCES["tomtom"].fetch = lambda: [tt(uuid2)]
    before_seen = len(state()["seen"])
    sent.clear()
    monitor.main([])
    assert len(state()["seen"]) == before_seen, "rotation re-introduced the incident"
    assert sent == [] or all("🚧" not in t and "🚨" not in t for t in sent)

    STATE.unlink()
    shutil.rmtree(DOCS)
    print("ALL REGISTRY-HYGIENE TESTS PASSED (stable ids, purge, eviction, "
          "re-expansion, sanitation, region veto)")


if __name__ == "__main__":
    run()
