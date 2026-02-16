from __future__ import annotations

import argparse, time
import os
from datetime import datetime, timedelta
import traceback
from urllib.parse import urlparse, parse_qs
import yaml
from dotenv import load_dotenv

from scraper import scrape_slots_for_date
from filters import WatchConfig, parse_date, parse_time, within_watch
from notify import send_email, send_pushover, format_slots
from state import State


def build_watch(cfg: dict) -> WatchConfig:
    min_open = cfg.get("min_open_slots", cfg.get("min_players", 1))
    return WatchConfig(
        start_date=parse_date(cfg["start_date"]),
        end_date=parse_date(cfg["end_date"]),
        days_of_week=set(cfg.get("days_of_week", [])) if cfg.get("days_of_week") else None,
        start_time=parse_time(cfg["start_time"]) if cfg.get("start_time") else None,
        end_time=parse_time(cfg["end_time"]) if cfg.get("end_time") else None,
        min_open_slots=int(min_open),
    )


def daterange(start, end):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def slot_key(s: dict) -> str:
    href = str(s.get("href", "") or "")
    slot_id = ""
    if href:
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            # GRFMIDList is the stable tee-time id on this WebTrac flow.
            # `_csrf_token` rotates frequently and must not be used for de-dupe.
            slot_id = (qs.get("GRFMIDList") or [""])[0].strip()
        except Exception:
            slot_id = ""

    # Include players so an actual state change (e.g., 2 -> 4 open slots) re-alerts once.
    stable_id = slot_id or f"{s['date']}|{s['time']}"
    return f"{stable_id}|players={int(s.get('players', 0))}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="Run once then exit")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    load_dotenv()
    cfg = yaml.safe_load(open(args.config, "r", encoding="utf-8"))

    # Allow config.yaml to specify which env vars hold your Pushover keys
    if cfg.get("notify", {}).get("pushover", {}):
        po = cfg["notify"]["pushover"]
        if po.get("user_key_env"):
            os.environ["PUSHOVER_USER_KEY_ENV"] = str(po["user_key_env"])
        if po.get("app_token_env"):
            os.environ["PUSHOVER_APP_TOKEN_ENV"] = str(po["app_token_env"])

    url = cfg["site"]["url"]
    load_timeout = int(cfg["site"].get("load_timeout_sec", 45))
    interval = int(cfg["site"].get("check_interval_sec", 300))

    # ✅ NEW: search filter controls used by the scraper
    players_to_search = int(cfg["site"].get("number_of_players", 1))
    begin_time_label = str(cfg["site"].get("begin_time", "07:00 am"))

    watch = build_watch(cfg["watch"])
    state = State(cfg["runtime"]["state_file"])
    max_notifies = int(cfg["runtime"].get("max_notifies_per_run", 8))

    if args.debug:
        print(f"[debug] search filters -> number_of_players={players_to_search}, begin_time='{begin_time_label}'")

    def run_once():
        matches = []
        for d in daterange(watch.start_date, watch.end_date):
            if watch.days_of_week and d.weekday() not in watch.days_of_week:
                continue

            try:
                slots = scrape_slots_for_date(
                    url,
                    d.isoformat(),
                    players_to_search=players_to_search,
                    begin_time_label=begin_time_label,
                    load_timeout_sec=load_timeout,
                    debug=args.debug,
                )
            except Exception as e:
                # Extra guard: scraper is expected to return [], but never let this kill the monitor.
                print(f"[error] scrape failed for {d.isoformat()}: {e}")
                if args.debug:
                    traceback.print_exc()
                continue

            if args.debug:
                print(f"[debug] {d.isoformat()} scraped {len(slots)} raw slots")

            for s in slots:
                try:
                    t_24 = datetime.strptime(s.time.upper().replace(" ", ""), "%I:%M%p").time()
                except Exception:
                    try:
                        t_24 = datetime.strptime(s.time, "%H:%M").time()
                    except Exception:
                        continue

                if within_watch(watch, d, t_24, s.players):
                    matches.append({"date": d.isoformat(), "time": s.time, "players": s.players, "href": s.href})

        if args.debug:
            print(f"[debug] total matches before de-dupe vs state: {len(matches)}")

        new_slots = []
        for s in matches:
            key = slot_key(s)
            if not state.has_seen(key):
                state.mark_seen(key)
                new_slots.append(s)

        if not new_slots:
            if args.debug:
                print("[debug] no new matching slots")
            state.save()
            return

        if len(new_slots) > max_notifies:
            new_slots = new_slots[:max_notifies]

        subject = f"{len(new_slots)} tee times found at Charleston Muni"
        body = format_slots(new_slots)

        if cfg.get("notify", {}).get("email", {}).get("enabled"):
            send_email(subject, body, cfg["notify"]["email"]["to"], cfg["notify"]["email"].get("from_name", "TeeTime Monitor"))

        if cfg.get("notify", {}).get("pushover", {}).get("enabled"):
            send_pushover(subject, body)

        if args.debug:
            print("[debug] notified about:")
            print(body)

        state.save()

    if args.once:
        try:
            run_once()
        except Exception as e:
            print(f"[error] run failed: {e}")
            if args.debug:
                traceback.print_exc()
    else:
        while True:
            try:
                run_once()
            except Exception as e:
                print(f"[error] run failed: {e}")
                if args.debug:
                    traceback.print_exc()
            time.sleep(interval)


if __name__ == "__main__":
    main()
