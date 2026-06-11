"""Offline tests for the valuation signals (CAPE + Buffett Indicator)."""

import math

from market_pulse import data
from market_pulse.signals import evaluate


def _calm_closes():
    # A flat, unremarkable market so the only extreme comes from valuation.
    return [100.0 + math.sin(i / 7.0) for i in range(300)]


# --------------------------------------------------------------------------
# Scoring: expensive valuations push the composite toward TRIM / BE FEARFUL.
# --------------------------------------------------------------------------

def test_expensive_valuation_pushes_toward_fearful():
    calm = evaluate(_calm_closes(), vix_closes=[15.0])
    rich = evaluate(_calm_closes(), vix_closes=[15.0], cape=39, buffett_indicator=235)
    # Adding record-high valuations must move the score meaningfully greedier.
    assert rich.score < calm.score - 30
    keys = {s.key for s in rich.signals}
    assert {"cape", "buffett"} <= keys


def test_cheap_valuation_pushes_toward_greedy():
    cheap = evaluate(_calm_closes(), vix_closes=[15.0], cape=10, buffett_indicator=65)
    base = evaluate(_calm_closes(), vix_closes=[15.0])
    assert cheap.score > base.score  # cheap valuations lean BUY


def test_record_valuations_can_trigger_fearful_with_froth():
    # A frothy, near-highs market PLUS record valuations should read BE FEARFUL.
    base = [100.0 + i * 0.1 for i in range(260)]
    blow = [base[-1] * f for f in (1.05, 1.10, 1.15, 1.20)]
    a = evaluate(base + blow, vix_closes=[11.0], cape=40, buffett_indicator=238)
    assert a.action == "TRIM"
    assert a.corroborating() >= 2


def test_valuation_optional_does_not_break_existing():
    a = evaluate(_calm_closes(), vix_closes=[15.0])  # no valuation passed
    assert {"cape", "buffett"}.isdisjoint({s.key for s in a.signals})


# --------------------------------------------------------------------------
# Pure parsers for the data sources.
# --------------------------------------------------------------------------

def test_parse_multpl_cape():
    html = '<div id="current">Current Shiller PE Ratio: 38.61 <span>+0.1%</span></div>'
    assert data._parse_multpl_cape(html) == 38.61
    assert data._parse_multpl_cape("<html>no value here</html>") is None


def test_parse_fred_latest_skips_gaps():
    csv_text = "observation_date,GDP\n2025-01-01,29800.0\n2025-04-01,.\n"
    # most recent real value (the trailing '.' is a missing observation)
    assert data._parse_fred_latest(csv_text) == 29800.0
    assert data._parse_fred_latest("observation_date,X\n") is None
