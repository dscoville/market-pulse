"""Replay Be Greedy over decades of history: how often would it have emailed,
and what did the market do next?

    python -m market_pulse.backtest                      # fetch history, run, print
    python -m market_pulse.backtest --save-data hist/    # ...and cache the data
    python -m market_pulse.backtest --data hist/         # re-run offline from the cache
    python -m market_pulse.backtest --markdown out.md    # also write a Markdown report

Each trading day since 1990 (when the VIX begins) is scored with the real
engine (``signals.evaluate``) on the trailing two years of closes — the same
window the daily run fetches — and fed through the real alert rules
(``policy.decide``). Several variants run side by side so the old engine, the
new one and a few alternatives can be compared on identical data.

Point-in-time care: the VIX is that day's close, and CAPE is the *previous*
month's value, so no variant sees data it wouldn't have had. Returns are S&P
500 price only (no dividends), and the "follow the emails" portfolio earns
nothing on cash; the two omissions roughly offset.
"""

from __future__ import annotations

import argparse
import bisect
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import history
from .config import Config
from .policy import decide, rearm, record_alert
from .signals import (
    _CAPE_CURVE,
    Assessment,
    Signal,
    _classify,
    _interp,
    evaluate,
)

WINDOW = 504                      # ~2 years of trading days, like the live fetch
HORIZONS = {"3m": 63, "6m": 126, "12m": 252, "24m": 504}
TRIM_FRACTION = 0.10              # "consider taking some off the top"
PERCENTILE_MONTHS = 240           # 20-year lookback for the percentile variant


# --------------------------------------------------------------------------
# Variants
# --------------------------------------------------------------------------

@dataclass
class Variant:
    key: str
    name: str
    valuation: str           # "none" | "legacy" | "tilt" | "percentile"
    latch: bool
    rearm_level: float = 30.0
    threshold: float = 60.0
    cooldown_days: int = 7
    trim_threshold: float | None = None   # stricter bar for TRIM only, if set


VARIANTS = [
    Variant("legacy", "Old engine (CAPE full weight, weekly re-send) — what has been emailing",
            valuation="legacy", latch=False),
    Variant("pre_cape", "Pre-June engine (no CAPE, weekly re-send)",
            valuation="none", latch=False),
    Variant("new", "NEW default: CAPE tilt ≤15 pts, market-only corroboration, latch (re-arm ±30)",
            valuation="tilt", latch=True, rearm_level=30.0),
    Variant("new_rearm20", "New, stricter re-arm (±20)",
            valuation="tilt", latch=True, rearm_level=20.0),
    Variant("new_rearm40", "New, looser re-arm (±40)",
            valuation="tilt", latch=True, rearm_level=40.0),
    Variant("new_trim75", "New, but BE FEARFUL needs ≤ -75 (BE GREEDY still ≥ 60)",
            valuation="tilt", latch=True, rearm_level=30.0, trim_threshold=75.0),
    Variant("percentile", "Alt: CAPE vs its own 20-yr percentile (full weight) + latch",
            valuation="percentile", latch=True, rearm_level=30.0),
    Variant("no_cape_latch", "Alt: no CAPE at all + latch",
            valuation="none", latch=True, rearm_level=30.0),
]


def _percentile_score(cape: float, past: list[float]) -> float:
    """Where today's CAPE sits in its trailing range, mapped to ±40 points."""
    if not past:
        return 0.0
    below = sum(1 for v in past if v < cape)
    pct = below / len(past)
    return (0.5 - pct) * 80.0


def _assess(variant: Variant, closes: list[float], vix: float | None,
            cape: float | None, cape_past: list[float], as_of: str) -> Assessment:
    vix_list = [vix] if vix is not None else None
    if variant.valuation == "tilt":
        return evaluate(closes, vix_closes=vix_list, as_of=as_of, cape=cape)
    base = evaluate(closes, vix_closes=vix_list, as_of=as_of)
    if variant.valuation == "none" or cape is None:
        return base
    if variant.valuation == "legacy":
        # Reproduce the June 2026 engine: full-weight curve, and it counted
        # as a corroborating signal like any market signal.
        extra = Signal("cape", "CAPE (legacy)", f"{cape:.0f}", _interp(cape, _CAPE_CURVE), kind="market")
    else:
        extra = Signal("cape", "CAPE percentile", f"{cape:.0f}",
                       _percentile_score(cape, cape_past), kind="valuation")
    signals = base.signals + [extra]
    score = max(-100.0, min(100.0, sum(s.score for s in signals)))
    action, stance, headline = _classify(score)
    return Assessment(score, action, stance, headline, signals, base.price, as_of)


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------

