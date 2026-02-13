from __future__ import annotations

import json
import os
from typing import Set


class State:
    def __init__(self, path: str):
        self.path = path
        self.seen: Set[str] = set()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self.seen = set()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self.seen = set(map(str, data))
            elif isinstance(data, dict) and "seen" in data and isinstance(data["seen"], list):
                self.seen = set(map(str, data["seen"]))
            else:
                self.seen = set()
        except Exception:
            self.seen = set()

    def has_seen(self, key: str) -> bool:
        return key in self.seen

    def mark_seen(self, key: str) -> None:
        self.seen.add(key)

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(sorted(self.seen), f, indent=2)
