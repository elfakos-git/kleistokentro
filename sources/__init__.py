"""Shared contract for all traffic sources.

Every source module must expose:  fetch() -> list[Event]

To add a new source later:
  1. Copy an existing module in this folder (iefimerida.py is the simplest).
  2. Adapt fetch() to return Event objects.
  3. Add the module to SOURCES in monitor.py.
That's it — dedup, notification and failure handling are handled centrally.
"""
from dataclasses import dataclass
import hashlib

import requests

# A realistic browser User-Agent. Sites treat the default python-requests
# UA as a bot and may block it.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
}

TIMEOUT = 30  # seconds — never let a hung site eat the whole run


@dataclass
class Event:
    id: str        # stable unique identifier (used for dedup, never shown)
    source: str    # human-readable source name, e.g. "iefimerida"
    title: str     # headline / road name
    url: str       # link included in the notification
    details: str = ""  # extra text (e.g. police remarks + congestion level)


def get(url: str) -> requests.Response:
    """Fetch a URL with sane defaults. Raises on HTTP errors."""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


def stable_id(*parts: str) -> str:
    """Deterministic short ID from text parts (for sources without URLs
    per item, like the police bulletin)."""
    joined = "||".join(p.strip().lower() for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Shared Athens-relevance vocabulary (used by news + diavgeia modules)
# ---------------------------------------------------------------------------
ATHENS_TERMS = [
    "αθην", "αττικ", "κεντρο", "συνταγμα", "ομονοια", "συγγρου",
    "κηφισια", "κηφισο", "πατησιων", "σταδιου", "πανεπιστημιου",
    "βασιλισσης σοφιας", "βασ. σοφιας", "αλεξανδρας", "μεσογειων",
    "πειραι", "καλλιθε", "αμπελοκηπ", "ακροπολ", "μοναστηρακ",
]
OTHER_REGIONS = [
    "θεσσαλονικ", "πατρα", "πατρών", "ηρακλει", "λαρισ", "βολο",
    "ιωαννιν", "τεμπ", "κρητη", "ροδο", "κερκυρα", "χαλκιδικ",
]


def norm_greek(text: str) -> str:
    """Lowercase and strip Greek accents for robust keyword matching."""
    table = str.maketrans("άέήίόύώϊΐΰϋ", "αεηιουωιιυυ")
    return text.lower().translate(table)


def mentions_athens(text: str) -> bool:
    return any(t in norm_greek(text) for t in ATHENS_TERMS)


def mentions_other_region(text: str) -> bool:
    return any(r in norm_greek(text) for r in OTHER_REGIONS)
