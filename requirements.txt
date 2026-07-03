"""Offline tests for sources/waze.py using a realistic georss fixture.
Run with:  python tests/test_waze.py
"""
import sys, time
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

now_ms = int(time.time() * 1000)
hour = 3_600_000
IN = {"x": 23.7348, "y": 37.9755}          # Syntagma (x=lon, y=lat!)
OUT = {"x": 22.9444, "y": 40.6401}         # Thessaloniki

FIXTURE = {"alerts": [
    # 1. KEEP: fresh road closure, reliable, in the box
    {"uuid": "w-1", "type": "ROAD_CLOSED", "subtype": "ROAD_CLOSED_EVENT",
     "street": "Λεωφ. Βασιλίσσης Αμαλίας", "city": "Αθήνα",
     "location": IN, "pubMillis": now_ms - hour, "reliability": 8},
    # 2. KEEP: major accident
    {"uuid": "w-2", "type": "ACCIDENT", "subtype": "ACCIDENT_MAJOR",
     "street": "Πατησίων", "city": "Αθήνα",
     "location": IN, "pubMillis": now_ms - 2*hour, "reliability": 7},
    # 3. SKIP: minor accident
    {"uuid": "w-3", "type": "ACCIDENT", "subtype": "ACCIDENT_MINOR",
     "location": IN, "pubMillis": now_ms, "reliability": 9},
    # 4. SKIP: hazard (noise category)
    {"uuid": "w-4", "type": "HAZARD", "subtype": "HAZARD_ON_ROAD_POT_HOLE",
     "location": IN, "pubMillis": now_ms, "reliability": 10},
    # 5. SKIP: reliable closure but outside the box
    {"uuid": "w-5", "type": "ROAD_CLOSED", "subtype": "ROAD_CLOSED_HAZARD",
     "location": OUT, "pubMillis": now_ms, "reliability": 9},
    # 6. SKIP: unconfirmed closure (low reliability)
    {"uuid": "w-6", "type": "ROAD_CLOSED", "subtype": "ROAD_CLOSED_EVENT",
     "location": IN, "pubMillis": now_ms, "reliability": 3},
    # 7. SKIP: stale report (uuid churn guard)
    {"uuid": "w-7", "type": "ROAD_CLOSED", "subtype": "ROAD_CLOSED_CONSTRUCTION",
     "location": IN, "pubMillis": now_ms - 30*hour, "reliability": 9},
    # 8. KEEP: closure with no street name → placeholder title
    {"uuid": "w-8", "type": "ROAD_CLOSED", "subtype": None,
     "location": IN, "pubMillis": now_ms - hour, "reliability": 6},
    # 9. SKIP: junk entries
    {"type": "ROAD_CLOSED", "location": IN, "pubMillis": now_ms,
     "reliability": 9},                     # no uuid
    "garbage",
]}

from sources import waze

def run():
    mock_resp = MagicMock()
    mock_resp.json.return_value = FIXTURE
    mock_resp.raise_for_status.return_value = None

    with patch.object(waze.requests, "get", return_value=mock_resp) as m:
        events = waze.fetch()
        kw = m.call_args.kwargs
        assert kw["params"]["env"] == "row" and kw["params"]["types"] == "alerts"
        assert kw["headers"]["Referer"].startswith("https://www.waze.com")
        assert kw["timeout"] == 30

    ids = [e.id for e in events]
    assert ids == ["w-1", "w-2", "w-8"], ids
    assert events[0].title == "Λεωφ. Βασιλίσσης Αμαλίας, Αθήνα"
    assert "Κλειστός δρόμος" in events[0].details
    assert "Σοβαρό τροχαίο" in events[1].details
    assert events[2].title == "Άγνωστη θέση στο κέντρο"
    assert events[0].url.startswith("https://ul.waze.com/ul?ll=37.9755")

    # Schema drift → loud failure
    mock_resp.json.return_value = {"jams": []}
    with patch.object(waze.requests, "get", return_value=mock_resp):
        try:
            waze.fetch(); raise AssertionError("should have raised")
        except RuntimeError as e:
            assert "endpoint changed" in str(e)
    print("ALL WAZE TESTS PASSED (kept 3/10 fixture alerts)")

if __name__ == "__main__":
    run()
