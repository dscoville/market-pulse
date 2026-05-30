"""Offline unit tests for the signal engine. No network required."""

import math

import pytest

from market_pulse.signals import (
    drawdown_from_high,
    evaluate,
    range_position,
    sma,
    wilder_rsi,
)


def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], 5) == 3
    assert sma([1, 2, 3, 4, 5], 2) == 4.5
    assert sma([1, 2], 5) is None


def test_rsi_all_gains_is_100():
    rising = list(range(1, 60))
    assert wilder_rsi(rising, 14) == 100.0


def test_rsi_all_losses_near_zero():
    falling = list(range(60, 1, -1))
    assert wilder_rsi(falling, 14) < 1.0


def test_rsi_bounds_and_known_midrange():
    # Alternating noise around a flat trend should sit near the middle.
    series = []
    price = 100.0
    for i in range(100):
        price += 1 if i % 2 == 0 else -1
        series.append(price)
    rsi = wilder_rsi(series, 14)
    assert 0 <= rsi <= 100
    assert 30 < rsi < 70


def test_drawdown_from_high():
    closes = [100, 110, 120, 90]  # high 120, last 90
    assert drawdown_from_high(closes) == pytest.approx(-25.0)
    flat = [100, 100, 100]
    assert drawdown_from_high(flat) == 0.0


def test_range_position():
    assert range_position([10, 20, 30]) == pytest.approx(1.0)   # at the high
    assert range_position([30, 20, 10]) == pytest.approx(0.0)   # at the low
    assert range_position([10, 30, 20]) == pytest.approx(0.5)   # middle


def test_evaluate_requires_enough_data():
    with pytest.raises(ValueError):
        evaluate([1, 2, 3])


def _flat_then(closes_tail, base=100.0, n=260):
    """Build a long flat-ish history then append a custom recent tail."""
    history = [base + math.sin(i / 5.0) * 0.5 for i in range(n)]
    return history + list(closes_tail)


def test_calm_market_holds_and_does_not_alert():
    closes = [100.0 + math.sin(i / 7.0) * 1.0 for i in range(300)]
    a = evaluate(closes, vix_closes=[15.0])
    assert a.action == "HOLD"
    assert abs(a.score) < 40


def test_crash_triggers_buy():
    # Long uptrend, then a sharp ~30% drawdown into the close.
    up = [100.0 + i * 0.5 for i in range(260)]  # ends ~229
    high = up[-1]
    crash = [high * f for f in (0.95, 0.90, 0.82, 0.75, 0.70)]
    closes = up + crash
    a = evaluate(closes, vix_closes=[42.0])  # VIX spiking with the crash
    assert a.action == "BUY"
    assert a.score >= 60
    assert a.corroborating() >= 2


def test_melt_up_triggers_trim():
    # Steady grind, then a steep parabolic blow-off above trend at the highs.
    base = [100.0 + i * 0.1 for i in range(260)]  # ends ~126
    last = base[-1]
    blowoff = [last * f for f in (1.06, 1.12, 1.18, 1.24, 1.30)]
    closes = base + blowoff
    a = evaluate(closes, vix_closes=[10.0])  # complacent VIX at the top
    assert a.action == "TRIM"
    assert a.score <= -40


def test_score_is_clamped():
    up = [100.0 + i * 0.5 for i in range(260)]
    crash = [up[-1] * f for f in (0.7, 0.6, 0.5, 0.45, 0.4)]
    a = evaluate(up + crash, vix_closes=[80.0])
    assert -100.0 <= a.score <= 100.0
