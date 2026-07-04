"""Data layer: watchlist I/O, memo/thesis frontmatter parsing and validation.

Immutable style: transform functions take an object and return a new one;
nothing is mutated in place.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

ACTIONS = [
    "enter", "wait_for_pullback", "hold", "watch_only",
    "good_company_bad_price", "crowded_theme", "thesis_broken",
    "no_edge", "trim", "exit",
]
SIGNAL_KEYS = [
    "chain", "narrative", "fundamentals", "valuation",
    "flows", "sentiment", "competition", "macro",
]
SIGNAL_VALUES = ["favorable", "neutral", "unfavorable", "no_signal"]
THESIS_STATUS = ["intact", "weakening", "damaged", "dead"]
CONFIDENCE = ["high", "medium", "low"]


def ensure_dirs(data_dir: Path) -> None:
    for sub in ("theses", "analyses", "retrospects"):
        (Path(data_dir) / sub).mkdir(parents=True, exist_ok=True)


def load_watchlist(data_dir: Path) -> dict:
    p = Path(data_dir) / "watchlist.json"
    if not p.exists():
        return {"stocks": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_watchlist(data_dir: Path, watchlist: dict) -> None:
    p = Path(data_dir) / "watchlist.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(watchlist, ensure_ascii=False, indent=2), encoding="utf-8")


def add_stock(
    watchlist: dict, *, ticker: str, thesis: str,
    layer: str = "", name: str = "", note: str = "", holding: bool = False,
) -> dict:
    if not TICKER_RE.match(ticker):
        raise ValueError(f"invalid ticker: {ticker} (uppercase, e.g. MU, BRK.B)")
    if any(s["ticker"] == ticker for s in watchlist["stocks"]):
        raise ValueError(f"{ticker} is already on the watchlist")
    entry = {
        "ticker": ticker, "name": name, "thesis": thesis, "layer": layer,
        "added": datetime.now(timezone.utc).date().isoformat(), "note": note,
        "holding": holding,
    }
    return {"stocks": watchlist["stocks"] + [entry]}


def set_holding(watchlist: dict, ticker: str, holding: bool) -> dict:
    if not any(s["ticker"] == ticker for s in watchlist["stocks"]):
        raise ValueError(f"{ticker} is not on the watchlist")
    return {"stocks": [
        {**s, "holding": holding} if s["ticker"] == ticker else s
        for s in watchlist["stocks"]
    ]}


def remove_stock(watchlist: dict, ticker: str) -> dict:
    return {"stocks": [s for s in watchlist["stocks"] if s["ticker"] != ticker]}


_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

MEMO_REQUIRED = [
    "ticker", "date", "thesis", "action", "confidence",
    "price_at_analysis", "verdict", "thesis_health", "review_trigger",
]
_VERDICTS = ["below_range", "in_range", "above_range"]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1)) or {}
    return meta, m.group(2)


HOLDING_ONLY_ACTIONS = ["hold", "trim", "exit"]
NON_HOLDING_ONLY_ACTIONS = ["enter", "wait_for_pullback"]


def validate_memo(meta: dict, *, holding: bool | None = None) -> list[str]:
    errors = [f"missing field: {f}" for f in MEMO_REQUIRED if f not in meta]
    action = meta.get("action")
    if holding is True and action in NON_HOLDING_ONLY_ACTIONS:
        errors.append(
            f"action '{action}' is only legal when the watchlist entry is not "
            f"holding (this name has holding=true)")
    if holding is False and action in HOLDING_ONLY_ACTIONS:
        errors.append(
            f"action '{action}' requires holding=true on the watchlist entry "
            f"(set it with `stocklux hold <TICKER>`)")
    if "ticker" in meta and not isinstance(meta["ticker"], str):
        errors.append(
            f"ticker must be a string (YAML parses bare ON/NO/YES as booleans — "
            f"quote it): {meta['ticker']!r}")
    if "action" in meta and meta["action"] not in ACTIONS:
        errors.append(f"invalid action: {meta['action']} (must be one of the ten states)")
    if "confidence" in meta and meta["confidence"] not in CONFIDENCE:
        errors.append(f"invalid confidence: {meta['confidence']} (high/medium/low)")
    if "thesis_health" in meta and meta["thesis_health"] not in THESIS_STATUS:
        errors.append(f"invalid thesis_health: {meta['thesis_health']}")
    if "verdict" in meta and meta["verdict"] not in _VERDICTS:
        errors.append(f"invalid verdict: {meta['verdict']}")
    br = meta.get("buy_range")
    if br is not None and not (isinstance(br, list) and len(br) == 2):
        errors.append("buy_range must be [low, high] or null")
    pt = meta.get("price_targets")
    if pt is not None:
        if not isinstance(pt, dict):
            errors.append("price_targets must be {bear, base, bull, horizon} or null")
        else:
            for k in ("bear", "base", "bull"):
                if not isinstance(pt.get(k), (int, float)):
                    errors.append(f"price_targets.{k} must be a number")
    for k, v in (meta.get("signals") or {}).items():
        if k not in SIGNAL_KEYS:
            errors.append(f"unknown signal dimension: {k}")
        elif v not in SIGNAL_VALUES:
            errors.append(f"invalid signal value: {k}={v}")
    return errors


def list_memos(data_dir: Path, ticker: str) -> list[Path]:
    d = Path(data_dir) / "analyses" / ticker
    return sorted(d.glob("*.md")) if d.exists() else []


def load_memo(path: Path, *, holding: bool | None = None) -> dict:
    meta, body = parse_frontmatter(Path(path).read_text(encoding="utf-8"))
    return {"meta": meta, "body": body,
            "errors": validate_memo(meta, holding=holding), "path": str(path)}


def latest_memo(data_dir: Path, ticker: str, *, holding: bool | None = None) -> dict | None:
    memos = list_memos(data_dir, ticker)
    return load_memo(memos[-1], holding=holding) if memos else None


def list_theses(data_dir: Path) -> list[dict]:
    d = Path(data_dir) / "theses"
    paths = sorted(d.glob("*.md")) if d.exists() else []
    out = []
    for p in paths:
        meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        out.append({"id": p.stem, "meta": meta, "body": body, "path": str(p)})
    return out
