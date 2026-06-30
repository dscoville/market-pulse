"""Offline tests for delivery routing (config) and the unsubscribe footer.

No network: we never call Resend here, only check how the code *decides* to
send and what the rendered email contains.
"""

import math

import pytest

from market_pulse.config import Config
from market_pulse.emailer import UNSUBSCRIBE_TOKEN, EmailError, send_broadcast
from market_pulse import report
from market_pulse.signals import evaluate


# --------------------------------------------------------------------------
# Config: which delivery path do we take, given the environment?
# --------------------------------------------------------------------------

def _clear_email_env(monkeypatch):
    for var in ("RESEND_API_KEY", "RESEND_AUDIENCE_ID", "EMAIL_TO", "EMAIL_FROM"):
        monkeypatch.delenv(var, raising=False)


def test_no_key_cannot_send(monkeypatch):
    _clear_email_env(monkeypatch)
    monkeypatch.setenv("RESEND_AUDIENCE_ID", "aud_123")
    cfg = Config.from_env()
    assert cfg.send_mode is None
    assert cfg.can_send is False


def test_audience_routes_to_broadcast(monkeypatch):
    _clear_email_env(monkeypatch)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_AUDIENCE_ID", "aud_123")
    cfg = Config.from_env()
    assert cfg.send_mode == "broadcast"
    assert cfg.can_send is True


def test_email_to_routes_to_direct(monkeypatch):
    _clear_email_env(monkeypatch)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_TO", "me@example.com, you@example.com")
    cfg = Config.from_env()
    assert cfg.send_mode == "direct"
    assert cfg.email_to == ["me@example.com", "you@example.com"]


def test_empty_email_from_falls_back_to_default(monkeypatch):
    # The workflow passes EMAIL_FROM="" when the secret is unset; the default
    # must still apply, or Resend rejects an empty sender ("domain is invalid").
    _clear_email_env(monkeypatch)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM", "")
    cfg = Config.from_env()
    assert cfg.email_from == "Be Greedy <onboarding@resend.dev>"


def test_audience_wins_when_both_set(monkeypatch):
    _clear_email_env(monkeypatch)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_AUDIENCE_ID", "aud_123")
    monkeypatch.setenv("EMAIL_TO", "me@example.com")
    assert Config.from_env().send_mode == "broadcast"


# --------------------------------------------------------------------------
# Broadcast guards: reject a known-bad sender before hitting the Resend API.
# --------------------------------------------------------------------------

def test_broadcast_rejects_shared_resend_sender():
    # Resend 403s broadcasts from onboarding@resend.dev ("use a verified
    # domain"). Fail fast with an actionable message instead of a buried 403.
    with pytest.raises(EmailError, match="verified domain"):
        send_broadcast(
            "re_test",
            "Be Greedy <onboarding@resend.dev>",
            "aud_123",
            "subject",
            f"html {UNSUBSCRIBE_TOKEN}",
            f"text {UNSUBSCRIBE_TOKEN}",
        )


# --------------------------------------------------------------------------
# Report: the unsubscribe footer only appears when a URL is supplied.
# --------------------------------------------------------------------------

def _crash_assessment():
    up = [100.0 + i * 0.5 for i in range(260)]
    crash = [up[-1] * f for f in (0.95, 0.90, 0.82, 0.75, 0.70)]
    return evaluate(up + crash, vix_closes=[42.0])


def test_unsubscribe_absent_by_default():
    a = _crash_assessment()
    assert "Unsubscribe" not in report.render_text(a)
    assert "Unsubscribe" not in report.render_html(a)


def test_unsubscribe_token_threads_through_for_broadcast():
    a = _crash_assessment()
    text = report.render_text(a, unsubscribe_url=UNSUBSCRIBE_TOKEN)
    html = report.render_html(a, unsubscribe_url=UNSUBSCRIBE_TOKEN)
    # send_broadcast requires the token in both bodies; make sure it's there.
    assert UNSUBSCRIBE_TOKEN in text
    assert UNSUBSCRIBE_TOKEN in html
