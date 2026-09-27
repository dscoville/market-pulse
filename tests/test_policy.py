"""Offline tests for the alert rules: threshold, corroboration, latch, cooldown."""

from datetime import datetime, timedelta, timezone

from market_pulse.config import Config
from market_pulse.policy import decide, latched_action, rearm, record_alert
from market_pulse.signals import Assessment, Signal

NOW = datetime(2026, 9, 25, 22, 0, tzinfo=timezone.utc)


def _cfg(**over) -> Config:
    base = dict(
        resend_api_key=None, email_from="x", audience_id=None, email_to=[],
        alert_threshold=60.0, min_corroborating=2, cooldown_days=7,
        rearm_level=30.0, state_file="unused", dry_run=False, force=False,
    )
    base.update(over)
    return Config(**base)


def _assess(score: float) -> Assessment:
    action = "TRIM" if score <= -40 else "BUY" if score >= 40 else "HOLD"
    sign = -1 if score < 0 else 1
    signals = [Signal(k, k, "", sign * 20.0) for k in ("rsi", "trend", "range")]
    return Assessment(score, action, "", "", signals, 100.0, "")


def test_first_extreme_sends():
    ok, _ = decide(_assess(-70), _cfg(), {}, now=NOW)
    assert ok


def test_same_side_stays_quiet_while_extreme_persists():
    state: dict = {}
    record_alert(state, _assess(-70), now=NOW)
    # Weeks later, still rich: cooldown has long expired, but no re-send.
    later = NOW + timedelta(days=30)
    rearm(state, -65, 30)
    ok, reason = decide(_assess(-65), _cfg(), state, now=later)
    assert not ok and "already alerted" in reason


def test_cooling_rearms_then_next_extreme_sends():
    state: dict = {}
    record_alert(state, _assess(-70), now=NOW)
    assert rearm(state, -45, 30) is False      # cooler, but not neutral yet
    assert latched_action(state) == "TRIM"
    assert rearm(state, -25, 30) is True       # back near neutral: re-armed
    assert latched_action(state) is None
    ok, _ = decide(_assess(-66), _cfg(), state, now=NOW + timedelta(days=60))
    assert ok


def test_opposite_side_is_not_blocked_by_latch():
    state: dict = {}
    record_alert(state, _assess(-70), now=NOW)
    ok, _ = decide(_assess(75), _cfg(), state, now=NOW + timedelta(days=40))
    assert ok


def test_cooldown_still_applies():
    state: dict = {}
    record_alert(state, _assess(-70), now=NOW)
    state["latched"] = None
    ok, reason = decide(_assess(-70), _cfg(), state, now=NOW + timedelta(days=2))
    assert not ok and "cooldown" in reason


def test_legacy_state_is_treated_as_latched():
    # state/last_alert.json as written before the latch existed.
    legacy = {"last_alert_at": NOW.isoformat(), "last_alert_score": -70.2,
              "last_alert_action": "TRIM"}
    assert latched_action(legacy) == "TRIM"
    assert rearm(legacy, -62, 30) is True       # migrated to explicit key
    assert legacy["latched"] == "TRIM"
    ok, _ = decide(_assess(-62), _cfg(), legacy, now=NOW + timedelta(days=10))
    assert not ok


def test_below_threshold_and_weak_corroboration_skip():
    assert not decide(_assess(-50), _cfg(), {}, now=NOW)[0]
    lone = Assessment(-70, "TRIM", "", "", [Signal("rsi", "", "", -70.0)], 100.0, "")
    ok, reason = decide(lone, _cfg(), {}, now=NOW)
    assert not ok and "corroborating" in reason
