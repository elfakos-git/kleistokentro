"""Regression: legend rows must never become astynomia events.

The bulletin page renders its colour key as a table row, so the "road"
cell holds a level word ("Ομαλή") while the row text also contains
"Πολύ Αυξημένη" — which, outside rush hours, sailed into the anomaly
branch and produced a production event literally titled "Ομαλή".

Run with:  python tests/test_astynomia_legend.py
"""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sources.astynomia import _classify, LEVELS

ATHENS = ZoneInfo("Europe/Athens")
# Sunday 14:00 — outside every rush window: the exact conditions under
# which the production ghost fired.
NOW = datetime(2026, 7, 5, 14, 0, tzinfo=ATHENS)


def run():
    # 1. THE production ghost: a level word in the road cell, with the
    #    top level detected on the row → must be skipped as a legend.
    for word in LEVELS:
        kind, ev = _classify(word, "Πολύ Αυξημένη", "Πολύ Αυξημένη", NOW)
        assert ev is None and kind.startswith("skip: legend"), (word, kind)

    # 2. Punctuated/accented variants must not slip through either.
    for road in ("Ομαλή:", "ΟΜΑΛΗ", " Πολύ Αυξημένη "):
        kind, ev = _classify(road.strip(), "x", "Πολύ Αυξημένη", NOW)
        assert ev is None and kind.startswith("skip: legend"), (road, kind)

    # 3. A REAL road at Πολύ Αυξημένη off-rush must STILL fire the
    #    anomaly — the guard must not blunt the feature it protects.
    kind, ev = _classify("Λ. Κηφισίας", "", "Πολύ Αυξημένη", NOW)
    assert kind == "anomaly" and ev is not None and ev.title == "Λ. Κηφισίας"

    # 4. A real disruption remark still fires whatever the level.
    kind, ev = _classify("Σταδίου", "Κλειστή λόγω πορείας", "Ομαλή", NOW)
    assert kind == "disruption" and "Κλειστή" in ev.details

    print("ALL ASTYNOMIA LEGEND TESTS PASSED")


if __name__ == "__main__":
    run()
