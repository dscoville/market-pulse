"""Market data fetching. The only module that touches the network.

Resilient by design: the daily prices come from one of several keyless
sources, tried in order, so a single provider rate-limiting a cloud IP (Stooq
routinely 200s an HTML "limit exceeded" page to GitHub runners) doesn't take
the whole run down.

  1. Stooq daily CSV       S&P 500 -> ^spx,   VIX -> ^vix
  2. Yahoo Finance chart   S&P 500 -> ^GSPC,  VIX -> ^VIX

The network calls are thin; the parsing is pure (``_parse_stooq_csv`` /
``_parse_yahoo_chart``) so it stays dependency-free and testable offline.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

# Browser-ish UA: Yahoo 403s the stdlib default, and it doesn't hurt Stooq.
_UA = "Mozilla/5.0 (compatible; market-pulse/0.1; +https://github.com/dscoville/market-pulse)"

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
STOOQ_SYMBOLS = {"sp500": "^spx", "vix": "^vix"}

YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?range=2y&interval=1d"
)
YAHOO_SYMBOLS = {"sp500": "%5EGSPC", "vix": "%5EVIX"}  # %5E == '^'


def _http_get(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _parse_stooq_csv(raw: str) -> tuple[list[str], list[float]]:
    """Parse Stooq's daily CSV. Returns ([], []) if it's not usable CSV."""
    dates: list[str] = []
    closes: list[float] = []
    for row in csv.DictReader(io.StringIO(raw)):
        value = row.get("Close")
        if value in (None, "", "null", "N/A"):
            continue
        try:
            close = float(value)
        except (TypeError, ValueError):
            continue
        dates.append(row.get("Date", ""))
        closes.append(close)
    return dates, closes


def _parse_yahoo_chart(raw: str) -> tuple[list[str], list[float]]:
    """Parse Yahoo's v8 chart JSON. Returns ([], []) if it's not usable."""
    doc = json.loads(raw)
    result = (doc.get("chart") or {}).get("result") or []
    if not result:
        return [], []
    res = result[0]
    stamps = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    raw_closes = quote.get("close") or []
    dates: list[str] = []
    closes: list[float] = []
    for ts, close in zip(stamps, raw_closes):
        if close is None:  # Yahoo nulls out non-trading / missing days
            continue
        dates.append(datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"))
        closes.append(float(close))
    return dates, closes


def _fetch_stooq(symbol_key: str, timeout: int) -> tuple[list[str], list[float]]:
    symbol = STOOQ_SYMBOLS.get(symbol_key, symbol_key)
    return _parse_stooq_csv(_http_get(STOOQ_URL.format(symbol=symbol), timeout))


def _fetch_yahoo(symbol_key: str, timeout: int) -> tuple[list[str], list[float]]:
    symbol = YAHOO_SYMBOLS.get(symbol_key)
    if symbol is None:  # only know how to map our own keys to Yahoo tickers
        return [], []
    return _parse_yahoo_chart(_http_get(YAHOO_URL.format(symbol=symbol), timeout))


_PROVIDERS = (("Stooq", _fetch_stooq), ("Yahoo", _fetch_yahoo))


def fetch_closes(symbol_key: str, timeout: int = 30) -> tuple[list[str], list[float]]:
    """Fetch (dates, closes) for a symbol, oldest first.

    Tries each provider in turn and returns the first that yields usable data,
    so one source being down or rate-limited doesn't fail the run.
    """
    problems: list[str] = []
    for name, provider in _PROVIDERS:
        try:
            dates, closes = provider(symbol_key, timeout)
        except Exception as e:  # network/parse hiccup — try the next source
            problems.append(f"{name}: {type(e).__name__}: {e}")
            continue
        if closes:
            return dates, closes
        problems.append(f"{name}: no usable rows (likely rate-limited)")

    raise ValueError(
        f"No usable data for '{symbol_key}' from any source. "
        + " | ".join(problems)
    )


# --------------------------------------------------------------------------
# Valuation gauges (slow-moving, best-effort, optional — like the VIX).
# Parsing is pure so it's testable offline; the fetchers swallow failures and
# return None so a flaky source can never take down the daily run.
# --------------------------------------------------------------------------

MULTPL_CAPE_URL = "https://www.multpl.com/shiller-pe"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


def _parse_multpl_cape(html: str) -> float | None:
    """Pull the current Shiller CAPE (PE10) out of a multpl.com page."""
    m = re.search(r"Current Shiller PE Ratio:?\s*([0-9]+(?:\.[0-9]+)?)", html, re.I)
    return float(m.group(1)) if m else None


def _parse_fred_latest(csv_text: str) -> float | None:
    """Most recent numeric value from a FRED CSV download (skips '.' gaps)."""
    rows = csv_text.strip().splitlines()
    for line in reversed(rows[1:]):  # skip the header row
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            return float(parts[-1].strip())
        except ValueError:
            continue
    return None


def fetch_cape(timeout: int = 30) -> float | None:
    """Current Shiller CAPE. Returns None (with a reason) if unavailable."""
    try:
        html = _http_get(MULTPL_CAPE_URL, timeout)
    except Exception as e:
        print(f"CAPE: fetch failed — {type(e).__name__}: {e}", file=sys.stderr)
        return None
    v = _parse_multpl_cape(html)
    if v is None:
        has = "Shiller" in html
        print(f"CAPE: page fetched ({len(html)} bytes, 'Shiller' present={has}) "
              "but no value parsed", file=sys.stderr)
    return v


def _fred_latest(series: str, timeout: int) -> float | None:
    try:
        return _parse_fred_latest(_http_get(FRED_CSV_URL.format(series=series), timeout))
    except Exception as e:
        print(f"Buffett: FRED {series} fetch failed — {type(e).__name__}: {e}", file=sys.stderr)
        return None


def fetch_buffett_indicator(timeout: int = 30) -> float | None:
    """Approximate Buffett Indicator (total US market cap / GDP, %).

    Uses the Wilshire 5000 full-cap index (≈ total market value in $bn) over
    GDP ($bn), both from FRED's keyless CSV. Returns None on any failure.
    """
    will = _fred_latest("WILL5000PRFC", timeout)
    gdp = _fred_latest("GDP", timeout)
    if not will or not gdp:
        print(f"Buffett: missing data (wilshire={will}, gdp={gdp})", file=sys.stderr)
        return None
    return will / gdp * 100.0
