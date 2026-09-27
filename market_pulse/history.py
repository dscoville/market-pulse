"""Long price + valuation history for the backtest. Never used by the daily run.

The daily alert only needs ~2 years of prices (see ``data.py``). A backtest
needs decades, plus the monthly Shiller CAPE series, so it gets its own
fetchers here. Like ``data.py``, every source is keyless and the parsing is
pure so it can be tested offline.

  S&P 500 daily   Stooq full history, falling back to Yahoo (since 1970)
  VIX daily       datasets/finance-vix on GitHub (CBOE), falling back to Yahoo
  CAPE monthly    multpl.com's by-month table, falling back to Shiller's
                  dataset mirrored at datasets/s-and-p-500 on GitHub (which
                  stops being updated a few years back)

Fetched series can be written to / read from plain ``date,value`` CSVs so a
backtest can be re-run offline and reproducibly.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
import time
from datetime import datetime

from . import data

# An explicit period (from 1970) rather than range=max: Yahoo silently
# downgrades range=max to monthly-ish bars even when interval=1d is asked for.
YAHOO_HISTORY_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?period1=0&period2={now}&interval=1d"
)
VIX_GITHUB_URL = "https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv"
MULTPL_CAPE_TABLE_URL = "https://www.multpl.com/shiller-pe/table/by-month"
SHILLER_GITHUB_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv"

Series = tuple[list[str], list[float]]  # (ISO dates, values), oldest first


# --------------------------------------------------------------------------
# Pure parsers
# --------------------------------------------------------------------------

def _parse_date_value_csv(raw: str, date_col: str, value_col: str) -> Series:
    """Generic CSV -> (dates, values), skipping blanks/zeros, sorted oldest first."""
    rows: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        d = (row.get(date_col) or "").strip()
        v = (row.get(value_col) or "").strip()
        try:
            val = float(v)
        except ValueError:
            continue
        if not d or val <= 0:
            continue
        rows[_iso(d)] = val
    dates = sorted(rows)
    return dates, [rows[d] for d in dates]


def _iso(d: str) -> str:
    """Normalise 'YYYY-MM-DD' or 'MM/DD/YYYY' to ISO."""
    if "/" in d:
        return datetime.strptime(d, "%m/%d/%Y").strftime("%Y-%m-%d")
    return d[:10]


def parse_multpl_cape_table(html: str) -> Series:
    """Parse multpl's by-month CAPE table (rows like 'Sep 1, 2026' | '39.12')."""
    rows: dict[str, float] = {}
    pattern = re.compile(
        r"<td[^>]*>\s*([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})\s*</td>\s*<td[^>]*>(.*?)</td>",
        re.S,
    )
    for date_txt, cell in pattern.findall(html):
        text = re.sub(r"<[^>]+>|&#x?[0-9a-fA-F]+;|&[a-z]+;", " ", cell)
        m = re.search(r"\d+(?:\.\d+)?", text)
        if not m:
            continue
        val = float(m.group(0))
        if not 3 <= val <= 80:  # same sanity bound as data._parse_multpl_cape
            continue
        d = datetime.strptime(" ".join(date_txt.split()), "%b %d, %Y")
        rows[d.strftime("%Y-%m-01")] = val
    dates = sorted(rows)
    return dates, [rows[d] for d in dates]


def parse_shiller_cape(raw: str) -> Series:
    """PE10 column of the datasets/s-and-p-500 mirror of Shiller's data."""
    return _parse_date_value_csv(raw, "Date", "PE10")


def parse_vix_github(raw: str) -> Series:
    return _parse_date_value_csv(raw, "DATE", "CLOSE")


# --------------------------------------------------------------------------
# Fetchers (network)
# --------------------------------------------------------------------------

def is_daily(dates: list[str]) -> bool:
    """True if the series looks like daily bars (median gap of a few days)."""
    if len(dates) < 30:
        return False
    days = [datetime.fromisoformat(d) for d in dates]
    gaps = sorted((b - a).days for a, b in zip(days, days[1:]))
    return gaps[len(gaps) // 2] <= 4


def _first_usable(name: str, attempts, daily: bool = False) -> Series:
    problems = []
    for label, fn in attempts:
        try:
            dates, values = fn()
        except Exception as e:
            problems.append(f"{label}: {type(e).__name__}: {e}")
            continue
        if not values:
            problems.append(f"{label}: no usable rows")
        elif daily and not is_daily(dates):
            problems.append(f"{label}: {len(values)} rows are not daily bars")
        else:
            print(f"{name}: {len(values)} rows from {label} "
                  f"({dates[0]} → {dates[-1]})", file=sys.stderr)
            return dates, values
        print(f"{name}: {problems[-1]}", file=sys.stderr)
    raise ValueError(f"No usable {name} history. " + " | ".join(problems))


def _yahoo_history(key: str, timeout: int) -> Series:
    url = YAHOO_HISTORY_URL.format(symbol=data.YAHOO_SYMBOLS[key], now=int(time.time()))
    return data._parse_yahoo_chart(data._http_get(url, timeout))


def fetch_sp500_history(timeout: int = 60) -> Series:
    return _first_usable("S&P 500", [
        ("Stooq", lambda: data._fetch_stooq("sp500", timeout)),
        ("Yahoo", lambda: _yahoo_history("sp500", timeout)),
    ], daily=True)


def fetch_vix_history(timeout: int = 60) -> Series:
    return _first_usable("VIX", [
        ("GitHub finance-vix", lambda: parse_vix_github(data._http_get(VIX_GITHUB_URL, timeout))),
        ("Yahoo", lambda: _yahoo_history("vix", timeout)),
    ], daily=True)


def fetch_cape_history(timeout: int = 60) -> Series:
    return _first_usable("CAPE", [
        ("multpl", lambda: parse_multpl_cape_table(data._http_get(MULTPL_CAPE_TABLE_URL, timeout))),
        ("GitHub Shiller mirror", lambda: parse_shiller_cape(data._http_get(SHILLER_GITHUB_URL, timeout))),
    ])


# --------------------------------------------------------------------------
# Local cache: plain date,value CSVs
# --------------------------------------------------------------------------

FILES = {"sp500": "sp500_daily.csv", "vix": "vix_daily.csv", "cape": "cape_monthly.csv"}


def save_series(path: str, series: Series) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for d, v in zip(*series):
            w.writerow([d, f"{v:.4f}".rstrip("0").rstrip(".")])


def load_series(path: str) -> Series:
    with open(path) as f:
        return _parse_date_value_csv(f.read(), "date", "value")


def load_all(directory: str) -> dict[str, Series]:
    return {k: load_series(os.path.join(directory, name)) for k, name in FILES.items()}


def fetch_all(save_to: str | None = None) -> dict[str, Series]:
    out = {
        "sp500": fetch_sp500_history(),
        "vix": fetch_vix_history(),
        "cape": fetch_cape_history(),
    }
    if save_to:
        for k, name in FILES.items():
            save_series(os.path.join(save_to, name), out[k])
    return out
