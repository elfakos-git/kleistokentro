"""Athens traffic monitor — orchestrator.

Flow of every run:
  1. Load state.json and the subscriber list.
  2. Fetch each selected source independently; one failure never blocks
     the others. `--only tomtom` runs a subset (the fast 30-min workflow).
  3. Deliver notifications per subscriber; save state + dashboard data.

NOTIFICATION MODEL (two tiers, per subscriber)
  🚨 URGENT — sent to a subscriber the moment an event first sits within
     THEIR urgency window (urgent_days before its first day), if it is in
     THEIR areas. An event announced a month early still alerts each user
     when it becomes imminent for them. Exactly-once per user via the
     closure registry's alerted_chats list.
  🗓 DIGEST — one summary per day per subscriber at THEIR chosen Athens
     hour, covering closures in their areas over their lookahead window.
     Evening digests (hour >= 18) start from TOMORROW: at night, today's
     closures are stale news.
  🚧 Undated announcements can't be scheduled, so they notify matching
     subscribers immediately.

SUBSCRIBERS
  Read from, in priority order: the SUBSCRIBERS_JSON env secret (keeps
  chat ids out of a public repo) → subscribers.json in the repo → a
  single-user fallback (the TELEGRAM_CHAT_ID admin with defaults), so an
  unconfigured deployment behaves like the original single-user system.
  A NEW subscriber is onboarded silently: existing closures are marked
  as already-alerted for them (no backlog blast — the same philosophy
  as per-source seeding). System warnings always go to the admin chat.

DELIVERY GUARANTEE (unchanged in spirit)
  Dated events: per-user alerted flag set ONLY on confirmed send.
  Undated events: marked seen ONLY when every matching subscriber got
  the message; a partial failure retries next run (a rare duplicate for
  some beats a silent miss for others).
"""
import json
import os
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sources import astynomia, diavgeia, enrich, iefimerida, kathimerini, tomtom
import notify

SOURCES = {
    "astynomia": astynomia,
    "diavgeia": diavgeia,
    "iefimerida": iefimerida,
    "kathimerini": kathimerini,  # remove this line if it keeps failing
    "tomtom": tomtom,            # realtime; also runs alone every 30 min
}

BASE = Path(__file__).parent
STATE_FILE = BASE / "state.json"
DASHBOARD_FILE = BASE / "docs" / "data.json"
SUBSCRIBERS_FILE = BASE / "subscribers.json"

MAX_SEEN = 500
MAX_NOTIFICATIONS_PER_RUN = 8    # per subscriber, per run
FAILURE_ALERT_AFTER = 6
MAX_HISTORY = 30
MAX_RUNS = 60
MAX_CLOSURES = 300

SUB_DEFAULTS = {"areas": [], "urgent_days": 2,
                "digest_hour": 8, "digest_lookahead_days": 7}
ATHENS = ZoneInfo("Europe/Athens")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _athens_now() -> datetime:
    """Athens wall clock; kept as a function so tests can patch time."""
    return datetime.now(ATHENS)


def safe_send(text: str, chat_id: str | None = None) -> bool:
    """Send via Telegram; NEVER let a messaging hiccup crash the run."""
    try:
        notify.send(text, chat_id)
        return True
    except Exception:
        print(f"Telegram send failed (chat {chat_id or 'admin'}):",
              file=sys.stderr)
        traceback.print_exc()
        return False


def load_subscribers() -> list[dict]:
    """Priority: SUBSCRIBERS_JSON secret → subscribers.json → admin-only
    fallback. Invalid entries are skipped with a warning, never a crash."""
    raw = os.environ.get("SUBSCRIBERS_JSON", "").strip()
    if not raw and SUBSCRIBERS_FILE.exists():
        raw = SUBSCRIBERS_FILE.read_text(encoding="utf-8")
    subs = []
    if raw:
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("subscribers must be a JSON list")
            for i, entry in enumerate(data):
                if not isinstance(entry, dict) or not str(entry.get("chat_id", "")).strip():
                    print(f"subscribers: skipping invalid entry #{i}",
                          file=sys.stderr)
                    continue
                sub = {**SUB_DEFAULTS, **entry}
                sub["chat_id"] = str(sub["chat_id"]).strip()
                sub["areas"] = [a for a in (sub.get("areas") or [])
                                if isinstance(a, str)]
                subs.append(sub)
        except (ValueError, TypeError) as exc:
            print(f"subscribers config invalid ({exc}) — falling back "
                  f"to admin-only", file=sys.stderr)
            subs = []
    if not subs:
        admin = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if admin:
            subs = [{**SUB_DEFAULTS, "name": "admin", "chat_id": admin}]
    return subs


