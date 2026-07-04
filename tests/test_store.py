import json

import pytest

from stocklux import store


def test_load_watchlist_missing_returns_empty(tmp_path):
    assert store.load_watchlist(tmp_path) == {"stocks": []}


def test_ensure_dirs_creates_all_subdirs(tmp_path):
    store.ensure_dirs(tmp_path)
    for sub in ("theses", "analyses", "retrospects"):
        assert (tmp_path / sub).is_dir()


def test_add_stock_returns_new_object():
    wl = {"stocks": []}
    out = store.add_stock(wl, ticker="ON", thesis="ev-adoption", layer="power-semis")
    assert wl == {"stocks": []}  # original object not mutated
    assert out["stocks"][0]["ticker"] == "ON"
    assert out["stocks"][0]["thesis"] == "ev-adoption"
    assert out["stocks"][0]["added"]  # has a date


def test_add_stock_rejects_bad_ticker():
    with pytest.raises(ValueError):
        store.add_stock({"stocks": []}, ticker="mu!", thesis="x")


def test_add_stock_rejects_duplicate():
    wl = store.add_stock({"stocks": []}, ticker="ON", thesis="x")
    with pytest.raises(ValueError):
        store.add_stock(wl, ticker="ON", thesis="x")


def test_remove_stock():
    wl = store.add_stock({"stocks": []}, ticker="ON", thesis="x")
    assert store.remove_stock(wl, "ON") == {"stocks": []}


def test_add_stock_holding_defaults_false():
    wl = store.add_stock({"stocks": []}, ticker="ON", thesis="x")
    assert wl["stocks"][0]["holding"] is False


def test_add_stock_holding_true():
    wl = store.add_stock({"stocks": []}, ticker="ON", thesis="x", holding=True)
    assert wl["stocks"][0]["holding"] is True


def test_set_holding_returns_new_object():
    wl = store.add_stock({"stocks": []}, ticker="ON", thesis="x")
    out = store.set_holding(wl, "ON", True)
    assert wl["stocks"][0]["holding"] is False  # original not mutated
    assert out["stocks"][0]["holding"] is True
    back = store.set_holding(out, "ON", False)
    assert back["stocks"][0]["holding"] is False


def test_set_holding_unknown_ticker_raises():
    with pytest.raises(ValueError):
        store.set_holding({"stocks": []}, "ZZZ", True)


def test_save_and_load_roundtrip(tmp_path):
    wl = store.add_stock({"stocks": []}, ticker="ON", thesis="x", note="中文备注 utf-8 test")
    store.save_watchlist(tmp_path, wl)
    assert store.load_watchlist(tmp_path) == wl
    # file must be UTF-8 without ASCII escaping
    raw = (tmp_path / "watchlist.json").read_text(encoding="utf-8")
    assert "中文备注 utf-8 test" in raw


VALID_MEMO = """---
ticker: "ON"
date: 2026-07-04
thesis: ev-adoption
layer: memory
action: enter
confidence: medium
buy_range: [38, 55]
multiple_basis: "8-12x cyclical EPS"
price_at_analysis: 1032
verdict: below_range
thesis_health: intact
top_risks: [ev-demand-stall, oversupply]
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
# ON full analysis

Body content.
"""


def test_parse_frontmatter():
    meta, body = store.parse_frontmatter(VALID_MEMO)
    assert meta["ticker"] == "ON"
    assert meta["buy_range"] == [38, 55]
    assert body.startswith("# ON full analysis")


def test_parse_no_frontmatter():
    meta, body = store.parse_frontmatter("just text")
    assert meta == {} and body == "just text"


def test_validate_memo_ok():
    meta, _ = store.parse_frontmatter(VALID_MEMO)
    assert store.validate_memo(meta) == []


def test_validate_memo_catches_errors():
    meta, _ = store.parse_frontmatter(VALID_MEMO)
    bad = {**meta, "action": "buy_buy_buy", "verdict": "cheap",
           "signals": {**meta["signals"], "chain": "great", "unknown_dim": "favorable"}}
    del bad["ticker"]
    errors = store.validate_memo(bad)
    joined = "\n".join(errors)
    assert "ticker" in joined
    assert "action" in joined
    assert "verdict" in joined
    assert "chain" in joined
    assert "unknown_dim" in joined


def test_latest_memo_picks_newest(tmp_path):
    d = tmp_path / "analyses" / "ON"
    d.mkdir(parents=True)
    (d / "2026-06-01.md").write_text(VALID_MEMO.replace("2026-07-04", "2026-06-01"),
                                     encoding="utf-8")
    (d / "2026-07-04.md").write_text(VALID_MEMO, encoding="utf-8")
    memo = store.latest_memo(tmp_path, "ON")
    assert str(memo["meta"]["date"]) == "2026-07-04"
    assert memo["errors"] == []


def test_latest_memo_none_when_missing(tmp_path):
    assert store.latest_memo(tmp_path, "ZZZ") is None


def test_list_theses(tmp_path):
    d = tmp_path / "theses"
    d.mkdir()
    (d / "ev-adoption.md").write_text(
        "---\nid: ev-adoption\nname: EV adoption\nstatus: intact\ncreated: 2026-07-01\n---\nthesis body",
        encoding="utf-8")
    out = store.list_theses(tmp_path)
    assert out[0]["id"] == "ev-adoption"
    assert out[0]["meta"]["status"] == "intact"
    assert out[0]["body"] == "thesis body"


def test_validate_memo_price_targets_ok():
    meta, _ = store.parse_frontmatter(VALID_MEMO)
    good = {**meta, "price_targets": {"bear": 30, "base": 48, "bull": 66,
                                       "horizon": "12mo"}}
    assert store.validate_memo(good) == []


def test_validate_memo_price_targets_bad_shape():
    meta, _ = store.parse_frontmatter(VALID_MEMO)
    assert store.validate_memo({**meta, "price_targets": "1650"})
    errors = store.validate_memo({**meta, "price_targets": {"bear": "low", "base": 1650,
                                                             "bull": 2400}})
    assert any("bear" in e for e in errors)


def test_validate_memo_holding_gates_actions():
    meta, _ = store.parse_frontmatter(VALID_MEMO)  # action: enter
    # enter is legal only when not holding
    assert store.validate_memo(meta, holding=False) == []
    assert any("holding" in e for e in store.validate_memo(meta, holding=True))
    # hold is legal only when holding
    held = {**meta, "action": "hold"}
    assert store.validate_memo(held, holding=True) == []
    assert any("holding" in e for e in store.validate_memo(held, holding=False))
    # watch_only is legal either way; holding unknown (None) checks nothing
    either = {**meta, "action": "watch_only"}
    assert store.validate_memo(either, holding=True) == []
    assert store.validate_memo(either, holding=False) == []
    assert store.validate_memo(meta) == []  # no holding context → no gate


def test_validate_memo_rejects_boolean_ticker():
    """YAML parses bare ON/NO/YES as booleans — must be caught, not silently accepted."""
    meta, _ = store.parse_frontmatter(VALID_MEMO.replace('ticker: "ON"', "ticker: ON"))
    assert meta["ticker"] is True
    assert any("ticker" in e for e in store.validate_memo(meta))
