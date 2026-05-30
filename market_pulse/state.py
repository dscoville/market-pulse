"""Tiny JSON-file state store used to enforce the 'rare emails' guarantee.

The GitHub Actions workflow commits this file back to the repo after each run,
so the cooldown survives across runs even though the runner is ephemeral.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def load_state(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path: str, state: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def days_since_last_alert(state: dict, now: datetime | None = None) -> float | None:
    ts = state.get("last_alert_at")
    if not ts:
        return None
    last = datetime.fromisoformat(ts)
    now = now or datetime.now(timezone.utc)
    return (now - last).total_seconds() / 86400.0


def cooldown_active(state: dict, cooldown_days: int, now: datetime | None = None) -> bool:
    elapsed = days_since_last_alert(state, now=now)
    return elapsed is not None and elapsed < cooldown_days
