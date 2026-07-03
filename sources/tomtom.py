"""TomTom Traffic Incidents — real-time layer (official API).

WHY THIS REPLACED WAZE
  Waze's endpoint is unofficial, disallows automated access, and blocks
  GitHub's servers (verified 403 in production). TomTom offers the same
  category of data through an official API with a free tier (~2,500
  requests/day — the 30-minute schedule uses ~48), a real terms of
  service, and no fights.

SETUP (one-time, ~5 minutes)
  1. Create a free account at https://developer.tomtom.com
  2. It gives you an API key on signup (a "Traffic" key works).
  3. Add it in GitHub: Settings → Secrets and variables → Actions →
     New repository secret, name TOMTOM_API_KEY.
  Until the secret exists this source fails with a clear message; if you
  don't want the realtime layer at all, disable the "Realtime fast
  check" workflow in the Actions tab instead (⋯ menu → Disable workflow).

WHAT WE KEEP (mirrors the old Waze policy)
  * Road closures (iconCategory 8) — always.
  * Accidents (iconCategory 1) — only when magnitudeOfDelay >= 3
    (major); fender-benders excluded.
  Everything else (jams, weather, roadworks already announced on
  Diavgeia) is ignored: state or duplication, not new disruptions.

  Identity = TomTom's incident id (stable across polls → exactly-once).
  language=el-GR gives Greek descriptions directly.

DEBUG
  TOMTOM_API_KEY=yourkey python -m sources.tomtom          # kept
  TOMTOM_API_KEY=yourkey python -m sources.tomtom --all    # everything
  (on Windows PowerShell:  $env:TOMTOM_API_KEY="yourkey"; python -m sources.tomtom)
"""
import os
from datetime import datetime, timezone

from . import Event, get

SOURCE = "TomTom (realtime)"
API_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"

# Central Athens bounding box (~Syntagma ± 3-4 km), as minLon,minLat,maxLon,maxLat.
BBOX = "23.690,37.945,23.775,38.005"
ASSUME_TODAY = True   # realtime source: no date in text = happening now

FIELDS = ("{incidents{properties{id,iconCategory,magnitudeOfDelay,"
          "startTime,from,to,events{description}},"
          "geometry{type,coordinates}}}")

CLOSED, ACCIDENT = 8, 1          # TomTom iconCategory codes
MIN_ACCIDENT_MAGNITUDE = 3       # magnitudeOfDelay: 3 = major
LABELS = {CLOSED: "Κλειστός δρόμος", ACCIDENT: "Σοβαρό τροχαίο"}


def _api_key() -> str:
    key = os.environ.get("TOMTOM_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "TOMTOM_API_KEY secret is not set — add it in GitHub "
            "(Settings → Secrets → Actions) or disable the 'Realtime "
            "fast check' workflow. See README, 'Realtime layer'.")
    return key


def _keep(props: dict) -> str | None:
    cat = props.get("iconCategory")
    if cat == CLOSED:
        return LABELS[CLOSED]
    if (cat == ACCIDENT
            and int(props.get("magnitudeOfDelay") or 0) >= MIN_ACCIDENT_MAGNITUDE):
        return LABELS[ACCIDENT]
    return None


def _started(props: dict) -> bool:
    """Skip incidents scheduled for the future — planned closures are
    Diavgeia's job; this layer is for what's happening NOW."""
    raw = props.get("startTime")
    if not raw:
        return True
    try:
        start = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return True
    return start <= datetime.now(timezone.utc)


def _first_point(geometry: dict):
    """First (lat, lon) of a Point or LineString, or None."""
    coords = (geometry or {}).get("coordinates")
    try:
        if isinstance(coords[0], (int, float)):      # Point: [lon, lat]
            return float(coords[1]), float(coords[0])
        return float(coords[0][1]), float(coords[0][0])   # LineString
    except (TypeError, IndexError, ValueError):
        return None


def _to_event(inc: dict, label: str) -> Event | None:
    props = inc.get("properties") or {}
    inc_id = props.get("id")
    if not inc_id:
        return None
    frm, to = (props.get("from") or "").strip(), (props.get("to") or "").strip()
    if frm and to and frm != to:
        title = f"{frm} → {to}"
    else:
        title = frm or to or "Κέντρο Αθήνας"
    descriptions = [e.get("description", "") for e in (props.get("events") or [])
                    if isinstance(e, dict)]
    desc = "; ".join(d for d in descriptions if d)
    point = _first_point(inc.get("geometry"))
    url = (f"https://www.google.com/maps?q={point[0]},{point[1]}"
           if point else "https://www.google.com/maps?q=Athens")
    return Event(
        id=str(inc_id),
        source=SOURCE,
        title=title,
        url=url,
        details=f"{label}" + (f" — {desc}" if desc else ""),
    )


def fetch() -> list[Event]:
    resp = get(API_URL, params={
        "key": _api_key(),
        "bbox": BBOX,
        "fields": FIELDS,
        "language": "el-GR",
        "timeValidityFilter": "present",
    })
    data = resp.json()
    if "incidents" not in data or not isinstance(data["incidents"], list):
        # Fail loudly: a silent zero would look healthy forever.
        raise RuntimeError("tomtom: unexpected response shape "
                           "(no 'incidents' list) — API changed?")
    events = []
    for inc in data["incidents"]:
        if not isinstance(inc, dict):
            continue
        label = _keep(inc.get("properties") or {})
        if label and _started(inc.get("properties") or {}):
            ev = _to_event(inc, label)
            if ev:
                events.append(ev)
    return events


if __name__ == "__main__":  # manual check — see DEBUG in the docstring
    import sys
    resp = get(API_URL, params={"key": _api_key(), "bbox": BBOX,
                                "fields": FIELDS, "language": "el-GR",
                                "timeValidityFilter": "present"})
    raw = resp.json().get("incidents", [])
    print(f"TomTom returned {len(raw)} incident(s) in the central-Athens box\n")
    if "--all" in sys.argv:
        for i in raw:
            p = i.get("properties", {})
            print(f"  cat={p.get('iconCategory')} mag={p.get('magnitudeOfDelay')} "
                  f"{p.get('from') or '?'}")
        print()
    for e in fetch():
        print(f"KEEP  {e.title}\n      {e.details}\n      {e.url}\n")
