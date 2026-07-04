import json

import pytest

MEMO_TEXT = """---
ticker: "ON"
date: 2026-06-01
thesis: ev-adoption
layer: memory
action: enter
confidence: medium
buy_range: [38, 55]
multiple_basis: "8-12x cyclical EPS"
price_at_analysis: 900
verdict: below_range
thesis_health: intact
top_risks: [oversupply]
review_trigger: "EV unit sales turn negative YoY"
signals:
  chain: favorable
  narrative: favorable
  fundamentals: favorable
  valuation: favorable
  flows: neutral
  sentiment: unfavorable
  competition: neutral
  macro: no_signal
---
# ON analysis body
"""

BROKEN_MEMO = """---
ticker: CHPT
date: 2026-06-15
action: yolo
---
broken memo
"""


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    (d / "theses").mkdir(parents=True)
    (d / "analyses" / "ON").mkdir(parents=True)
    (d / "analyses" / "CHPT").mkdir(parents=True)
    (d / "watchlist.json").write_text(json.dumps({"stocks": [
        {"ticker": "ON", "name": "onsemi", "thesis": "ev-adoption",
         "layer": "power-semis", "added": "2026-07-01", "note": ""},
        {"ticker": "CHPT", "name": "ChargePoint", "thesis": "ev-adoption",
         "layer": "charging", "added": "2026-07-01", "note": ""},
    ]}, ensure_ascii=False), encoding="utf-8")
    (d / "quotes.json").write_text(json.dumps({
        "fetched_at": "2026-07-04T00:00:00+00:00",
        "quotes": {
            "ON": {"price": 1032.0, "ttm_pe": 23.3, "fwd_pe": 7.2, "stale": False},
            "CHPT": {"price": 236.5, "ttm_pe": 20.2, "fwd_pe": 20.4, "stale": False},
        }}, ensure_ascii=False), encoding="utf-8")
    (d / "flows.json").write_text(json.dumps({
        "fetched_at": "2026-07-04T00:00:00+00:00",
        "flows": {"ON": {"short_pct_float": 0.02, "stale": False,
                          "signals": {"accumulation_hint": True}}}},
        ensure_ascii=False), encoding="utf-8")
    (d / "theses" / "ev-adoption.md").write_text(
        "---\nid: ev-adoption\nname: EV adoption\nstatus: intact\ncreated: 2026-07-01\n---\nthesis body",
        encoding="utf-8")
    (d / "analyses" / "ON" / "2026-06-01.md").write_text(MEMO_TEXT, encoding="utf-8")
    (d / "analyses" / "CHPT" / "2026-06-15.md").write_text(BROKEN_MEMO, encoding="utf-8")
    return d
