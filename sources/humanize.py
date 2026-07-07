"""Plain-language summaries of bureaucratic traffic-decision titles.

WHY
  Diavgeia subjects are legally precise and humanly unreadable:
    "25403 - Προσωρινές κυκλοφοριακές ρυθμίσεις - Προσωρινή διακοπή της
     κυκλοφορίας των οχημάτων στη δεξιά λωρίδα της οδού Κυψέλης, στο
     ύψος του ο.α.80, περιοχής Δήμου Αθηναίων, στις 05.07.2026, κατά
     τις ώρες 07.00΄ έως 12.00΄, λόγω εκτέλεσης εργασιών ..."
  becomes
    "Διακοπή κυκλοφορίας στην οδό Κυψέλης (δεξιά λωρίδα, ύψος αρ. 80)
     · 5/7, 07:00–12:00 · λόγω εργασιών επισκευής των εξωστών"

DESIGN RULES (this is presentation, so it must be boring and safe)
  * Purely rule-based and deterministic — no models, no network.
  * ADDITIVE: the original title is never replaced anywhere; summarize()
    returns "" whenever it cannot do clearly better, and callers fall
    back to the title. News headlines are already human — they match
    none of the bureaucratic patterns and naturally pass through.
  * Extraction mirrors how a Greek reader parses these subjects: verb
    (τι), street (πού), qualifiers (τμήμα/ύψος/ρεύμα/λωρίδα), dates and
    hours (πότε), reason (γιατί). Anything not found is simply omitted.

USED BY  monitor.py (dashboard + closure registry) and ics_feed.py.
TESTS    python tests/test_humanize.py
"""
import re
from datetime import date

from . import norm_greek

MAX_REASON = 60          # clip the "λόγω ..." clause on a word boundary
SAVINGS_RATIO = 0.8      # a summary must be materially shorter to be worth it

MONTH_NUM = ["", "Ιαν", "Φεβ", "Μαρ", "Απρ", "Μαΐ", "Ιουν",
             "Ιουλ", "Αυγ", "Σεπ", "Οκτ", "Νοε", "Δεκ"]

# --- what --------------------------------------------------------------
_ACTIONS = [                       # (norm-pattern, human label)
    (re.compile(r"διακοπ\w*\s+της\s+κυκλοφορ"), "Διακοπή κυκλοφορίας"),
    (re.compile(r"απαγορευσ\w*\s+(?:της\s+)?(?:στασης|σταθμευσ)"),
     "Απαγόρευση στάσης/στάθμευσης"),
    (re.compile(r"πεζοδρομ"), "Πεζοδρόμηση"),
]
_DEFAULT_ACTION = "Κυκλοφοριακές ρυθμίσεις"

# --- where (matched on the ORIGINAL text so casing/accents survive) ----
# Section FIRST and consumed, or its "οδού Νιρβάνα" would win the
# street match ("από το ύψος της οδού Α έως το ύψος της οδού Β").
SECTION_RE = re.compile(
    r"από\s+το\s+ύψος\s+της\s+οδο[υύ]\s+([^,()]{2,40}?)\s*,?\s*"
    r"[εέ]ως\s+το\s+ύψος\s+της\s+οδο[υύ]\s+([^,()]{2,40}?)(?=,|\s+στ|\s+περιοχ|$)")
HEIGHT_RE = re.compile(r"στο\s+ύψος\s+του\s+ο\.?\s*α\.?\s*(\d+)")
STREET_RE = re.compile(r"οδο[υύ]\s+([^,()]{2,45}?)(?=,|\s+στο\b|\s+στη\b|\s+περιοχ|$)")
AVENUE_RE = re.compile(r"(?:Λεωφ(?:όρου|\.)|Λ\.)\s*([^,()]{2,45}?)(?=,|\s+στο\b|\s+στη\b|\s+περιοχ|$)")
DIRECTION_RE = re.compile(r"(?:στο\s+)?ρεύμα\s+(?:κυκλοφορίας\s+)?προς\s+([^,()]{2,30}?)(?=,|$)")
MUNICIPALITY_RE = re.compile(r"περιοχής?\s+(Δήμ(?:ου|ων)\s+[^,()]{2,60}?)(?=,|$)")

_LANES = [("δεξια λωριδα", "δεξιά λωρίδα"),
          ("αριστερη λωριδα", "αριστερή λωρίδα"),
          ("μεσαια λωριδα", "μεσαία λωρίδα")]

# --- when --------------------------------------------------------------
HOURS_RE = re.compile(
    r"ωρ\w*\s+(\d{1,2})[.:](\d{2})\S{0,3}\s*"
    r"(?:εως|μεχρι|-|–)\s*(?:τις\s+)?(\d{1,2})[.:](\d{2})")

# --- why ---------------------------------------------------------------
REASON_RE = re.compile(r"λόγω\s+(.{4,120}?)(?:\s*[,.]\s*$|[,.;(]|$)")


def _clean(s: str) -> str:
    return " ".join((s or "").split()).strip(" -–—.·")


