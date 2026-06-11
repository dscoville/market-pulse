"""The heart of Be Greedy: turn raw price history into one conviction score.

The composite score runs from -100 to +100:

    +100  ........  extreme FEAR in the market   -> BE GREEDY (buy)
       0  ........  nothing out of the ordinary  -> STAND PAT (do nothing)
    -100  ........  extreme GREED in the market  -> BE FEARFUL (trim)

Every function here is pure (no network, no clock, no I/O) so the whole engine
is deterministic and unit-testable offline. `data.py` is the only thing that
touches the network.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Signal:
    key: str          # machine name, e.g. "drawdown"
    label: str        # human label for the email
    display: str      # formatted value, e.g. "-18.2%"
    score: float      # signed contribution to the composite
    note: str = ""    # one-line Buffett-flavoured interpretation

    @property
    def direction(self) -> str:
        if self.score > 0:
            return "fear"   # pushes toward BUY
        if self.score < 0:
            return "greed"  # pushes toward TRIM
        return "neutral"


@dataclass
class Assessment:
    score: float          # composite, clamped to [-100, 100]
    action: str           # "BUY" | "TRIM" | "HOLD"
    stance: str           # short label, e.g. "BE GREEDY"
    headline: str         # one sentence summary
    signals: list[Signal]
    price: float
    as_of: str

    def corroborating(self, min_magnitude: float = 8.0) -> int:
        """How many signals meaningfully agree with the composite direction."""
        if self.action == "HOLD":
            return 0
        want = "fear" if self.action == "BUY" else "greed"
        return sum(
            1 for s in self.signals
            if s.direction == want and abs(s.score) >= min_magnitude
        )


# --------------------------------------------------------------------------
# Indicator primitives
# --------------------------------------------------------------------------

def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def wilder_rsi(closes: list[float], period: int = 14) -> float | None:
    """Relative Strength Index using Wilder's smoothing. Returns 0..100."""
    if len(closes) <= period:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def drawdown_from_high(closes: list[float], lookback: int = 252) -> float:
    """Percent below the trailing high (<= 0). e.g. -18.2 means 18.2% off the high."""
    window = closes[-lookback:] if len(closes) >= lookback else closes
    high = max(window)
    last = closes[-1]
    return (last - high) / high * 100.0


def range_position(closes: list[float], lookback: int = 252) -> float:
    """Where the last price sits in its trailing range: 0.0 = low, 1.0 = high."""
    window = closes[-lookback:] if len(closes) >= lookback else closes
    lo = min(window)
    hi = max(window)
    last = closes[-1]
    if hi == lo:
        return 0.5
    return (last - lo) / (hi - lo)


def _interp(x: float, points: list[tuple[float, float]]) -> float:
    """Piecewise-linear map of x through (x, y) knots, clamped at both ends."""
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return points[-1][1]


# --------------------------------------------------------------------------
# Scoring curves. Positive => fear/cheap => lean BUY. Negative => greed/expensive.
# Tuned so that a single signal can't trip an alert on its own; it takes a
# genuine, corroborated extreme to clear the default threshold of 60.
# --------------------------------------------------------------------------

_DRAWDOWN_CURVE = [(-40, 55), (-30, 46), (-20, 33), (-12, 20), (-7, 9), (-3, 3), (0, 0)]
_RSI_CURVE = [(10, 35), (20, 25), (30, 13), (40, 4), (50, 0), (60, -4), (70, -13), (80, -25), (90, -35)]
_TREND_CURVE = [(-20, 24), (-12, 15), (-5, 6), (0, 0), (5, -6), (12, -15), (20, -24)]
_RANGE_CURVE = [(0.0, 13), (0.1, 9), (0.3, 3), (0.5, 0), (0.7, -3), (0.9, -9), (1.0, -13)]
_VIX_CURVE = [(10, -18), (13, -10), (17, 0), (20, 7), (25, 16), (30, 26), (40, 40), (55, 50)]

