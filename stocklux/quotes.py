"""Deterministic quote fetcher: yfinance → quotes.json structure.

Failure semantics: a failed ticker keeps its previous values with stale=True;
with no previous record, all fields are null.
"""
from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf

FIELDS = {
    "price": "currentPrice",
    "ttm_pe": "trailingPE",
    "fwd_pe": "forwardPE",
    "ttm_eps": "trailingEps",
    "fwd_eps": "forwardEps",
    "market_cap": "marketCap",
    "high_52w": "fiftyTwoWeekHigh",
    "low_52w": "fiftyTwoWeekLow",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_one(ticker: str) -> dict:
    info = yf.Ticker(ticker).info
    quote = {k: info.get(v) for k, v in FIELDS.items()}
    if quote["price"] is None:
        quote["price"] = info.get("regularMarketPrice")
    quote["stale"] = False
    quote["fetched_at"] = _now()
    return quote


def fetch_quotes(tickers: list[str], prev: dict | None = None) -> dict:
    prev_quotes = (prev or {}).get("quotes", {})
    quotes: dict = {}
    for t in tickers:
        try:
            quotes[t] = _fetch_one(t)
        except Exception:
            prev_q = prev_quotes.get(t) or {}
            old = {k: prev_q.get(k) for k in FIELDS}
            old["fetched_at"] = prev_q.get("fetched_at")
            old["stale"] = True
            quotes[t] = old
    return {"fetched_at": _now(), "quotes": quotes}
