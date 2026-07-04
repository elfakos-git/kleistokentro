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

## Why requests go through curl_cffi

astynomia.gr returned 403 to GitHub's servers even with browser headers:
its firewall fingerprints the TLS handshake itself, which plain Python
requests can't disguise. All source fetches therefore go through
`curl_cffi`, which impersonates a real Chrome browser's TLS fingerprint
(see `get()` in `sources/__init__.py`). If curl_cffi isn't installed the
code falls back to plain requests with a printed warning — fine for
quick local checks, but install requirements.txt for real use.

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
   - `python -m sources.kathimerini`  ← worked in production via RSS
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


### Diavgeia (added, then de-noised after production testing)

`sources/diavgeia.py` watches the official transparency portal where every
police traffic-regulation decision must legally be published — usually
before it takes effect. It uses the official OpenData JSON API (no
scraping) and dedups by ΑΔΑ. The first live run proved the API ignores
fancy query syntax and returns unrelated decisions (police procurement),
so precision is now enforced in our own code: a decision is kept ONLY if
its subject contains the traffic stem "κυκλοφορ" AND names central
Athens. Two simple queries are merged for recall.

First-use check: `python -m sources.diavgeia` prints kept decisions;
`python -m sources.diavgeia --all` also prints what was filtered out —
run it once to sanity-check the keyword filter against real data.
Offline tests: `python tests/test_diavgeia.py`.


### Realtime layer: TomTom (replaced Waze after production testing)

Waze's unofficial endpoint returned 403 to GitHub's servers on the first
live run and disallows automated access — wrong foundation for a
low-maintenance system. `sources/tomtom.py` uses TomTom's OFFICIAL
Traffic Incidents API instead: free tier (~2,500 requests/day; the
30-minute schedule uses ~48), Greek-language descriptions, proper terms
of service.

Setup (one-time, ~5 min): create a free account at
https://developer.tomtom.com, copy the API key it gives you, and add it
as a repository secret named TOMTOM_API_KEY. Until then this source
fails with a clear message — if you don't want the realtime layer at
all, just disable the "Realtime fast check" workflow instead (Actions
tab → the workflow → ⋯ menu → Disable workflow).

It keeps road closures (always) and major accidents only, runs on its
own 30-minute workflow (`.github/workflows/realtime.yml`), and both
workflows share one concurrency group so they never race on state.json.
First-use check: `python -m sources.tomtom --all` (needs the key in the
environment — see the module docstring for the Windows command).
Offline tests: `python tests/test_tomtom.py`.



## Subscribers & notification settings (multi-user)

The monitor gathers everything centrally; each subscriber is notified
according to their own settings. Two tiers per user:

- 🚨 **Urgent** — sent the moment an event enters that user's urgency
  window (`urgent_days` before its first day), if it matches their
  areas. Events announced weeks ahead still alert each user when they
  become imminent. Exactly once per user. The message always says how
  soon: ΣΗΜΕΡΑ / ΑΥΡΙΟ / σε Ν ημέρες / ΣΕ ΕΞΕΛΙΞΗ.
- 🗓 **Daily digest** — one summary at the user's chosen Athens hour,
  covering their areas over their lookahead window. Evening digests
  (hour ≥ 18) start from TOMORROW — at night, today is stale news.
- 🚧 Undated announcements notify matching users immediately.

Configure in `subscribers.json` (copy `subscribers.example.json`):

    [
      {"name": "Alex",  "chat_id": "123456789",
       "areas": ["Κέντρο", "Βόρεια"],
       "urgent_days": 2, "digest_hour": 8,  "digest_lookahead_days": 7},
      {"name": "Maria", "chat_id": "987654321",
       "areas": ["Νότια"],
       "urgent_days": 1, "digest_hour": 21, "digest_lookahead_days": 3}
    ]

Field notes: `areas` from {Κέντρο, Βόρεια, Δυτικά, Νότια, Ανατολικά};
empty list = everywhere. Events without a recognized area go to
EVERYONE (a miss is worse than noise). `digest_hour` is Athens time,
null disables the digest. Each new person: they message the bot once,
you read their chat id from getUpdates (see Telegram setup), add an
entry, commit. New subscribers are onboarded silently — no backlog.

**Privacy on a public repo:** chat ids in `subscribers.json` are
publicly visible (harmless without the bot token, but they are
identifiers). To keep them private, put the same JSON into a repo
secret named `SUBSCRIBERS_JSON` instead and pass it in both workflow
files under `env:` — the secret takes priority over the file.

If neither exists, the system falls back to single-user mode
(TELEGRAM_CHAT_ID with default settings) — existing deployments keep
working unchanged. System warnings (source failures, flood guard)
always go to the admin chat (TELEGRAM_CHAT_ID).


### astynomia policy v2 (retuned on production data)

The remarks column proved to be mostly congestion-extent text, so the
bulletin now produces only two kinds of event: (1) remarks containing a
genuine disruption keyword (closure, demonstration, accident, works...)
— always kept; (2) "Πολύ Αυξημένη" OUTSIDE weekday rush windows
(07:00–10:30, 16:30–20:30) or anytime on weekends — congestion that
time-of-day can't explain, notified at most once per road per day.
Rush-hour heavy traffic is suppressed as expected state. Verify level
detection with `python -m sources.astynomia` (prints per-row decisions
with reasons); offline tests: `python tests/test_astynomia.py`.

The dashboard also distinguishes duration: events spanning ≥4 days
(long works) are shown subdued in amber — in the calendar (bottom-left
badge) and as ⏳ tagged cards sorted below short events — so a one-day
marathon closure never drowns under a three-month roadworks project.

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
    python tests/test_tomtom.py     # TomTom parsing + filters

Run these after ANY change to monitor.py or a source module.
