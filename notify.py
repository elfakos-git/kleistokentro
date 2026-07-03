"""Telegram notifications.

Needs two environment variables (set as GitHub Actions secrets):
  TELEGRAM_BOT_TOKEN — from @BotFather
  TELEGRAM_CHAT_ID   — your personal chat id (see README, "Telegram setup")
"""
import html
import os

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


def send(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
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
    lines = [f"🚧 <b>{html.escape(event.title)}</b>"]
    if event.details:
        lines.append(html.escape(event.details))
    lines.append(f'<a href="{html.escape(event.url)}">{html.escape(event.source)}</a>')
    return "\n\n".join(lines)
