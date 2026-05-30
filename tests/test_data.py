"""Offline tests for data parsing and provider fallback. No network."""

import json

import pytest

from market_pulse import data


# --------------------------------------------------------------------------
# Pure parsers
# --------------------------------------------------------------------------

def test_parse_stooq_csv_happy():
    raw = "Date,Open,High,Low,Close,Volume\n2026-05-28,10,11,9,10.5,0\n2026-05-29,10,12,9,11.25,0\n"
    dates, closes = data._parse_stooq_csv(raw)
    assert dates == ["2026-05-28", "2026-05-29"]
    assert closes == [10.5, 11.25]


def test_parse_stooq_csv_rate_limit_page_yields_nothing():
    # Stooq serves an HTML notice (HTTP 200) when it throttles a cloud IP.
    raw = "Exceeded the daily hits limit of the country\n"
    dates, closes = data._parse_stooq_csv(raw)
    assert dates == [] and closes == []


def test_parse_yahoo_chart_happy_and_skips_nulls():
    doc = {
        "chart": {
            "result": [
                {
                    # 2021-01-04, 2021-01-05, 2021-01-06 (UTC midnights)
                    "timestamp": [1609718400, 1609804800, 1609891200],
                    "indicators": {"quote": [{"close": [100.0, None, 102.5]}]},
                }
            ]
        }
    }
    dates, closes = data._parse_yahoo_chart(json.dumps(doc))
    # the middle row (null close) is dropped
    assert closes == [100.0, 102.5]
    assert dates == ["2021-01-04", "2021-01-06"]


def test_parse_yahoo_chart_error_payload_yields_nothing():
    doc = {"chart": {"result": None, "error": {"code": "Not Found"}}}
    assert data._parse_yahoo_chart(json.dumps(doc)) == ([], [])


# --------------------------------------------------------------------------
# Provider fallback
# --------------------------------------------------------------------------

def test_fallback_to_second_provider_when_first_is_empty(monkeypatch):
    monkeypatch.setattr(data, "_fetch_stooq", lambda k, t: ([], []))         # throttled
    monkeypatch.setattr(data, "_fetch_yahoo", lambda k, t: (["d"], [42.0]))  # works
    monkeypatch.setattr(data, "_PROVIDERS",
                        (("Stooq", data._fetch_stooq), ("Yahoo", data._fetch_yahoo)))
    dates, closes = data.fetch_closes("sp500")
    assert closes == [42.0]


def test_fallback_when_first_raises(monkeypatch):
    def boom(k, t):
        raise OSError("connection reset")
    monkeypatch.setattr(data, "_fetch_stooq", boom)
    monkeypatch.setattr(data, "_fetch_yahoo", lambda k, t: (["d"], [7.0]))
    monkeypatch.setattr(data, "_PROVIDERS",
                        (("Stooq", data._fetch_stooq), ("Yahoo", data._fetch_yahoo)))
    _, closes = data.fetch_closes("sp500")
    assert closes == [7.0]


def test_all_providers_failing_raises_with_detail(monkeypatch):
    monkeypatch.setattr(data, "_fetch_stooq", lambda k, t: ([], []))
    monkeypatch.setattr(data, "_fetch_yahoo", lambda k, t: ([], []))
    monkeypatch.setattr(data, "_PROVIDERS",
                        (("Stooq", data._fetch_stooq), ("Yahoo", data._fetch_yahoo)))
    with pytest.raises(ValueError) as ei:
        data.fetch_closes("sp500")
    msg = str(ei.value)
    assert "Stooq" in msg and "Yahoo" in msg
