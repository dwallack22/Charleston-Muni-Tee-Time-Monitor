from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import List, Dict

import requests


def format_slots(slots: List[Dict]) -> str:
    lines = []
    for s in slots:
        open_slots = s.get("players", 0)
        p_txt = f" ({open_slots} open slots)" if open_slots else ""
        lines.append(f"{s['date']}  {s['time']}{p_txt}\n{s['href']}")
    return "\n\n".join(lines)


def send_pushover(title: str, message: str) -> None:
    user_key = os.getenv(os.getenv("PUSHOVER_USER_KEY_ENV", "PUSHOVER_USER_KEY"), os.getenv("PUSHOVER_USER_KEY", ""))
    app_token = os.getenv(os.getenv("PUSHOVER_APP_TOKEN_ENV", "PUSHOVER_APP_TOKEN"), os.getenv("PUSHOVER_APP_TOKEN", ""))

    # Back-compat: if env var names are provided directly in config, users often export them normally.
    user_key = user_key.strip()
    app_token = app_token.strip()

    if not (user_key and app_token):
        raise RuntimeError("Pushover credentials missing. Set PUSHOVER_USER_KEY and PUSHOVER_APP_TOKEN (or adjust env names).")

    r = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": app_token,
            "user": user_key,
            "title": title,
            "message": message[:1024],
        },
        timeout=20,
    )
    r.raise_for_status()


def send_email(subject: str, body: str, to_addr: str, from_name: str = "TeeTime Monitor") -> None:
    """
    Minimal SMTP sender.

    Required env vars:
      SMTP_HOST, SMTP_PORT (optional; default 587), SMTP_USER, SMTP_PASS, SMTP_FROM

    Example:
      SMTP_HOST=smtp.gmail.com
      SMTP_PORT=587
      SMTP_USER=you@gmail.com
      SMTP_PASS=app_password
      SMTP_FROM=you@gmail.com
    """
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587").strip() or 587)
    user = os.getenv("SMTP_USER", "").strip()
    pw = os.getenv("SMTP_PASS", "").strip()
    from_addr = os.getenv("SMTP_FROM", user).strip()

    if not (host and user and pw and from_addr):
        raise RuntimeError("SMTP env vars missing. Set SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM (and optionally SMTP_PORT).")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=25) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)