# Valuation curves. Slow-moving "how expensive is the market" gauges — the
# Buffett-flavoured heart of the engine. High readings => expensive => greed
# => negative (lean TRIM / BE FEARFUL).
#   Shiller CAPE: long-run mean ~17; dot-com peak ~44; 1929 peak ~33.
_CAPE_CURVE = [(8, 30), (12, 20), (16, 8), (20, 0), (24, -8), (28, -16), (32, -26), (36, -36), (40, -46), (45, -52)]
#   Buffett Indicator (total market cap / GDP, %): historic mean ~85; dot-com
#   ~145; 2021 ~200; mid-2020s records ~210-240.
_BUFFETT_CURVE = [(60, 25), (80, 12), (100, 0), (120, -10), (140, -20), (160, -28), (185, -36), (210, -44), (240, -52)]


def evaluate(
    closes: list[float],
    vix_closes: list[float] | None = None,
    as_of: str = "",
    cape: float | None = None,
    buffett_indicator: float | None = None,
) -> Assessment:
    """Score the market from a list of daily S&P 500 closes (oldest -> newest)."""
    if len(closes) < 30:
        raise ValueError("need at least ~30 daily closes to assess the market")

    price = closes[-1]
    signals: list[Signal] = []

    dd = drawdown_from_high(closes, 252)
    signals.append(Signal(
        "drawdown", "Drawdown from 1-year high", f"{dd:.1f}%",
        _interp(dd, _DRAWDOWN_CURVE),
        "Great businesses go on sale when the index sells off.",
    ))

    rsi = wilder_rsi(closes, 14)
    if rsi is not None:
        signals.append(Signal(
            "rsi", "Momentum (14-day RSI)", f"{rsi:.0f}",
            _interp(rsi, _RSI_CURVE),
            "Oversold = panic selling; overbought = crowd euphoria.",
        ))

    s200 = sma(closes, 200)
    if s200:
        dev = (price - s200) / s200 * 100.0
        signals.append(Signal(
            "trend", "Distance from 200-day average", f"{dev:+.1f}%",
            _interp(dev, _TREND_CURVE),
            "Far below trend is bargain territory; far above is stretched.",
        ))

    pos = range_position(closes, 252)
    signals.append(Signal(
        "range", "Position in 52-week range", f"{pos * 100:.0f}% of range",
        _interp(pos, _RANGE_CURVE),
        "Near the lows the crowd is fearful; near the highs, greedy.",
    ))

    if vix_closes:
        vix = vix_closes[-1]
        signals.append(Signal(
            "vix", "Volatility (VIX fear gauge)", f"{vix:.1f}",
            _interp(vix, _VIX_CURVE),
            "A spiking VIX is the market screaming; a sleepy VIX is complacency.",
        ))

    if cape is not None:
        signals.append(Signal(
            "cape", "Shiller CAPE (10-year P/E)", f"{cape:.0f}",
            _interp(cape, _CAPE_CURVE),
            "Shiller's 10-year P/E — high means stocks are dear versus a decade of earnings.",
        ))

    if buffett_indicator is not None:
        signals.append(Signal(
            "buffett", "Buffett Indicator (market cap / GDP)", f"{buffett_indicator:.0f}%",
            _interp(buffett_indicator, _BUFFETT_CURVE),
            "Total US market value versus GDP — Buffett's favourite gauge. Sky-high means expensive.",
        ))

    raw = sum(s.score for s in signals)
    score = max(-100.0, min(100.0, raw))
    action, stance, headline = _classify(score)
    return Assessment(score, action, stance, headline, signals, price, as_of)


def _classify(score: float) -> tuple[str, str, str]:
    if score >= 60:
        return ("BUY", "BE GREEDY",
                "Blood in the streets. Be greedy when others are fearful — this is a buying window.")
    if score >= 40:
        return ("BUY", "LEAN IN",
                "Fear is rising and value is starting to appear. Consider adding.")
    if score <= -60:
        return ("TRIM", "BE FEARFUL",
                "Euphoria is running hot. Be fearful when others are greedy — consider taking some off the top.")
    if score <= -40:
        return ("TRIM", "TRIM A LITTLE",
                "The market is running rich. You could trim a little off the top.")
    return ("HOLD", "STAND PAT",
            "Nothing is out of whack. Do nothing — usually the smartest move.")
