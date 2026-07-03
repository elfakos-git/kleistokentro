# Athens Traffic Monitor

Checks three sources every 4 hours via GitHub Actions and sends a Telegram
message when a genuinely new traffic disruption for central Athens appears.
Each event is notified exactly once.

## How it decides what is "new"

Every event has a stable identity: the article URL for news sites, a hash of
(road + remark text) for the police bulletin. Identities already recorded in
`state.json` are never notified again. `state.json` is committed back to the
repo after every run, so the git history is a complete audit log of what the
monitor saw and when — if you ever wonder "why didn't I get notified?", look
at the commit history of `state.json` and the Actions logs.

Extra guards on top of dedup:

- News articles older than 3 days are ignored (protects against parser bugs
  flooding you with the archive).
- The police bulletin is ignored entirely if its "Τελευταία Ενημέρωση"
  timestamp is older than 12 hours (the page has been observed to go stale).
- Police notifications trigger on the ΕΠΙΣΗΜΑΝΣΕΙΣ (remarks) column only —
  closures, demonstrations, incidents. The current congestion level is
  included as context, never as a trigger, because congestion is transient
  and would be stale at a 4-hour cadence.
- News articles clearly about other regions (Θεσσαλονίκη, Πάτρα, …) with no
  Athens signal are skipped. Ambiguous titles are kept.
- Each source's FIRST successful run seeds silently — no notification
  storm, no workflow-ordering requirements, and adding a new source
  later never blasts its backlog at you.
- An event is marked as seen ONLY after its Telegram message is
  actually delivered. If Telegram is briefly down, the event is
  retried on the next run instead of being silently lost.
- Max 8 notifications per run; more than that almost certainly means a
  parser broke, so you get one summary message instead of spam.
- If a source fails 6 runs in a row (~1 day) you get one warning message.

## Telegram setup (one-time, ~5 minutes)

1. In Telegram, talk to `@BotFather` → `/newbot` → follow prompts → copy the
   **bot token**.
2. Send any message to your new bot (e.g. "hi") so it can reply to you.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and
   copy the number at `"chat":{"id": ...}` — that is your **chat id**.
4. In the GitHub repo: Settings → Secrets and variables → Actions → add
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## First deployment checklist

1. Push these files to the repo.
2. Locally (or in a Codespace): `pip install -r requirements.txt`, then run
   each parser by hand and compare with the page in your browser:
   - `python -m sources.iefimerida`
   - `python -m sources.kathimerini`  ← may be blocked; see below
   - `python -m sources.astynomia`    ← **must be verified**, see below
3. In GitHub → Actions → "Athens traffic monitor" → **Run workflow** (manual
   trigger). Each source's first run seeds silently and commits `state.json`.
4. Trigger it once more; it should report 0 new events and send nothing.

### Verifying astynomia.py (required)

The exact HTML of the congestion markers could not be confirmed at design
time. Run `python -m sources.astynomia`:

- Roads with remarks print correctly → done.
- Wrong/missing output → open the page in Chrome, right-click a table row →
  Inspect, and adjust the two spots marked `SELECTOR 1` and `SELECTOR 2` in
  `sources/astynomia.py`. The comments there explain what each one does.

### Kathimerini

The site blocked automated access during design. The module tries the
WordPress RSS feed first (`.../feed/`), then the HTML page. If it triggers
the failure alert repeatedly, delete the `"kathimerini": kathimerini,` line
from `SOURCES` in `monitor.py` and move on — iefimerida republishes the same
Traffic Police announcements, so you lose almost nothing.

## If a parser breaks (site redesign)

Symptoms: the ⚠️ consecutive-failure message, or the "…και N ακόμη νέα
γεγονότα" flood-guard message.

1. Run the affected module locally (`python -m sources.<name>`).
2. Compare its output with the page in your browser.
3. Adjust the selectors in that one file. Nothing else needs to change.

## Adding a new source later

1. Copy `sources/iefimerida.py` (simplest example).
2. Make `fetch()` return `Event` objects (`id`, `source`, `title`, `url`,
   optional `details`). Use the URL as `id` when items have URLs.
3. Add one line to `SOURCES` in `monitor.py`.

Dedup, flood protection, failure alerts and Telegram delivery are all
handled centrally — a new source is ~40 lines.

## Costs

Zero. GitHub Actions free tier (~1 minute per run, ~180 minutes/month),
Telegram bots are free, state lives in the repo.


### Diavgeia (added)

`sources/diavgeia.py` watches the official transparency portal where every
police traffic-regulation decision must legally be published — usually
before it takes effect. It uses the official OpenData JSON API (no
scraping), dedups by ΑΔΑ, and — unlike the news sources — keeps a decision
ONLY if its subject names central Athens (the API covers all of Greece, so
strictness beats keep-when-ambiguous here; big events are still caught by
the news sources as a second net).

First-use check: `python -m sources.diavgeia` prints kept decisions;
`python -m sources.diavgeia --all` also prints what was filtered out —
run it once to sanity-check the keyword filter against real data.
Offline tests: `python tests/test_diavgeia.py`.


### Waze (added)

`sources/waze.py` reads the endpoint behind the public Waze Live Map for a
central-Athens bounding box and keeps only road closures (any kind) and
major accidents with community reliability ≥ 6/10 — the real-time layer
for incidents and spontaneous protests. It runs on its OWN 30-minute
workflow (`.github/workflows/waze.yml`, `python monitor.py --only waze`)
because incidents expire too fast for the 4-hour cadence; both workflows
share one concurrency group so they never race on state.json. This works
on the free plan because public repos get unlimited Actions minutes.

CAVEAT: the endpoint is unofficial. If Waze changes or blocks it, you'll
get the consecutive-failure Telegram alert; the documented replacement is
TomTom's official Traffic Incidents API (free tier, requires signing up
for an API key — deliberately not used now to avoid managing a credential).

First-use check: `python -m sources.waze --all` prints every alert in the
box and which ones pass the filter. Tune the box in BOX (bboxfinder.com
helps) and strictness via MIN_RELIABILITY.
Offline tests: `python tests/test_waze.py`.

## Dashboard (GitHub Pages)

Every run also writes `docs/data.json` — a full snapshot of everything the
monitor currently sees (all parsed events, not just new ones), per-source
health, and the recent notification history. `docs/index.html` renders it.

**Enable it (one time):** repo Settings → Pages → Source: "Deploy from a
branch" → Branch: `main`, folder `/docs` → Save. Your dashboard appears at
`https://<username>.github.io/<repo>/` after the next run.

Note: free GitHub Pages requires a **public** repo. Your Telegram secrets
are safe either way (they live in Actions secrets, never in files), but the
dashboard itself will be publicly viewable — it contains only public
traffic info, so that's usually fine.

What the dashboard answers at a glance:
- Big traffic-light answer: red = active events, amber = a source is
  failing, green = all quiet.
- "Active now": everything currently visible on the monitored pages, with
  a NEW badge for items first seen this run.
- "Source health": green/amber/red per source, last successful check,
  items parsed — so a silently dying parser is visible before the
  Telegram failure alert fires.
- "Recent notifications": the last 30 messages sent, with links.

The page refreshes itself every 5 minutes; data updates whenever the
monitor runs.

## Tests

Run the whole offline suite (no network, no secrets needed):

    python tests/test_monitor.py    # orchestration guarantees (8 scenarios)
    python tests/test_diavgeia.py   # Diavgeia parsing + filters
    python tests/test_waze.py       # Waze parsing + filters

Run these after ANY change to monitor.py or a source module.
