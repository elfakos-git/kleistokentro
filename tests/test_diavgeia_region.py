"""Regression: the diavgeia region veto — offline, real module.
Run with:  python tests/test_diavgeia_region.py

Production notified two decisions that only LOOKED Athenian:
  * "Κυκλοφοριακές ρυθμίσεις στην οδό Αθηνών, στην Πάτρα" — a street
    literally NAMED Athinon, in Patras;
  * a Τέμπη oversize-transport permit citing "Μάνδρα Αττικής".
An Athens stem inside another region's decision is not an Athens
decision. The veto lives in diavgeia._to_event with its own telemetry
reason, and monitor.py keeps a second net behind it.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sources import Tally
from sources.diavgeia import _to_event

NOW_MS = int(time.time() * 1000)


def dec(ada, subject):
    return {"ada": ada, "status": "PUBLISHED", "subject": subject,
            "issueDate": NOW_MS}


def run():
    tally = Tally()
    assert _to_event(dec("ΠΑ1", "Κυκλοφοριακές ρυθμίσεις στην οδό Αθηνών, "
                                "στην Πάτρα Ν. Αχαϊας"), tally) is None
    assert _to_event(dec("ΤΕ2", "Κυκλοφοριακές ρυθμίσεις για διέλευση "
                                "οχήματος μέσω Τεμπών και Μάνδρας Αττικής"),
                     tally) is None
    assert dict(tally).get("άλλη περιοχή") == 2, dict(tally)

    ev = _to_event(dec("ΟΚ3", "Προσωρινή διακοπή της κυκλοφορίας επί της "
                              "οδού Σταδίου, περιοχής Δήμου Αθηναίων"), tally)
    assert ev is not None and ev.id == "ΟΚ3"
    ev = _to_event(dec("ΟΚ4", "Διακοπή κυκλοφορίας στη Λεωφ. Κηφισού, στο "
                              "ρεύμα κυκλοφορίας προς Λαμία, Δήμου "
                              "Μεταμόρφωσης"), tally)
    assert ev is not None, "direction 'προς Λαμία' must not trip the veto"

    print("ALL DIAVGEIA REGION-VETO TESTS PASSED")


if __name__ == "__main__":
    run()