def _fmt_day(iso: str, ref_year: int) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    out = f"{d}/{m}"
    if y != ref_year:
        out += f"/{y % 100:02d}"
    return out


def _runs(days: list[str]):
    """Group sorted ISO days into consecutive (first, last) runs."""
    runs = []
    for iso in sorted(set(days)):
        d = date.fromisoformat(iso)
        if runs and (d - date.fromisoformat(runs[-1][1])).days == 1:
            runs[-1][1] = iso
        else:
            runs.append([iso, iso])
    return runs


def compact_days(days: list[str], today: date | None = None) -> str:
    """'2026-07-05' → '5/7'; a solid range → '6/7 – 25/9'; up to three
    scattered days listed; more → '16 ημέρες, 7/7 – 31/7'."""
    if not days:
        return ""
    ref = (today or date.today()).year
    runs = _runs(days)
    if len(runs) == 1:
        a, b = runs[0]
        return _fmt_day(a, ref) if a == b else f"{_fmt_day(a, ref)} – {_fmt_day(b, ref)}"
    uniq = sorted(set(days))
    if len(uniq) <= 3:
        return ", ".join(_fmt_day(d, ref) for d in uniq)
    return (f"{len(uniq)} ημέρες, "
            f"{_fmt_day(uniq[0], ref)} – {_fmt_day(uniq[-1], ref)}")


def extract_hours(text: str) -> str:
    m = HOURS_RE.search(norm_greek(text or ""))
    if not m:
        return ""
    h1, m1, h2, m2 = (int(g) for g in m.groups())
    if not (h1 < 24 and h2 < 24 and m1 < 60 and m2 < 60):
        return ""
    return f"{h1:02d}:{m1:02d}–{h2:02d}:{m2:02d}"


def _reason(text: str) -> str:
    m = REASON_RE.search(text)
    if not m:
        return ""
    r = _clean(m.group(1))
    r = re.sub(r"^εκτέλεσης\s+", "", r)          # "εκτέλεσης εργασιών" → "εργασιών"
    if len(r) > MAX_REASON:                       # clip on a word boundary
        r = r[:MAX_REASON].rsplit(" ", 1)[0] + "…"
    # A clause that is (or ends in) a truncated fragment carries no
    # information — Diavgeia clips subjects mid-word ("λόγω εκτέλεσης α").
    if len(r) < 4 or len(r.rstrip("…").split()[-1]) < 3:
        return ""
    return r


def summarize(title: str, days: list[str] | None = None,
              today: date | None = None) -> str:
    """One readable Greek line, or "" when the original is already the
    better text. NEVER a replacement — callers must keep the title."""
    text = _clean(title)
    if not text:
        return ""
    norm = norm_greek(text)

    action = _DEFAULT_ACTION
    for pat, label in _ACTIONS:
        if pat.search(norm):
            action = label
            break

    quals, remaining = [], text
    m = SECTION_RE.search(remaining)
    if m:
        quals.append(f"από {_clean(m.group(1))} έως {_clean(m.group(2))}")
        remaining = remaining.replace(m.group(0), " ")   # consume: its
    m = HEIGHT_RE.search(remaining)                      # 'οδού' must not
    if m:                                                # win the street
        quals.append(f"ύψος αρ. {m.group(1)}")
        remaining = remaining.replace(m.group(0), " ")

    street = avenue = ""
    m = STREET_RE.search(remaining)
    if m:
        street = _clean(m.group(1))
    else:
        m = AVENUE_RE.search(remaining)
        if m:
            avenue = _clean(m.group(1))

    m = DIRECTION_RE.search(remaining)
    if m:
        quals.append(f"προς {_clean(m.group(1))}")
    for stem, label in _LANES:
        if stem in norm:
            quals.append(label)
            break
    muni = ""
    m = MUNICIPALITY_RE.search(text)
    if m:
        muni = _clean(m.group(1))

    reason = _reason(text)

    # Bureaucratese detector: without a concrete WHERE there is nothing
    # to say more plainly — a reason alone ("λόγω αγώνων") can't improve
    # on a news headline. Diavgeia subjects always name a street or a
    # municipality; headlines rarely match these patterns.
    if not (street or avenue or muni):
        return ""

    head = action
    if street:
        head += f" στην οδό {street}"
    elif avenue:
        head += f" στη Λ. {avenue}"
    elif muni:
        head += f" — {muni}"
    if (street or avenue) and muni:
        quals.append(muni)
    if quals:
        head += " (" + ", ".join(quals) + ")"

    parts = [head]
    when = compact_days(days or [], today)
    hours = extract_hours(text)
    if when and hours:
        parts.append(f"{when}, {hours}")
    elif when or hours:
        parts.append(when or hours)
    if reason:
        parts.append(f"λόγω {reason}")

    summary = " · ".join(parts)
    # Only worth showing when it genuinely reads shorter/cleaner.
    if len(summary) >= len(text) * SAVINGS_RATIO:
        return ""
    return summary
