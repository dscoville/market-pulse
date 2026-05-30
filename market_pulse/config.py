"""Runtime configuration, loaded from environment variables.

Everything has a sensible default so the engine can run in "report only"
mode with zero setup. Email sending kicks in once a RESEND_API_KEY plus a
destination is provided — either a RESEND_AUDIENCE_ID (the subscriber list,
the way the service runs) or an explicit EMAIL_TO (handy for local testing).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # Email delivery (Resend)
    resend_api_key: str | None
    email_from: str
    audience_id: str | None   # subscriber list — the service's primary path
    email_to: list[str]       # explicit recipients — fallback for testing

    # Alert behaviour
    alert_threshold: float  # absolute composite score required to send an email
    min_corroborating: int  # how many signals must agree before we alert
    cooldown_days: int      # never send more than one alert per this many days
    state_file: str         # where the last-alert timestamp is persisted

    # Flags
    dry_run: bool           # compute + render, but never actually send
    force: bool             # ignore threshold + cooldown (for testing the pipe)

    @classmethod
    def from_env(cls) -> "Config":
        to_raw = os.environ.get("EMAIL_TO", "")
        recipients = [e.strip() for e in to_raw.split(",") if e.strip()]
        return cls(
            resend_api_key=os.environ.get("RESEND_API_KEY") or None,
            # `or` (not get's default) so an empty EMAIL_FROM — which the
            # workflow passes when the secret is unset — still falls back.
            email_from=(
                os.environ.get("EMAIL_FROM") or "Be Greedy <onboarding@resend.dev>"
            ),
            audience_id=os.environ.get("RESEND_AUDIENCE_ID") or None,
            email_to=recipients,
            alert_threshold=_get_float("ALERT_THRESHOLD", 60.0),
            min_corroborating=_get_int("MIN_CORROBORATING", 2),
            cooldown_days=_get_int("COOLDOWN_DAYS", 7),
            state_file=os.environ.get("STATE_FILE", "state/last_alert.json"),
            dry_run=_get_bool("DRY_RUN", False),
            force=_get_bool("FORCE", False),
        )

    @property
    def send_mode(self) -> str | None:
        """How we'll deliver, or None if we can't. Audience wins if both set."""
        if not self.resend_api_key:
            return None
        if self.audience_id:
            return "broadcast"
        if self.email_to:
            return "direct"
        return None

    @property
    def can_send(self) -> bool:
        return self.send_mode is not None