@dataclass
class Alert:
    date: str
    index: int
    action: str
    score: float
    price: float


@dataclass
class Result:
    variant: Variant
    alerts: list[Alert] = field(default_factory=list)


def _monthly_lookup(dates: list[str], values: list[float]):
    """Return f(day) -> (value for the month *before* day's month, history up to it)."""
    months = [d[:7] for d in dates]

    def lookup(day: str) -> tuple[float | None, list[float]]:
        y, m = int(day[:4]), int(day[5:7])
        prev = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
        i = bisect.bisect_right(months, prev) - 1
        if i < 0:
            return None, []
        return values[i], values[max(0, i - PERCENTILE_MONTHS + 1): i + 1]

    return lookup


def simulate(data: dict, variants: list[Variant] = VARIANTS, start: str = "1990-01-01") -> tuple[list[Result], dict]:
    sp_dates, sp = data["sp500"]
    vix_dates, vix = data["vix"]
    cape_lookup = _monthly_lookup(*data["cape"])

    results = [Result(v) for v in variants]
    states: list[dict] = [{} for _ in variants]
    cfgs = [
        Config(resend_api_key=None, email_from="", audience_id=None, email_to=[],
               alert_threshold=v.threshold, min_corroborating=2,
               cooldown_days=v.cooldown_days, rearm_level=v.rearm_level,
               state_file="", dry_run=True, force=False)
        for v in variants
    ]

    first = max(WINDOW, bisect.bisect_left(sp_dates, max(start, vix_dates[0])))
    if first >= len(sp):
        raise ValueError(f"not enough S&P history to simulate: {len(sp)} rows, "
                         f"need more than {WINDOW} before {max(start, vix_dates[0])}")
    vj = 0
    for i in range(first, len(sp)):
        day = sp_dates[i]
        while vj + 1 < len(vix_dates) and vix_dates[vj + 1] <= day:
            vj += 1
        v_today = vix[vj] if vix_dates[vj] <= day else None
        cape, cape_past = cape_lookup(day)
        window = sp[i - WINDOW + 1: i + 1]
        now = datetime.fromisoformat(day).replace(hour=21, tzinfo=timezone.utc)

        for res, state, cfg in zip(results, states, cfgs):
            a = _assess(res.variant, window, v_today, cape, cape_past, day)
            if res.variant.latch:
                rearm(state, a.score, cfg.rearm_level)
            else:
                state["latched"] = None
            ok, _ = decide(a, cfg, state, now=now)
            tt = res.variant.trim_threshold
            if ok and tt is not None and a.action == "TRIM" and a.score > -tt:
                ok = False
            if ok:
                record_alert(state, a, now=now)
                res.alerts.append(Alert(day, i, a.action, a.score, sp[i]))

    span = {"first": sp_dates[first], "last": sp_dates[-1], "first_index": first,
            "years": (len(sp) - first) / 252.0}
    return results, span


# --------------------------------------------------------------------------
# Scoring the outcomes
# --------------------------------------------------------------------------

def forward_return(sp: list[float], i: int, h: int) -> float | None:
    if i + h >= len(sp):
        return None
    return sp[i + h] / sp[i] - 1.0


def follow_the_emails(sp: list[float], first: int, alerts: list[Alert]) -> float:
    """Start fully invested. TRIM: sell 10% of stocks to cash. BUY: all cash back in.

    Returns ending value relative to simply holding (1.0 = same as buy-and-hold).
    """
    by_index = {a.index: a.action for a in alerts}
    shares, cash = 1.0 / sp[first], 0.0
    for i in range(first, len(sp)):
        act = by_index.get(i)
        if act == "TRIM":
            sell = shares * TRIM_FRACTION
            shares -= sell
            cash += sell * sp[i]
        elif act == "BUY" and cash > 0:
            shares += cash / sp[i]
            cash = 0.0
    final = shares * sp[-1] + cash
    hold = sp[-1] / sp[first]
    return final / hold


