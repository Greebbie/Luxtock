"""Flow-data fetcher + volume/OBV accumulation signals. Deterministic, no LLM.

Honesty note (for humans and agents reading this data): these are all proxy
signals — 13F lags ~45 days, short interest updates biweekly, no dark-pool or
realtime flow. "Smart money quietly accumulating" is always an inference.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

_EMPTY_SIGNALS = {
    "up_down_volume_ratio": None,
    "obv_slope_20": None,
    "obv_slope_60": None,
    "accumulation_hint": False,
}

_FLOW_FIELDS = {
    "shares_short": "sharesShort",
    "short_pct_float": "shortPercentOfFloat",
    "short_ratio": "shortRatio",
    "inst_pct": "heldPercentInstitutions",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_volume_signals(history: pd.DataFrame) -> dict:
    df = history.tail(120).copy()
    if len(df) < 60 or "Close" not in df or "Volume" not in df:
        return dict(_EMPTY_SIGNALS)
    delta = df["Close"].diff()
    up_vol = df.loc[delta > 0, "Volume"].mean()
    down_vol = df.loc[delta < 0, "Volume"].mean()
    ratio = (
        round(float(up_vol / down_vol), 2)
        if down_vol and not pd.isna(down_vol) and not pd.isna(up_vol)
        else None
    )

    direction = delta.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (df["Volume"] * direction).fillna(0).cumsum()
    mean_vol = float(df["Volume"].tail(60).mean())

    def slope(n: int) -> float:
        s = obv.tail(n).to_numpy(dtype=float)
        k = np.polyfit(np.arange(len(s)), s, 1)[0]
        return round(float(k / mean_vol), 3)

    s20, s60 = slope(20), slope(60)
    px_change_60 = float(df["Close"].iloc[-1] / df["Close"].iloc[-60] - 1)
    hint = abs(px_change_60) < 0.05 and s20 > 0 and (ratio or 0) > 1.2
    return {
        "up_down_volume_ratio": ratio,
        "obv_slope_20": s20,
        "obv_slope_60": s60,
        "accumulation_hint": bool(hint),
    }


def _fetch_one(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info  # raises on failure; fetch_flows handles the fallback
    flow = {k: info.get(v) for k, v in _FLOW_FIELDS.items()}
    flow.update({"insider_net_6m": None, "put_call_oi_ratio": None,
                 "signals": dict(_EMPTY_SIGNALS), "stale": False, "fetched_at": _now()})
    try:
        ins = t.insider_transactions
        if ins is not None and not ins.empty and {"Shares", "Text"} <= set(ins.columns):
            buys = ins.loc[ins["Text"].str.contains("Buy", case=False, na=False), "Shares"].sum()
            sells = ins.loc[ins["Text"].str.contains("Sale", case=False, na=False), "Shares"].sum()
            flow["insider_net_6m"] = int(buys - sells)
    except Exception:
        pass
    try:
        expirations = t.options
        if expirations:
            chain = t.option_chain(expirations[0])
            call_oi = float(chain.calls["openInterest"].sum())
            put_oi = float(chain.puts["openInterest"].sum())
            if call_oi:
                flow["put_call_oi_ratio"] = round(put_oi / call_oi, 2)
    except Exception:
        pass
    try:
        flow["signals"] = compute_volume_signals(t.history(period="6mo"))
    except Exception:
        pass
    return flow


def fetch_flows(tickers: list[str], prev: dict | None = None) -> dict:
    prev_flows = (prev or {}).get("flows", {})
    flows_out: dict = {}
    for t in tickers:
        try:
            flows_out[t] = _fetch_one(t)
        except Exception:
            # Schema-complete fallback: normalize to all flow keys
            prev_f = prev_flows.get(t) or {}
            old = {k: prev_f.get(k) for k in _FLOW_FIELDS}
            old["insider_net_6m"] = prev_f.get("insider_net_6m")
            old["put_call_oi_ratio"] = prev_f.get("put_call_oi_ratio")
            # Ensure signals is always a dict
            sig = prev_f.get("signals")
            old["signals"] = sig if isinstance(sig, dict) else dict(_EMPTY_SIGNALS)
            old["fetched_at"] = prev_f.get("fetched_at")
            old["stale"] = True
            flows_out[t] = old
    return {"fetched_at": _now(), "flows": flows_out}
