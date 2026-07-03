"""Waze — real-time incidents in central Athens (unofficial endpoint).

WHY THIS SOURCE
  Accidents and spontaneous closures (protests included) appear on Waze
  within minutes, reported by drivers — long before any announcement.
  This is the "what's happening on the asphalt right now" layer.

HOW IT WORKS
  The same endpoint the public Waze Live Map uses:
    GET https://www.waze.com/live-map/api/georss
        ?top&bottom&left&right (bounding box) &env=row (Europe)
        &types=alerts
  Requires browser-like headers (UA + Referer) or it rejects the call.
  Response: JSON with an "alerts" list; coordinates come as x=longitude,
  y=latitude (note the reversal), timestamps as epoch milliseconds.

  IMPORTANT: this endpoint is UNOFFICIAL. It is stable and widely used,
  but Waze can change or block it at any time without notice. The
  monitor's failure isolation and consecutive-failure alert make that a
  visible, non-fatal event. If it dies permanently, the documented
  fallback is TomTom's official Traffic Incidents API (free tier, needs
  an API key — see README).

WHAT WE KEEP (deliberately conservative — this feed is noisy)
  * ROAD_CLOSED — any subtype: closures are exactly what we monitor for.
  * ACCIDENT with subtype ACCIDENT_MAJOR — minor fender-benders excluded.
  * Both only when community reliability >= MIN_RELIABILITY (scale 0-10),
    so one driver's mistaken tap doesn't page you.
  * HAZARD, POLICE, JAM etc. are ignored: state, not disruption events.

  Identity = the Waze alert uuid. One physical incident occasionally
  gets re-reported under a new uuid → a rare duplicate notification is
  possible; accepted as the cost of zero infrastructure.

CADENCE
  Pointless at 4 hours — incidents expire. Runs on its own 30-minute
  workflow (.github/workflows/waze.yml) via `python monitor.py --only waze`.

DEBUG
  python -m sources.waze            # kept alerts
  python -m sources.waze --all      # everything in the box (for tuning)
"""
from datetime import datetime, timedelta, timezone

from . import Event, TIMEOUT

import requests

SOURCE = "Waze"
API_URL = "https://www.waze.com/live-map/api/georss"

# Central Athens bounding box (~Syntagma ± 3-4 km).
# Tune with https://bboxfinder.com if you want a wider/narrower net.
BOX = {"bottom": 37.945, "top": 38.005, "left": 23.690, "right": 23.775}

MIN_RELIABILITY = 6      # community score 0-10; below this = unconfirmed
MAX_AGE_HOURS = 24       # ignore reports older than this (uuid-churn guard)

KEEP = {                 # (type, subtype-rule) → Greek label
    "ROAD_CLOSED": ("any", "Κλειστός δρόμος"),
    "ACCIDENT": ("ACCIDENT_MAJOR", "Σοβαρό τροχαίο"),
}

# The endpoint rejects non-browser clients: UA + Referer are required.
WAZE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.waze.com/live-map/directions",
}


def _keep(alert: dict) -> str | None:
    """Return the Greek label if this alert passes the filter, else None."""
    rule = KEEP.get(alert.get("type"))
    if rule is None:
        return None
    subtype_rule, label = rule
    if subtype_rule != "any" and alert.get("subtype") != subtype_rule:
        return None
    if int(alert.get("reliability") or 0) < MIN_RELIABILITY:
        return None
    return label


def _in_box(alert: dict) -> bool:
    """The server filters by box, but verify — edge spillover happens.
    Waze quirk: x is LONGITUDE, y is LATITUDE."""
    loc = alert.get("location") or {}
    try:
        lat, lon = float(loc["y"]), float(loc["x"])
    except (KeyError, TypeError, ValueError):
        return False
    return (BOX["bottom"] <= lat <= BOX["top"]
            and BOX["left"] <= lon <= BOX["right"])


def _fresh(alert: dict) -> bool:
    ms = alert.get("pubMillis")
    if not isinstance(ms, (int, float)) or ms <= 0:
        return False   # no timestamp → not trustworthy enough to page you
    reported = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return datetime.now(timezone.utc) - reported < timedelta(hours=MAX_AGE_HOURS)


def _to_event(alert: dict, label: str) -> Event:
    street = (alert.get("street") or "").strip()
    city = (alert.get("city") or "").strip()
    title = ", ".join(p for p in (street, city) if p) or "Άγνωστη θέση στο κέντρο"
    reported = datetime.fromtimestamp(alert["pubMillis"] / 1000,
                                      tz=timezone.utc).astimezone()
    loc = alert["location"]
    return Event(
        id=str(alert["uuid"]),
        source=SOURCE,
        title=title,
        url=f"https://ul.waze.com/ul?ll={loc['y']}%2C{loc['x']}&zoom=16",
        details=(f"{label} — αναφορά οδηγών "
                 f"(αξιοπιστία {alert.get('reliability')}/10, "
                 f"{reported.strftime('%H:%M %d/%m')})"),
    )


def fetch() -> list[Event]:
    resp = requests.get(
        API_URL,
        params={**BOX, "env": "row", "types": "alerts"},
        headers=WAZE_HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if "alerts" not in data or not isinstance(data["alerts"], list):
        # Fail loudly: a silent zero would look healthy forever.
        raise RuntimeError("waze: unexpected response shape "
                           "(no 'alerts' list) — endpoint changed?")
    events = []
    for alert in data["alerts"]:
        if not isinstance(alert, dict) or not alert.get("uuid"):
            continue
        label = _keep(alert)
        if label and _in_box(alert) and _fresh(alert):
            events.append(_to_event(alert, label))
    return events


if __name__ == "__main__":  # manual check: python -m sources.waze [--all]
    import json as _json
    import sys
    resp = requests.get(API_URL, params={**BOX, "env": "row", "types": "alerts"},
                        headers=WAZE_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    raw = resp.json().get("alerts", [])
    print(f"Waze returned {len(raw)} alert(s) in the central-Athens box\n")
    if "--all" in sys.argv:
        for a in raw:
            print(f"  {a.get('type'):<12} {a.get('subtype') or '-':<28} "
                  f"rel={a.get('reliability')} {a.get('street') or '?'}")
        print()
    for e in fetch():
        print(f"KEEP  {e.title}\n      {e.details}\n      {e.url}\n")
