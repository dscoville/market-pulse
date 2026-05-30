"""Market data fetching. The only module that touches the network.

Source: Stooq daily CSV (keyless, no API key required).
  S&P 500 -> ^spx,  VIX -> ^vix

Returns plain Python lists so the signal engine stays dependency-free and
fully testable offline.
"""

from __future__ import annotations

import csv
import io
import urllib.request

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"

SYMBOLS = {
    "sp500": "^spx",
    "vix": "^vix",
}


def fetch_closes(symbol_key: str, timeout: int = 30) -> tuple[list[str], list[float]]:
    """Fetch (dates, closes) for a symbol, oldest first.

    `symbol_key` may be a friendly name in SYMBOLS ("sp500", "vix") or a raw
    Stooq symbol.
    """
    symbol = SYMBOLS.get(symbol_key, symbol_key)
    url = STOOQ_URL.format(symbol=symbol)
    req = urllib.request.Request(url, headers={"User-Agent": "market-pulse/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")

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

    if not closes:
        raise ValueError(
            f"No usable data returned for '{symbol}'. "
            f"Stooq may be rate-limiting or the symbol changed. URL: {url}"
        )
    return dates, closes
