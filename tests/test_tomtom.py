"""Offline tests for sources/tomtom.py.  Run: python tests/test_tomtom.py"""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURE = {"incidents": [
    # 1. KEEP: road closure, LineString geometry
    {"properties": {"id": "t-1", "iconCategory": 8, "magnitudeOfDelay": 4,
                    "startTime": "2026-07-03T06:00:00Z",
                    "from": "Σταδίου", "to": "Πλ. Συντάγματος",
                    "events": [{"description": "Κλειστή οδός"}]},
     "geometry": {"type": "LineString",
                  "coordinates": [[23.7311, 37.9792], [23.735, 37.976]]}},
    # 2. KEEP: major accident, Point geometry
    {"properties": {"id": "t-2", "iconCategory": 1, "magnitudeOfDelay": 3,
                    "from": "Λ. Αλεξάνδρας",
                    "events": [{"description": "Ατύχημα"}]},
     "geometry": {"type": "Point", "coordinates": [23.744, 37.991]}},
    # 3. SKIP: minor accident
    {"properties": {"id": "t-3", "iconCategory": 1, "magnitudeOfDelay": 1},
     "geometry": {"type": "Point", "coordinates": [23.73, 37.98]}},
    # 4. SKIP: traffic jam (state, not disruption)
    {"properties": {"id": "t-4", "iconCategory": 6, "magnitudeOfDelay": 4},
     "geometry": {"type": "Point", "coordinates": [23.73, 37.98]}},
    # 5. SKIP: closure scheduled for the FUTURE (Diavgeia's job)
    {"properties": {"id": "t-5", "iconCategory": 8,
                    "startTime": "2030-01-01T00:00:00Z"},
     "geometry": {"type": "Point", "coordinates": [23.73, 37.98]}},
    # 6. KEEP: closure with no street names / broken geometry
    {"properties": {"id": "t-6", "iconCategory": 8}, "geometry": {}},
    # 7. SKIP: junk
    {"properties": {"iconCategory": 8}},   # no id
    "garbage",
]}

os.environ["TOMTOM_API_KEY"] = "test-key"
from sources import tomtom

def run():
    mock_resp = MagicMock()
    mock_resp.json.return_value = FIXTURE
    with patch.object(tomtom, "get", return_value=mock_resp) as m:
        events = tomtom.fetch()
        params = m.call_args.kwargs["params"]
        assert params["key"] == "test-key"
        assert params["bbox"] == tomtom.BBOX and params["language"] == "el-GR"

    assert [e.id for e in events] == ["t-1", "t-2", "t-6"], [e.id for e in events]
    assert events[0].title == "Σταδίου → Πλ. Συντάγματος"
    assert "Κλειστός δρόμος" in events[0].details
    assert events[0].url == "https://www.google.com/maps?q=37.9792,23.7311"
    assert "Σοβαρό τροχαίο" in events[1].details
    assert events[2].title == "Κέντρο Αθήνας"

    # Missing key → clear, actionable failure
    del os.environ["TOMTOM_API_KEY"]
    try:
        tomtom.fetch(); raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "TOMTOM_API_KEY" in str(e)
    os.environ["TOMTOM_API_KEY"] = "test-key"

    # Schema drift → loud failure
    mock_resp.json.return_value = {"nope": []}
    with patch.object(tomtom, "get", return_value=mock_resp):
        try:
            tomtom.fetch(); raise AssertionError("should have raised")
        except RuntimeError as e:
            assert "API changed" in str(e)
    print("ALL TOMTOM TESTS PASSED (kept 3/8 fixture incidents)")

if __name__ == "__main__":
    run()
