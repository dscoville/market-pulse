"""When to email: the alert rules, kept pure so the backtest replays them exactly.

An alert fires on *entering* an extreme, not on *being in* one. After a
BE FEARFUL email the TRIM side is latched: it stays quiet — however long the
market stays rich — until the score cools back inside ``±rearm_level``. Only
then can the next TRIM go out. BUY works the same way. Without the latch the
7-day cooldown was the only brake, so a market parked at an extreme got the
same email every week.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .config import Config
from .signals import Assessment
from .state import cooldown_active


def latched_action(state: dict) -> str | None:
    """The side we've already alerted on and not yet re-armed, if any.

    State written before the latch existed has no ``latched`` key; treat its
    last alert as still latched so the upgrade can't trigger a repeat email.
    """
    if "latched" in state:
        return state["latched"]
    return state.get("last_alert_action")


def rearm(state: dict, score: float, rearm_level: float) -> bool:
    """Clear the latch once the score has cooled back toward neutral.

    Mutates ``state``; returns True if it changed (so the caller can persist).
    """
    latched = latched_action(state)
    if latched is None:
        return False
    cooled = (
        (latched == "TRIM" and score > -rearm_level)
        or (latched == "BUY" and score < rearm_level)
    )
    if cooled:
        state["latched"] = None
        return True
    if "latched" not in state:  # migrate legacy state to the explicit key
        state["latched"] = latched
        return True
    return False


def decide(a: Assessment, cfg: Config, state: dict,
           now: datetime | None = None) -> tuple[bool, str]:
    """Return (should_send, reason). Call ``rearm`` first."""
    if cfg.force:
        return True, "forced"
    if a.action == "HOLD":
        return False, "market is not out of whack (HOLD)"
    if abs(a.score) < cfg.alert_threshold:
        return False, f"|score| {abs(a.score):.0f} below threshold {cfg.alert_threshold:.0f}"
    if a.corroborating() < cfg.min_corroborating:
        return False, f"only {a.corroborating()} corroborating signals (need {cfg.min_corroborating})"
    if latched_action(state) == a.action:
        return False, (f"already alerted on this {a.action} extreme; waiting for the "
                       f"score to cool inside ±{cfg.rearm_level:.0f} before alerting again")
    if cooldown_active(state, cfg.cooldown_days, now=now):
        return False, f"cooldown active (last alert < {cfg.cooldown_days} days ago)"
    return True, "extreme reached and cooldown clear"


def record_alert(state: dict, a: Assessment, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    state["last_alert_at"] = now.isoformat()
    state["last_alert_score"] = round(a.score, 1)
    state["last_alert_action"] = a.action
    state["latched"] = a.action