def _median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def summarize(results: list[Result], span: dict, sp: list[float]) -> list[dict]:
    first = span["first_index"]
    h = HORIZONS["12m"]
    base_12m = [r for r in (forward_return(sp, i, h) for i in range(first, len(sp))) if r is not None]
    rows = []
    for res in results:
        trims = [a for a in res.alerts if a.action == "TRIM"]
        buys = [a for a in res.alerts if a.action == "BUY"]
        t12 = [r for r in (forward_return(sp, a.index, h) for a in trims) if r is not None]
        b12 = [r for r in (forward_return(sp, a.index, h) for a in buys) if r is not None]
        rows.append({
            "key": res.variant.key,
            "name": res.variant.name,
            "alerts": len(res.alerts),
            "per_year": len(res.alerts) / span["years"],
            "trims": len(trims),
            "buys": len(buys),
            "trim_12m_median": _median(t12),
            "trim_12m_fell": (sum(1 for r in t12 if r < 0) / len(t12)) if t12 else None,
            "buy_12m_median": _median(b12),
            "all_12m_median": _median(base_12m),
            "all_12m_fell": sum(1 for r in base_12m if r < 0) / len(base_12m),
            "follow_vs_hold": follow_the_emails(sp, first, res.alerts),
        })
    return rows


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def _pct(x: float | None, signed: bool = True) -> str:
    if x is None:
        return "—"
    return f"{x * 100:+.1f}%" if signed else f"{x * 100:.0f}%"


def render_markdown(results: list[Result], span: dict, rows: list[dict], sp: list[float]) -> str:
    out = [
        "# Be Greedy backtest",
        "",
        f"S&P 500, {span['first']} → {span['last']} ({span['years']:.1f} years). "
        "Price returns only; cash earns nothing.",
        "",
        "| Variant | Emails | per yr | TRIM | BUY | S&P 12m after TRIM (median) | TRIMs followed by a 12m fall | "
        "S&P 12m after BUY (median) | Follow emails vs hold |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        out.append(
            f"| {r['name']} | {r['alerts']} | {r['per_year']:.1f} | {r['trims']} | {r['buys']} | "
            f"{_pct(r['trim_12m_median'])} | {_pct(r['trim_12m_fell'], False)} | "
            f"{_pct(r['buy_12m_median'])} | {_pct(r['follow_vs_hold'] - 1)} |"
        )
    base = rows[0]
    out += [
        "",
        f"Baseline, any day: S&P 12m median {_pct(base['all_12m_median'])}; "
        f"fell over the next 12m {_pct(base['all_12m_fell'], False)} of the time.",
        "",
        f"*Follow emails vs hold*: start fully invested; each TRIM sells {TRIM_FRACTION:.0%} of stocks "
        "to cash, each BUY puts all cash back. Negative = following the emails ended with less.",
    ]
    for res in results:
        if res.variant.key not in ("new", "legacy"):
            continue
        out += ["", f"## Emails — {res.variant.name}", ""]
        if res.variant.key == "legacy":
            by_year: dict[str, list[int]] = {}
            for a in res.alerts:
                t, b = by_year.setdefault(a.date[:4], [0, 0])
                by_year[a.date[:4]] = [t + (a.action == "TRIM"), b + (a.action == "BUY")]
            out += ["| Year | TRIM | BUY |", "|---|---:|---:|"]
            out += [f"| {y} | {t} | {b} |" for y, (t, b) in sorted(by_year.items())]
            recent = [a for a in res.alerts if a.date >= "2026-05-01"]
            if recent:
                out += ["", "Since May 2026 (compare with the real emails in `state/` history): "
                        + ", ".join(f"{a.date} {a.action} {a.score:.0f}" for a in recent)]
            continue
        out += ["| Date | Email | Score | S&P | 3m | 6m | 12m | 24m |",
                "|---|---|---:|---:|---:|---:|---:|---:|"]
        for a in res.alerts:
            fwd = [_pct(forward_return(sp, a.index, h)) for h in HORIZONS.values()]
            label = "BE GREEDY" if a.action == "BUY" else "BE FEARFUL"
            out.append(f"| {a.date} | {label} | {a.score:.0f} | {a.price:,.0f} | " + " | ".join(fwd) + " |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Backtest Be Greedy's alerts over history")
    p.add_argument("--data", help="read cached history CSVs from this directory instead of fetching")
    p.add_argument("--save-data", help="after fetching, cache the history CSVs here")
    p.add_argument("--start", default="1990-01-01", help="first day to simulate (default 1990-01-01)")
    p.add_argument("--markdown", help="also write the Markdown report to this path (appends)")
    args = p.parse_args(argv)

    data = history.load_all(args.data) if args.data else history.fetch_all(save_to=args.save_data)
    results, span = simulate(data, start=args.start)
    rows = summarize(results, span, data["sp500"][1])
    md = render_markdown(results, span, rows, data["sp500"][1])
    print(md)
    if args.markdown:
        with open(args.markdown, "a") as f:
            f.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
