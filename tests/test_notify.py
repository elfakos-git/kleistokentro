"""Offline tests for notify.py formatters (no network, no secrets).
Run with:  python tests/test_notify.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notify import format_event, format_urgent, format_digest, imminence_label

TODAY = "2026-07-08"


def run():
    # --- format_event: plain preferred, canonical fallback -------------
    ev = SimpleNamespace(title="25404 - Προσωρινές κυκλοφοριακές ρυθμίσεις...",
                         plain="Διακοπή κυκλοφορίας στην οδό Ερμού · Τετ 8/7",
                         details="", url="http://x", source="Διαύγεια (Τροχαία)")
    out = format_event(ev)
    assert "οδό Ερμού" in out and "25404" not in out
    ev2 = SimpleNamespace(title="Σκέτος τίτλος", details="λεπτομέρειες",
                          url="http://x", source="πηγή")     # no plain attr
    out2 = format_event(ev2)
    assert "Σκέτος τίτλος" in out2 and "λεπτομέρειες" in out2

    # HTML injection stays escaped
    ev3 = SimpleNamespace(title="<b>x</b>", plain="", details="", url="http://x", source="s")
    assert "<b>x</b>" not in format_event(ev3).replace("🚧 <b>", "")

    # --- imminence labels ----------------------------------------------
    assert imminence_label(["2026-07-08"], TODAY) == "ΣΗΜΕΡΑ"
    assert imminence_label(["2026-07-09"], TODAY) == "ΑΥΡΙΟ"
    assert imminence_label(["2026-07-11"], TODAY) == "σε 3 ημέρες"
    assert imminence_label(["2026-07-06", "2026-07-09"], TODAY) == "ΣΕ ΕΞΕΛΙΞΗ"
    assert imminence_label(["2026-07-01"], TODAY) == ""

    # --- format_urgent: plain carries the dates → no duplicate 📅 ------
    entry = {"title": "25404 - ...", "url": "http://x", "source": "Διαύγεια (Τροχαία)",
             "area": "Βόρεια", "days": ["2026-07-09"],
             "plain": "Διακοπή κυκλοφορίας στην οδό Χ · Πέμ 9/7, 21:00–05:00"}
    u = format_urgent(entry, TODAY)
    assert "ΑΥΡΙΟ" in u and "οδό Χ" in u
    assert "📅" not in u, "plain already carries the dates"
    assert "📍 Βόρεια" in u, "area survives without the date line"

    bare = {**entry, "plain": ""}
    u2 = format_urgent(bare, TODAY)
    assert "📅 09/07" in u2, "no plain → the span line returns"

    # --- format_digest: plain preferred per line, grouping intact -------
    entries = [
        {"title": "Τ1", "plain": "Απλή γραμμή 1", "url": "http://1",
         "area": "Κέντρο", "days": ["2026-07-08"]},
        {"title": "Τ2", "plain": "", "url": "http://2",
         "area": "", "days": ["2026-07-09"]},
    ]
    d = format_digest(entries, TODAY, 7, TODAY)
    assert "Απλή γραμμή 1" in d and "Τ1" not in d
    assert "Τ2" in d                      # fallback to title
    assert "Σήμερα 08/07" in d and "09/07" in d

    empty = format_digest([], TODAY, 7, TODAY)
    assert "Κανένα γνωστό κλείσιμο" in empty

    print("ALL NOTIFY TESTS PASSED (plain wiring, imminence, digest grouping)")


if __name__ == "__main__":
    run()
