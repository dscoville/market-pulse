"""Offline tests for the backtest harness and the long-history parsers."""

import math
from datetime import date, timedelta

from market_pulse import backtest, history


def _weekdays(start: date, n: int) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _dataset(closes: list[float], vix: float, cape: float) -> dict:
    dates = _weekdays(date(2000, 1, 3), len(closes))
    months = sorted({d[:7] + "-01" for d in dates} | {"1999-12-01"})
    return {
        "sp500": (dates, closes),
        "vix": (dates, [vix] * len(dates)),
        "cape": (months, [cape] * len(months)),
    }


def _results(data, keys):
    variants = [v for v in backtest.VARIANTS if v.key in keys]
    results, span = backtest.simulate(data, variants=variants, start="2000-01-01")
    return {r.variant.key: r for r in results}, span


def test_parked_at_the_highs_legacy_resends_weekly_new_sends_at_most_once():
    # A steady bull market (no melt-up) with CAPE at 40 for over a year:
    # the situation of summer 2026.
    closes = [100.0 * math.exp(0.0006 * i + 0.01 * math.sin(i / 7.0)) for i in range(900)]
    res, _ = _results(_dataset(closes, vix=15.0, cape=40.0), {"legacy", "new"})
    assert len(res["legacy"].alerts) > 20                      # ~weekly, as seen live
    assert all(a.action == "TRIM" for a in res["legacy"].alerts)
    assert len(res["new"].alerts) <= 1                         # latched after any one


def test_crash_sends_one_buy_per_episode_with_latch():
    up = [100.0 * (1.0004 ** i) for i in range(700)]
    crash = [up[-1] * (0.985 ** k) for k in range(1, 60)]         # ~-60%, grinding
    closes = up + crash + [crash[-1]] * 40
    res, _ = _results(_dataset(closes, vix=45.0, cape=20.0), {"pre_cape", "new"})
    assert [a.action for a in res["new"].alerts] == ["BUY"]
    assert len(res["pre_cape"].alerts) > 1                     # weekly re-sends


def test_summary_and_markdown_render():
    closes = [100.0 * math.exp(0.0006 * i + 0.01 * math.sin(i / 7.0)) for i in range(900)]
    data = _dataset(closes, vix=15.0, cape=40.0)
    res, span = _results(data, {"legacy", "new"})
    results = list(res.values())
    rows = backtest.summarize(results, span, closes)
    md = backtest.render_markdown(results, span, rows, closes)
    assert "Be Greedy backtest" in md and "Follow emails vs hold" in md


def test_follow_the_emails_trim_before_fall_beats_holding():
    sp = [100.0] * 10 + [50.0] * 10
    alerts = [backtest.Alert("d", 5, "TRIM", -70, 100.0)]
    assert backtest.follow_the_emails(sp, 0, alerts) > 1.0


def test_cape_is_point_in_time_previous_month():
    lookup = backtest._monthly_lookup(["2020-01-01", "2020-02-01", "2020-03-01"], [10.0, 20.0, 30.0])
    assert lookup("2020-03-15")[0] == 20.0     # March uses February's value
    assert lookup("2020-01-15")[0] is None      # nothing before January


def test_parse_multpl_cape_table():
    html = (
        '<tr class="odd"><td>Sep 1, 2026</td><td>\n&#x2002;\n39.12\n</td></tr>'
        "<tr><td>Aug 1, 2026</td><td>&#x2002;38.50</td></tr>"
    )
    assert history.parse_multpl_cape_table(html) == (["2026-08-01", "2026-09-01"], [38.5, 39.12])


def test_parse_shiller_cape_skips_zero_rows():
    raw = ("Date,SP500,Dividend,Earnings,Consumer Price Index,Long Interest Rate,"
           "Real Price,Real Dividend,Real Earnings,PE10\n"
           "1881-01-01,6.19,0.27,0.49,9.42,4.0,1,1,1,18.47\n"
           "2026-08-01,7711.3,0,0,0,0,0,0,0,0.0\n")
    assert history.parse_shiller_cape(raw) == (["1881-01-01"], [18.47])


def test_series_round_trip(tmp_path):
    series = (["2020-01-02", "2020-01-03"], [3257.85, 3234.85])
    path = tmp_path / "s.csv"
    history.save_series(str(path), series)
    assert history.load_series(str(path)) == series


def test_is_daily_rejects_coarse_bars():
    assert history.is_daily(_weekdays(date(2000, 1, 3), 60))
    monthly = [f"{2000 + i // 12}-{i % 12 + 1:02d}-01" for i in range(60)]
    assert not history.is_daily(monthly)