def area_ok(area: str, sub: dict) -> bool:
    """Untagged events pass every filter: we can't prove they're
    outside a subscriber's areas, and a miss is worse than noise."""
    return not sub["areas"] or not area or area in sub["areas"]


def selected_sources(argv) -> dict:
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
    state.setdefault("seeded", [])
    state.setdefault("source_status", {})
    state.setdefault("active", {})
    state.setdefault("closures", {})       # id -> dated event + alerted_chats
    state.setdefault("known_chats", [])    # subscribers already onboarded
    state.setdefault("digests", {})        # chat_id -> last digest date
    state.setdefault("notifications", [])
    state.setdefault("runs", [])
    if state.pop("initialized", False) and not state["seeded"]:
        state["seeded"] = list(SOURCES)
    state.pop("failures", None)
    for c in state["closures"].values():   # migrate single-user flag
        if c.pop("alerted", False):
            c["alerted_chats"] = list({*c.get("alerted_chats", []),
                                       *state["known_chats"]})
        c.setdefault("alerted_chats", [])
    return state


def onboard_new_subscribers(state: dict, subs: list[dict]) -> None:
    """A chat_id seen for the first time is marked as already-alerted on
    every EXISTING closure: joining must never blast the backlog. Their
    digests still show everything."""
    for sub in subs:
        chat = sub["chat_id"]
        if chat not in state["known_chats"]:
            for c in state["closures"].values():
                if chat not in c["alerted_chats"]:
                    c["alerted_chats"].append(chat)
            state["known_chats"].append(chat)
            print(f"Onboarded subscriber {sub.get('name', chat)} silently")


