"""Telegram notifications.

Needs two environment variables (set as GitHub Actions secrets):
  TELEGRAM_BOT_TOKEN — from @BotFather
  TELEGRAM_CHAT_ID   — your personal chat id (see README, "Telegram setup")

PLAIN-LANGUAGE TITLES: every formatter prefers the event's `plain`
line (sources/humanize.py) when one exists and falls back to the
canonical title otherwise. The plain line already carries the dates
and hours in readable Greek, so when it is used the urgent format
drops its own 📅 span line rather than repeat the information.
"""
import html
import os

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


def send(text: str, chat_id: str | None = None) -> None:
    """Send to a specific chat, or to the admin chat (TELEGRAM_CHAT_ID)
    when none is given — system warnings always go to the admin."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    resp = requests.post(
        API.format(token=token),
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    resp.raise_for_status()


def format_event(event) -> str:
    title = getattr(event, "plain", "") or event.title
    lines = [f"🚧 <b>{html.escape(title)}</b>"]
    if event.details:
        lines.append(html.escape(event.details))
    lines.append(f'<a href="{html.escape(event.url)}">{html.escape(event.source)}</a>')
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Two-tier notifications: urgent alerts + daily digest
# ---------------------------------------------------------------------------
from datetime import date as _date

GREEK_DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη",
              "Παρασκευή", "Σάββατο", "Κυριακή"]


def _dm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def imminence_label(days: list[str], today: str) -> str:
    """How soon is this? ALWAYS shown on urgent alerts (product rule)."""
    upcoming = [d for d in days if d >= today]
    if not upcoming:
        return ""
    if min(days) < today <= max(days):
        return "ΣΕ ΕΞΕΛΙΞΗ"
    delta = (_date.fromisoformat(upcoming[0]) - _date.fromisoformat(today)).days
    if delta == 0:
        return "ΣΗΜΕΡΑ"
    if delta == 1:
        return "ΑΥΡΙΟ"
    return f"σε {delta} ημέρες"


def format_urgent(entry: dict, today: str) -> str:
    """🚨 alert for an event entering the urgency window. entry is a
    closure-registry dict: title, url, source, area, days (+ optional
    plain). The plain line embeds dates/hours, so 📅 is only added for
    events without one."""
    when = imminence_label(entry["days"], today)
    title = entry.get("plain") or entry["title"]
    lines = [f"🚨 <b>{html.escape(when)}</b> — {html.escape(title)}"]
    meta = ""
    if not entry.get("plain"):
        span = (_dm(entry["days"][0]) if len(entry["days"]) == 1
                else f"{_dm(entry['days'][0])} – {_dm(entry['days'][-1])}")
        meta = f"📅 {span}"
    if entry.get("area"):
        meta += (" " if meta else "") + f"📍 {entry['area']}"
    if meta:
        lines.append(meta)
    lines.append(f'<a href="{html.escape(entry["url"])}">{html.escape(entry["source"])}</a>')
    return "\n\n".join(lines)


def format_digest(entries: list[dict], start: str, lookahead: int,
                  today: str) -> str:
    """🗓 one digest message: everything in effect or starting within
    [start, start+lookahead], grouped by day. Evening digests pass
    start=tomorrow. Capped well under Telegram's 4096-char limit."""
    horizon = _date.fromisoformat(start).toordinal() + lookahead
    by_day: dict[str, list[dict]] = {}
    for c in entries:
        for d in c["days"]:
            if d >= start and _date.fromisoformat(d).toordinal() <= horizon:
                by_day.setdefault(d, []).append(c)
    if not by_day:
        return (f"🗓 Καλημέρα! Κανένα γνωστό κλείσιμο για τις επόμενες "
                f"{lookahead} ημέρες στις περιοχές σου.")
    out, shown, MAX_LINES = ["🗓 <b>Κλεισίματα των επόμενων ημερών</b>"], 0, 18
    for d in sorted(by_day):
        wd = GREEK_DAYS[_date.fromisoformat(d).weekday()]
        label = "Σήμερα" if d == today else wd
        out.append(f"\n<b>{label} {_dm(d)}</b>")
        for c in by_day[d]:
            if shown >= MAX_LINES:
                break
            area = f" ({c['area']})" if c.get("area") else ""
            line = c.get("plain") or c["title"]
            out.append(f"• <a href=\"{html.escape(c['url'])}\">"
                       f"{html.escape(line[:90])}</a>{html.escape(area)}")
            shown += 1
        if shown >= MAX_LINES:
            out.append("…και ακόμη περισσότερα — δες το dashboard.")
            break
    return "\n".join(out)
