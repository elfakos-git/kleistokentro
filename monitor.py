"""Athens traffic monitor — orchestrator.

Flow of every run:
  1. Load state.json (seen IDs, per-source status, history).
  2. Fetch each selected source independently; one failure never blocks
     the others. `--only waze` runs a subset (the fast 30-min workflow);
     the 4-hour workflow runs everything.
  3. Notify events not yet seen; save state.json + docs/data.json.

DELIVERY GUARANTEE
  An event's ID is persisted as "seen" ONLY after its Telegram message
  is confirmed sent. If Telegram is down, the event is retried on the
  next run instead of being silently lost. (Flood-capped overflow is
  persisted deliberately — skipping it is a decision, not a failure.)

SEEDING (per source, not global)
  A source's FIRST successful fetch seeds its events silently. No
  workflow-ordering requirements, and adding a new source later never
  blasts its backlog at you.

Other rails: MAX_NOTIFICATIONS_PER_RUN caps a run (+1 summary message);
FAILURE_ALERT_AFTER consecutive failures → one alert; all lists capped;
state entries of removed sources are pruned.
"""
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from sources import astynomia, diavgeia, iefimerida, kathimerini, waze
import notify

SOURCES = {
    "astynomia": astynomia,
    "diavgeia": diavgeia,
    "iefimerida": iefimerida,
    "kathimerini": kathimerini,  # remove this line if it keeps failing
    "waze": waze,                # also runs alone on the 30-min workflow
}

BASE = Path(__file__).parent
STATE_FILE = BASE / "state.json"
DASHBOARD_FILE = BASE / "docs" / "data.json"

MAX_SEEN = 500
MAX_NOTIFICATIONS_PER_RUN = 8
FAILURE_ALERT_AFTER = 6
MAX_HISTORY = 30
MAX_RUNS = 60


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_send(text: str) -> bool:
    """Send via Telegram; NEVER let a messaging hiccup crash the run
    (a crash here would lose the whole run's state)."""
    try:
        notify.send(text)
        return True
    except Exception:
        print("Telegram send failed:", file=sys.stderr)
        traceback.print_exc()
        return False


def selected_sources(argv) -> dict:
    """All sources, or the subset named via --only a,b. Unknown names
    fail loudly — a typo in a workflow must not silently run nothing."""
    if "--only" not in argv:
        return SOURCES
    names = argv[argv.index("--only") + 1].split(",")
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        raise SystemExit(f"--only: unknown source(s) {unknown}; "
                         f"available: {list(SOURCES)}")
    return {n: SOURCES[n] for n in names}


def load_state() -> dict:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    state.setdefault("seen", [])
    state.setdefault("seeded", [])          # sources already silently seeded
    state.setdefault("source_status", {})   # name -> last known report
    state.setdefault("active", {})          # name -> events at last run
    state.setdefault("notifications", [])
    state.setdefault("runs", [])
    if state.pop("initialized", False) and not state["seeded"]:
        state["seeded"] = list(SOURCES)     # migrate pre-review state files
    state.pop("failures", None)             # migrated into source_status
    return state


def save_state(state: dict) -> None:
    for key in ("source_status", "active"):   # prune removed sources
        state[key] = {n: v for n, v in state[key].items() if n in SOURCES}
    state["seeded"] = [n for n in state["seeded"] if n in SOURCES]
    state["seen"] = state["seen"][-MAX_SEEN:]
    state["notifications"] = state["notifications"][-MAX_HISTORY:]
    state["runs"] = state["runs"][-MAX_RUNS:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def write_dashboard(state: dict) -> None:
    """Merged snapshot: every source's LAST KNOWN status and events, in
    stable SOURCES order, regardless of which subset just ran."""
    DASHBOARD_FILE.parent.mkdir(exist_ok=True)
    DASHBOARD_FILE.write_text(json.dumps({
        "generated_at": now_iso(),
        "sources": [state["source_status"][n] for n in SOURCES
                    if n in state["source_status"]],
        "active_events": [e for n in SOURCES
                          for e in state["active"].get(n, [])],
        "recent_notifications": list(reversed(state["notifications"])),
        "runs": state["runs"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    to_run = selected_sources(argv)
    state = load_state()
    seen = set(state["seen"])
    pending = []   # new events awaiting confirmed delivery

    for name, module in to_run.items():
        first_time = name not in state["seeded"]
        try:
            events = module.fetch()
        except Exception:
            prev = state["source_status"].get(name, {})
            count = prev.get("consecutive_failures", 0) + 1
            print(f"[{name}] FAILED (consecutive: {count})", file=sys.stderr)
            traceback.print_exc()
            if count == FAILURE_ALERT_AFTER:
                safe_send(f"⚠️ Η πηγή <b>{name}</b> αποτυγχάνει εδώ και "
                          f"{count} συνεχόμενες εκτελέσεις. "
                          f"Δες τα logs στο GitHub Actions.")
            state["source_status"][name] = {
                "name": name, "ok": False, "items": 0,
                "consecutive_failures": count,
                "last_success": prev.get("last_success"),
            }
            continue

        print(f"[{name}] OK — {len(events)} event(s) parsed"
              + (" [seeding]" if first_time else ""))
        current = []
        for e in events:
            is_new = e.id not in seen
            if is_new:
                seen.add(e.id)                    # run-local dedup
                if first_time:
                    state["seen"].append(e.id)    # seed silently
                else:
                    pending.append(e)
            current.append({"source": e.source, "title": e.title,
                            "url": e.url, "details": e.details,
                            "new_this_run": is_new and not first_time})
        state["active"][name] = current
        state["source_status"][name] = {
            "name": name, "ok": True, "items": len(events),
            "consecutive_failures": 0, "last_success": now_iso(),
        }
        if first_time:
            state["seeded"].append(name)

    delivered = 0
    for e in pending:
        if delivered >= MAX_NOTIFICATIONS_PER_RUN:
            state["seen"].append(e.id)            # deliberate flood skip
            continue
        if safe_send(notify.format_event(e)):     # persist ONLY on success
            state["seen"].append(e.id)
            state["notifications"].append({
                "time": now_iso(), "source": e.source,
                "title": e.title, "url": e.url,
            })
            delivered += 1
            print(f"Notified: [{e.source}] {e.title}")
        else:
            print(f"Will retry next run: [{e.source}] {e.title}",
                  file=sys.stderr)
    overflow = len(pending) - MAX_NOTIFICATIONS_PER_RUN
    if overflow > 0:
        safe_send(f"…και {overflow} ακόμη νέα γεγονότα. "
                  f"Πιθανό πρόβλημα parser — δες τα logs.")

    state["runs"].append({
        "time": now_iso(),
        "new": len(pending),
        "sources_ok": sum(1 for n in to_run
                          if state["source_status"].get(n, {}).get("ok")),
        "sources_total": len(to_run),
    })
    save_state(state)
    write_dashboard(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