def save_state(state: dict) -> None:
    for key in ("source_status", "active"):
        state[key] = {n: v for n, v in state[key].items() if n in SOURCES}
    state["seeded"] = [n for n in state["seeded"] if n in SOURCES]
    today = _athens_now().date().isoformat()
    live = {i: c for i, c in state["closures"].items()
            if c.get("days") and max(c["days"]) >= today}
    if len(live) > MAX_CLOSURES:
        keep = sorted(live, key=lambda i: live[i]["days"][0])[:MAX_CLOSURES]
        live = {i: live[i] for i in keep}
    state["closures"] = live
    state["seen"] = state["seen"][-MAX_SEEN:]
    state["notifications"] = state["notifications"][-MAX_HISTORY:]
    state["runs"] = state["runs"][-MAX_RUNS:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def write_dashboard(state: dict) -> None:
    DASHBOARD_FILE.parent.mkdir(exist_ok=True)
    closures_public = [{k: v for k, v in c.items() if k != "alerted_chats"}
                       for c in state["closures"].values()]
    DASHBOARD_FILE.write_text(json.dumps({
        "generated_at": now_iso(),
        "sources": [state["source_status"][n] for n in SOURCES
                    if n in state["source_status"]],
        "active_events": [e for n in SOURCES
                          for e in state["active"].get(n, [])],
        "closures": sorted(closures_public, key=lambda c: c["days"][0]),
        "recent_notifications": list(reversed(state["notifications"])),
        "runs": state["runs"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _record(state, source, title, url):
    state["notifications"].append({"time": now_iso(), "source": source,
                                   "title": title, "url": url})


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    to_run = selected_sources(argv)
    state = load_state()
    subs = load_subscribers()
    onboard_new_subscribers(state, subs)
    seen = set(state["seen"])
    today = _athens_now().date().isoformat()
    pending_undated = []
    sent_count = {s["chat_id"]: 0 for s in subs}   # per-user flood cap

    # ------------------------------------------------------------- fetch
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
                seen.add(e.id)
            days = enrich.extract_days(               # TITLE only; Athens
                e.title, date.fromisoformat(today))   # clock, not server
            if not days and getattr(module, "ASSUME_TODAY", False):
                days = [today]                    # realtime = happening now
            area = enrich.classify_area(f"{e.title} {e.details}", url=e.url)
            entry = {"source": e.source, "title": e.title,
                     "url": e.url, "details": e.details,
                     "area": area, "days": days,
                     "new_this_run": is_new and not first_time}
            if is_new:
                if days:
                    # Dated: delivery moves to the per-user alerted flag;
                    # mark seen now. First sight of a source = everyone
                    # already "alerted" (silent seeding).
                    state["seen"].append(e.id)
                elif first_time:
                    state["seen"].append(e.id)    # seed undated silently
                else:
                    pending_undated.append((e, area))
            if days:
                prev_alerted = state["closures"].get(e.id, {}).get("alerted_chats", [])
                if first_time:
                    prev_alerted = [s["chat_id"] for s in subs]
                state["closures"][e.id] = {
                    "source": e.source, "title": e.title, "url": e.url,
                    "details": e.details, "area": area, "days": days,
                    "alerted_chats": list(prev_alerted),
                }
            if days and max(days) < today:
                continue                          # over → not "active"
            current.append(entry)
        state["active"][name] = current
        state["source_status"][name] = {
            "name": name, "ok": True, "items": len(events),
            "consecutive_failures": 0, "last_success": now_iso(),
        }
        if first_time:
            state["seeded"].append(name)

    # ------------------------------------- undated: immediate, per areas
    flood_skipped = 0
    for e, area in pending_undated:
        targets = [s for s in subs if area_ok(area, s)]
        if not targets:
            state["seen"].append(e.id)
            continue
        results = []
        for s in targets:
            if sent_count[s["chat_id"]] >= MAX_NOTIFICATIONS_PER_RUN:
                results.append(True)              # deliberate flood skip
                flood_skipped += 1
                continue
            text = notify.format_event(e)
            if area:
                text += f"\n\n📍 {area}"
            ok = safe_send(text, s["chat_id"])
            results.append(ok)
            if ok:
                sent_count[s["chat_id"]] += 1
        if all(results):                          # everyone got it (or capped)
            state["seen"].append(e.id)
            _record(state, e.source, e.title, e.url)
            print(f"Notified ({len(targets)} chats): [{e.source}] {e.title}")
        else:
            seen.discard(e.id)                    # retry whole event next run
            print(f"Will retry next run: [{e.source}] {e.title}",
                  file=sys.stderr)
    if flood_skipped:
        safe_send(f"…και {flood_skipped} ακόμη νέα γεγονότα δεν εστάλησαν. "
                  f"Πιθανό πρόβλημα parser — δες τα logs.")

    # ------------------- dated: urgent when entering each USER's window
    for cid, c in state["closures"].items():
        upcoming = [d for d in c["days"] if d >= today]
        if not upcoming:
            continue
        delta = (date.fromisoformat(upcoming[0])
                 - date.fromisoformat(today)).days
        for s in subs:
            chat = s["chat_id"]
            if (chat in c["alerted_chats"] or not area_ok(c["area"], s)
                    or delta > int(s["urgent_days"])
                    or sent_count[chat] >= MAX_NOTIFICATIONS_PER_RUN):
                continue
            if safe_send(notify.format_urgent(c, today), chat):
                c["alerted_chats"].append(chat)   # exactly-once, per user
                sent_count[chat] += 1
                _record(state, c["source"], f"🚨 {c['title']}", c["url"])
                print(f"Urgent → {s.get('name', chat)}: {c['title'][:60]}")

    # --------------------------------- digests: per user, per THEIR hour
    now_ath = _athens_now()
    for s in subs:
        chat, hour = s["chat_id"], s.get("digest_hour")
        if hour is None or now_ath.hour < int(hour):
            continue
        if state["digests"].get(chat) == today:
            continue                              # already digested today
        start = today
        if int(hour) >= 18:                       # evening digest → tomorrow
            start = date.fromordinal(
                date.fromisoformat(today).toordinal() + 1).isoformat()
        entries = [c for c in state["closures"].values()
                   if area_ok(c["area"], s)]
        text = notify.format_digest(entries, start,
                                    int(s["digest_lookahead_days"]), today)
        if safe_send(text, chat):
            state["digests"][chat] = today
            _record(state, "Ενημέρωση",
                    f"🗓 Ημερήσια ενημέρωση ({s.get('name', chat)})", "")
            print(f"Digest → {s.get('name', chat)}")
    state["digests"] = {c: d for c, d in state["digests"].items()
                        if c in {s["chat_id"] for s in subs}}

    state["runs"].append({
        "time": now_iso(),
        "new": len(pending_undated),
        "sources_ok": sum(1 for n in to_run
                          if state["source_status"].get(n, {}).get("ok")),
        "sources_total": len(to_run),
    })
    save_state(state)
    write_dashboard(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
