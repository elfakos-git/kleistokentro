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


# Transport: prefer curl_cffi, which impersonates a real Chrome browser's
# TLS fingerprint. Plain python-requests has a distinctive TLS handshake
# that WAFs block with 403 REGARDLESS of headers — this is exactly what
# happened with astynomia.gr on GitHub's runners. Fall back to requests
# if curl_cffi isn't installed (e.g. quick local checks before pip install).
try:
    from curl_cffi import requests as _http
    _IMPERSONATE = {"impersonate": "chrome"}
except ImportError:                       # pragma: no cover
    _http = requests
    _IMPERSONATE = {}
    print("NOTE: curl_cffi not installed — falling back to plain requests; "
          "some sites (astynomia.gr) may return 403. "
          "Run: pip install -r requirements.txt")


def get(url: str, params: dict | None = None,
        extra_headers: dict | None = None):
    """Fetch a URL with sane defaults + browser TLS impersonation.
    Raises on HTTP errors. All source modules should use this."""
    headers = {**HEADERS, **(extra_headers or {})}
    resp = _http.get(url, params=params, headers=headers,
                     timeout=TIMEOUT, **_IMPERSONATE)
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
    "ιωαννιν", "τεμπ", "κρητη", "ροδο", "κερκυρα", "χαλκιδικ", "θηβ",
]


def canonical_url(href: str) -> str:
    """Strip query strings / fragments so rotating tracking parameters
    (?utm_source=...) can never make an old page look like a NEW event.
    Learned from production: kathimerini links carry utm parameters."""
    return href.split("?")[0].split("#")[0]


def norm_greek(text: str) -> str:
    """Lowercase and strip Greek accents for robust keyword matching."""
    table = str.maketrans("άέήίόύώϊΐΰϋ", "αεηιουωιιυυ")
    return text.lower().translate(table)


def mentions_athens(text: str) -> bool:
    return any(t in norm_greek(text) for t in ATHENS_TERMS)


def mentions_other_region(text: str) -> bool:
    return any(r in norm_greek(text) for r in OTHER_REGIONS)
