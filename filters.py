from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, datetime
from typing import Optional, Set


@dataclass(frozen=True)
class WatchConfig:
    start_date: date
    end_date: date
    days_of_week: Optional[Set[int]] = None  # 0=Mon ... 6=Sun
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    # Minimum open slots required to notify (1..4). Kept generic so this module can be reused.
    min_open_slots: int = 1


def parse_date(s: str) -> date:
    """Parse YYYY-MM-DD."""
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def parse_time(s: str) -> time:
    """Parse HH:MM (24h) or H:MM (24h)."""
    s = s.strip()
    # Allow '9:00' or '09:00'
    return datetime.strptime(s, "%H:%M").time()


def within_watch(cfg: WatchConfig, d: date, t: time, open_slots: int) -> bool:
    if d < cfg.start_date or d > cfg.end_date:
        return False
    if cfg.days_of_week is not None and d.weekday() not in cfg.days_of_week:
        return False
    if cfg.start_time is not None and t < cfg.start_time:
        return False
    if cfg.end_time is not None and t > cfg.end_time:
        return False
    if open_slots and open_slots < cfg.min_open_slots:
        return False
    if (open_slots == 0) and cfg.min_open_slots > 1:
        # Unknown players; treat as potentially valid so we don't miss a slot.
        return True
    return True
