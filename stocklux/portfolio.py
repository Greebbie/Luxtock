"""Module 2 — portfolio concentration & bear-stress report.

Deterministic computation over data/watchlist.json (optional per-entry
`shares` and top-level `cash_usd`), data/quotes.json, and the latest memo
frontmatter's price_targets.bear per ticker. No mutation; pure reads.

Holdings = watchlist entries with `holding: true`. A holding with no shares
(or shares == 0) is "unsized": it is listed in `positions` but excluded from
weight math, group math, and bear-stress. A sized holding whose quote price
is unavailable is degraded to unsized the same way (no value can be computed).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import store

SINGLE_NAME_CAUTION_PCT = 25.0
SINGLE_NAME_WARNING_PCT = 35.0
GROUP_CAUTION_PCT = 40.0
GROUP_WARNING_PCT = 60.0
BEAR_STRESS_WARNING_PCT = 20.0


def _load_quotes(data_dir: Path) -> dict:
    p = Path(data_dir) / "quotes.json"
    if not p.exists():
        return {"quotes": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def _price(quotes: dict, ticker: str) -> float | None:
    q = quotes.get("quotes", {}).get(ticker)
    price = q.get("price") if q else None
    return price if isinstance(price, (int, float)) else None


def _bear_target(data_dir: Path, ticker: str) -> float | None:
    """Latest memo's price_targets.bear for ticker, or None if no memo /
    no price_targets / non-numeric bear."""
    memo = store.latest_memo(data_dir, ticker)
    if not memo:
        return None
    pt = memo["meta"].get("price_targets")
    if not isinstance(pt, dict):
        return None
    bear = pt.get("bear")
    return bear if isinstance(bear, (int, float)) else None


def _group_weights(sized_positions: list[dict], entries_by_ticker: dict, key: str) -> dict:
    totals: dict[str, float] = {}
    for pos in sized_positions:
        group = entries_by_ticker[pos["ticker"]].get(key) or "(none)"
        totals[group] = totals.get(group, 0.0) + pos["weight_pct"]
    return totals


def _single_name_flags(sized_positions: list[dict]) -> list[dict]:
    flags = []
    for pos in sized_positions:
        w = pos["weight_pct"]
        if w >= SINGLE_NAME_WARNING_PCT:
            flags.append({
                "level": "warning", "kind": "single_name",
                "detail": (f"{pos['ticker']} is {w:.1f}% of portfolio "
                           f"(>= {SINGLE_NAME_WARNING_PCT:.0f}% warning)"),
            })
        elif w >= SINGLE_NAME_CAUTION_PCT:
            flags.append({
                "level": "caution", "kind": "single_name",
                "detail": (f"{pos['ticker']} is {w:.1f}% of portfolio "
                           f"(>= {SINGLE_NAME_CAUTION_PCT:.0f}% caution)"),
            })
    return flags


def _group_flags(groups: dict, label: str) -> list[dict]:
    flags = []
    for name, w in groups.items():
        if w >= GROUP_WARNING_PCT:
            flags.append({
                "level": "warning", "kind": "group",
                "detail": (f"{label} '{name}' is {w:.1f}% of portfolio "
                           f"(>= {GROUP_WARNING_PCT:.0f}% warning)"),
            })
        elif w >= GROUP_CAUTION_PCT:
            flags.append({
                "level": "caution", "kind": "group",
                "detail": (f"{label} '{name}' is {w:.1f}% of portfolio "
                           f"(>= {GROUP_CAUTION_PCT:.0f}% caution)"),
            })
    return flags


def portfolio_report(data_dir: Path) -> dict:
    data_dir = Path(data_dir)
    wl = store.load_watchlist(data_dir)
    quotes = _load_quotes(data_dir)
    cash_usd = wl.get("cash_usd") or 0.0

    holdings = [s for s in wl["stocks"] if s.get("holding")]

    sized_raw: list[tuple[dict, float, float, float]] = []  # entry, shares, price, value
    unsized_positions: list[dict] = []
    for entry in holdings:
        shares = entry.get("shares") or 0
        price = _price(quotes, entry["ticker"])
        if shares and shares > 0 and price is not None:
            sized_raw.append((entry, shares, price, shares * price))
        else:
            unsized_positions.append({
                "ticker": entry["ticker"], "shares": shares, "price": price,
                "unsized": True,
            })

    total_value = sum(value for *_rest, value in sized_raw) + cash_usd

    positions: list[dict] = []
    entries_by_ticker: dict[str, dict] = {}
    for entry, shares, price, value in sized_raw:
        weight_pct = (value / total_value * 100) if total_value else 0.0
        positions.append({
            "ticker": entry["ticker"], "shares": shares, "price": price,
            "value": value, "weight_pct": weight_pct,
        })
        entries_by_ticker[entry["ticker"]] = entry
    positions.extend(unsized_positions)

    sized_positions = [p for p in positions if not p.get("unsized")]

    by_layer = _group_weights(sized_positions, entries_by_ticker, "layer")
    by_thesis = _group_weights(sized_positions, entries_by_ticker, "thesis")
    groups = {"by_layer": by_layer, "by_thesis": by_thesis}

    flags: list[dict] = []
    flags.extend(_single_name_flags(sized_positions))
    flags.extend(_group_flags(by_layer, "layer"))
    flags.extend(_group_flags(by_thesis, "thesis"))

    covered_tickers: list[str] = []
    uncovered_tickers: list[str] = []
    stressed_total = cash_usd
    for entry, shares, price, value in sized_raw:
        ticker = entry["ticker"]
        bear = _bear_target(data_dir, ticker)
        if bear is not None:
            covered_tickers.append(ticker)
            stressed_total += shares * bear
        else:
            uncovered_tickers.append(ticker)
            stressed_total += value

    drawdown_pct = ((total_value - stressed_total) / total_value * 100) if total_value else 0.0

    bear_stress = {
        "stressed_value": stressed_total,
        "drawdown_pct": drawdown_pct,
        "covered_tickers": covered_tickers,
        "uncovered_tickers": uncovered_tickers,
    }
    if drawdown_pct >= BEAR_STRESS_WARNING_PCT:
        flags.append({
            "level": "warning", "kind": "bear_stress",
            "detail": (f"bear-case portfolio drawdown {drawdown_pct:.1f}% "
                       f"(>= {BEAR_STRESS_WARNING_PCT:.0f}% warning)"),
        })

    return {
        "positions": positions,
        "cash_usd": cash_usd,
        "total_value": total_value,
        "groups": groups,
        "flags": flags,
        "bear_stress": bear_stress,
    }
