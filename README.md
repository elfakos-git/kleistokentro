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

## Costs & performance

PUBLIC repo (required for free Pages): Actions minutes are UNLIMITED —
the schedule costs nothing. The optimizations below still matter for
notification latency and for the day you might go private.

PRIVATE repo math (2,000 free min/month, each job billed rounded UP to
a whole minute): before optimization ~54 jobs/day ≈ 1,650 min/month —
dangerously near the cap. After: the realtime job SKIPS entirely (zero
billed seconds) until TOMTOM_API_KEY exists, and its schedule pauses
02:00–06:00 Athens (restore 24/7 in realtime.yml if you want it), so
the worst case is ~46 jobs/day ≈ 1,400 min/month, and only ~180 until
you add the TomTom key.

In-run speed: sources are fetched CONCURRENTLY (the old sequential
loop made the 30s per-source timeouts additive — three hanging sites
meant a 90s run; now the fetch phase is capped by the slowest single
source), checkouts are shallow (fetch-depth: 1 — the state history
grows ~20k commits/year and must never be cloned), and HTML parsing
uses lxml (~10x faster, falls back to html.parser if absent). Typical
full run: well under a minute, and it stays that way as the repo ages.


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


## Admin page (manual curation)

`docs/admin.html` (linked from the dashboard footer as "διαχείριση") lets
you remove events permanently, edit the displayed title, and correct the
area or the closure dates. Changes are written to `docs/overrides.json`:
the dashboard applies them instantly, and the monitor applies them at
every run — a removed event never re-appears and never notifies, and
notifications use the edited title/area/dates.

One-time setup: create a fine-grained personal access token (GitHub →
Settings → Developer settings → Fine-grained tokens) scoped to ONLY this
repository with Contents: Read & write, and paste it once on the admin
page — it is stored only in that browser.

HONEST SECURITY NOTE: this is a static site, so the login form is a
curtain, not a lock (its password hash is public in the HTML, and a weak
password can be cracked from a hash — change it by replacing AUTH_HASH
in admin.html with sha256("user:pass")). The actual protection is the
GitHub token: without it, GitHub rejects every write, no matter who gets
past the login. Never commit the token anywhere.


## Recall instrumentation (v2 — making misses visible)

Every design iteration before this one was driven by visible noise;
missed events generate silence. This version makes the silence speak:

- **Filter telemetry.** Every source counts what it rejects and why
  ("άλλη περιοχή: 4, παλιό άρθρο: 2, ..."). The dashboard's source
  health shows "Κρατήθηκαν kept / fetched" with the reasons on the ⓘ,
  and a run that keeps 0 of ≥10 fetched items prints an over-filtering
  warning in the Actions log and a ⚠ on the dashboard — an eaten source
  is now a fact, not a quiet day.
- **Date-parser smoke detector.** Titles that LOOK dated (contain a
  numeric date or a Greek month name) but yield no extracted days are
  logged verbatim and counted per source (date_misses). The event still
  flows as undated (notifying immediately — a miss degrades to "less
  scheduled", never to silence), and the log line is the parser asking
  for a new pattern.
- **Greek month names.** extract_days now reads "στις 5 Ιουλίου 2026",
  "από 6 έως 9 Ιουλίου", "το Σάββατο 5 και την Κυριακή 6 Σεπτεμβρίου",
  and ordinal/no-year forms — the concrete hole named in the design
  review, closed and tested.

Honest scope note: a WRONGLY extracted date (right pattern, wrong read)
remains internally undetectable — no system can know the truth its only
source misstated. The smoke detector catches "couldn't read"; "misread"
is caught by you via the calendar, and fixed in seconds via the admin
page's date editor, which overrides extraction permanently.

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
