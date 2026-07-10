"""Module 3 — probability calibration ledger (data/calibration.json).

Grades matured memo price targets against realized history and tracks
immature memos so the ledger is useful from day one. Pure/deterministic:
reads memo frontmatter (via luxtock.store), data/history.jsonl and
data/quotes.json, never mutates its inputs. See framework/quant.md
"Module 3 — luxtock/calibrate.py" for the spec this implements.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from luxtock import store

MATURITY_DAYS = 365
REALIZED_MATCH_WINDOW_DAYS = 14
_TIERS = ("bear", "base", "bull")
_TARGET_KEYS = ("bear", "base", "bull")
_PROB_KEYS = ("p_bear", "p_base", "p_bull")


def _meta_date(meta: dict) -> date | None:
    v = meta.get("date")
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _full_price_targets(pt) -> bool:
    """A memo carries 'full' price targets when it has bear/base/bull AND
    the tier probabilities (the v2 contract) — the shape Brier grading
    needs. Grandfathered pre-policy memos lacking probabilities cannot be
    graded and are excluded from the matured ledger."""
    if not isinstance(pt, dict):
        return False
    return all(_is_number(pt.get(k)) for k in (*_TARGET_KEYS, *_PROB_KEYS))


def _has_bear_base_bull(pt) -> bool:
    if not isinstance(pt, dict):
        return False
    return all(_is_number(pt.get(k)) for k in _TARGET_KEYS)


def _load_quotes(data_dir: Path) -> dict:
    p = Path(data_dir) / "quotes.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _load_history(data_dir: Path) -> list[dict]:
    p = Path(data_dir) / "history.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = _parse_iso_date(row.get("date"))
        if d is None or not row.get("ticker"):
            continue
        rows.append({"date": d, "ticker": row["ticker"], "price": row.get("price")})
    return rows


def _parse_iso_date(v) -> date | None:
    try:
        return date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


def _ticker_dirs(data_dir: Path) -> list[str]:
    d = Path(data_dir) / "analyses"
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def _realized_tier(realized: float, bear: float, base: float, bull: float) -> str:
    lo_mid = (bear + base) / 2
    hi_mid = (base + bull) / 2
    if realized <= lo_mid:
        return "bear"
    if realized >= hi_mid:
        return "bull"
    return "base"


def _brier(probs: dict, realized_tier: str) -> float:
    return sum(
        (probs[f"p_{tier}"] - (1.0 if tier == realized_tier else 0.0)) ** 2
        for tier in _TIERS
    )


def _find_realized_price(
    history_rows: list[dict], ticker: str, maturity_date: date,
) -> tuple[float | None, str | None]:
    candidates = [
        r for r in history_rows
        if r["ticker"] == ticker and _is_number(r.get("price"))
    ]
    if not candidates:
        return None, f"no history rows for {ticker}"
    best = min(candidates, key=lambda r: abs((r["date"] - maturity_date).days))
    diff = abs((best["date"] - maturity_date).days)
    if diff > REALIZED_MATCH_WINDOW_DAYS:
        return None, (
            f"nearest history row ({best['date'].isoformat()}) is {diff}d from "
            f"maturity {maturity_date.isoformat()} — outside the "
            f"±{REALIZED_MATCH_WINDOW_DAYS}d window"
        )
    return best["price"], None


def _path_stats(
    rows: list[dict], price_at_analysis,
) -> tuple[float | None, float | None]:
    if not rows or not _is_number(price_at_analysis) or price_at_analysis == 0:
        return None, None
    pct = [
        (r["price"] / price_at_analysis - 1) * 100
        for r in rows if _is_number(r.get("price"))
    ]
    if not pct:
        return None, None
    return min(pct), max(pct)


def _build_matured_entry(
    ticker: str, meta: dict, as_of: date, history_rows: list[dict],
) -> dict | None:
    memo_date = _meta_date(meta)
    if memo_date is None:
        return None
    maturity_date = memo_date + timedelta(days=MATURITY_DAYS)
    if maturity_date > as_of:
        return None  # not matured yet

    pt = meta.get("price_targets")
    if not _full_price_targets(pt):
        return None  # can't be graded; not "full" price targets

    bear, base, bull = pt["bear"], pt["base"], pt["bull"]
    probs = {k: pt[k] for k in _PROB_KEYS}
    price_at_analysis = meta.get("price_at_analysis")

    realized_price, note = _find_realized_price(history_rows, ticker, maturity_date)
    if realized_price is None:
        return {
            "ticker": ticker,
            "memo_date": memo_date.isoformat(),
            "targets": {"bear": bear, "base": base, "bull": bull},
            "probs": probs,
            "realized_price": None,
            "realized_tier": None,
            "brier": None,
            "mae_pct": None,
            "mfe_pct": None,
            "note": note,
        }

    realized_tier = _realized_tier(realized_price, bear, base, bull)
    brier = _brier(probs, realized_tier)
    window_rows = [
        r for r in history_rows
        if r["ticker"] == ticker and memo_date <= r["date"] <= maturity_date
    ]
    mae_pct, mfe_pct = _path_stats(window_rows, price_at_analysis)

    return {
        "ticker": ticker,
        "memo_date": memo_date.isoformat(),
        "targets": {"bear": bear, "base": base, "bull": bull},
        "probs": probs,
        "realized_price": realized_price,
        "realized_tier": realized_tier,
        "brier": brier,
        "mae_pct": mae_pct,
        "mfe_pct": mfe_pct,
        "note": None,
    }


def _build_tracking_entry(ticker: str, meta: dict, as_of: date, quotes: dict) -> dict | None:
    memo_date = _meta_date(meta)
    if memo_date is None:
        return None
    maturity_date = memo_date + timedelta(days=MATURITY_DAYS)
    if maturity_date <= as_of:
        return None  # already matured — belongs on the matured ledger, not tracking

    pt = meta.get("price_targets")
    if not _has_bear_base_bull(pt):
        return None

    bear, base, bull = pt["bear"], pt["base"], pt["bull"]
    q = (quotes.get("quotes") or {}).get(ticker) or {}
    current_price = q.get("price")
    if not _is_number(current_price):
        return None

    months_elapsed = round((as_of - memo_date).days / 30.4375, 1)
    if bull == bear:
        pct_between_bear_bull = None
    else:
        pct_between_bear_bull = max(0.0, min(100.0, (current_price - bear) / (bull - bear) * 100))

    return {
        "ticker": ticker,
        "memo_date": memo_date.isoformat(),
        "months_elapsed": months_elapsed,
        "current_price": current_price,
        "pct_between_bear_bull": pct_between_bear_bull,
        "above_base": current_price >= base,
    }


def _write_calibration(data_dir: Path, result: dict) -> None:
    p = Path(data_dir) / "calibration.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def calibrate(data_dir: Path, as_of: date | None = None) -> dict:
    """Grade matured memo price targets and track immature ones.

    Writes data/calibration.json and returns the same dict. Empty-safe:
    with no matured memos, aggregate is {"n": 0, "mean_brier": None} and
    tracking is still reported.
    """
    data_dir = Path(data_dir)
    as_of = as_of or date.today()

    quotes = _load_quotes(data_dir)
    history_rows = _load_history(data_dir)
    tickers = _ticker_dirs(data_dir)

    matured: list[dict] = []
    for ticker in tickers:
        for memo_path in store.list_memos(data_dir, ticker):
            meta, _ = store.parse_frontmatter(memo_path.read_text(encoding="utf-8"))
            entry = _build_matured_entry(ticker, meta, as_of, history_rows)
            if entry is not None:
                matured.append(entry)

    tracking: list[dict] = []
    for ticker in tickers:
        memo = store.latest_memo(data_dir, ticker)
        if memo is None:
            continue
        entry = _build_tracking_entry(ticker, memo["meta"], as_of, quotes)
        if entry is not None:
            tracking.append(entry)

    briers = [m["brier"] for m in matured if m["brier"] is not None]
    aggregate = {
        "n": len(briers),
        "mean_brier": (sum(briers) / len(briers)) if briers else None,
    }

    result = {
        "as_of": as_of.isoformat(),
        "matured": matured,
        "tracking": tracking,
        "aggregate": aggregate,
    }
    _write_calibration(data_dir, result)
    return result
