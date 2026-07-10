import json

import pytest

from luxtock import portfolio


def _write_watchlist(data_dir, stocks, cash_usd=None):
    wl = {"stocks": stocks}
    if cash_usd is not None:
        wl["cash_usd"] = cash_usd
    (data_dir / "watchlist.json").write_text(json.dumps(wl, ensure_ascii=False), encoding="utf-8")


def _write_quotes(data_dir, prices: dict):
    (data_dir / "quotes.json").write_text(json.dumps({
        "fetched_at": "2026-07-10T00:00:00+00:00",
        "quotes": {t: {"price": p} for t, p in prices.items()},
    }, ensure_ascii=False), encoding="utf-8")


def _write_memo(data_dir, ticker, date, bear, base=None, bull=None):
    d = data_dir / "analyses" / ticker
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{date}.md").write_text(f"""---
ticker: "{ticker}"
date: {date}
price_targets:
  bear: {bear}
  base: {base if base is not None else bear * 2}
  bull: {bull if bull is not None else bear * 3}
---
body
""", encoding="utf-8")


def _entry(ticker, holding=True, shares=None, layer="l", thesis="t"):
    e = {"ticker": ticker, "name": ticker, "thesis": thesis, "layer": layer,
         "added": "2026-07-01", "note": "", "holding": holding}
    if shares is not None:
        e["shares"] = shares
    return e


# ---------------------------------------------------------------------------
# Weight math with cash
# ---------------------------------------------------------------------------

def test_weight_math_with_cash(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=10, layer="l1", thesis="t1"),
        _entry("B", shares=5, layer="l2", thesis="t2"),
    ], cash_usd=1000)
    _write_quotes(tmp_path, {"A": 100.0, "B": 200.0})

    report = portfolio.portfolio_report(tmp_path)

    assert report["cash_usd"] == 1000
    assert report["total_value"] == pytest.approx(3000.0)  # 1000 + 1000 + 1000 cash
    pos_a = next(p for p in report["positions"] if p["ticker"] == "A")
    pos_b = next(p for p in report["positions"] if p["ticker"] == "B")
    assert pos_a["value"] == pytest.approx(1000.0)
    assert pos_b["value"] == pytest.approx(1000.0)
    assert pos_a["weight_pct"] == pytest.approx(100 / 3)
    assert pos_b["weight_pct"] == pytest.approx(100 / 3)


def test_weight_math_no_cash_field_defaults_zero(tmp_path):
    _write_watchlist(tmp_path, [_entry("A", shares=1)])
    _write_quotes(tmp_path, {"A": 50.0})
    report = portfolio.portfolio_report(tmp_path)
    assert report["cash_usd"] == 0.0
    assert report["total_value"] == pytest.approx(50.0)
    assert report["positions"][0]["weight_pct"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Unsized holdings
# ---------------------------------------------------------------------------

def test_unsized_holding_no_shares_excluded_from_weight_math(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=10, layer="l1", thesis="t1"),
        _entry("C", layer="l3", thesis="t3"),  # holding, no shares key
    ])
    _write_quotes(tmp_path, {"A": 100.0, "C": 40.0})

    report = portfolio.portfolio_report(tmp_path)

    assert report["total_value"] == pytest.approx(1000.0)  # C excluded
    pos_c = next(p for p in report["positions"] if p["ticker"] == "C")
    assert pos_c["unsized"] is True
    assert "value" not in pos_c
    assert "weight_pct" not in pos_c
    # C is still named in the output
    assert {p["ticker"] for p in report["positions"]} == {"A", "C"}


def test_unsized_holding_zero_shares_excluded(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=10),
        _entry("D", shares=0),
    ])
    _write_quotes(tmp_path, {"A": 100.0, "D": 10.0})

    report = portfolio.portfolio_report(tmp_path)

    assert report["total_value"] == pytest.approx(1000.0)
    pos_d = next(p for p in report["positions"] if p["ticker"] == "D")
    assert pos_d["unsized"] is True


def test_non_holding_entries_are_not_positions(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=10),
        _entry("E", holding=False, shares=5),
    ])
    _write_quotes(tmp_path, {"A": 100.0, "E": 100.0})

    report = portfolio.portfolio_report(tmp_path)
    assert {p["ticker"] for p in report["positions"]} == {"A"}


# ---------------------------------------------------------------------------
# Single-name flag thresholds (25% caution / 35% warning)
# ---------------------------------------------------------------------------

def _single_name_report(tmp_path, value, cash):
    _write_watchlist(tmp_path, [_entry("A", shares=1)], cash_usd=cash)
    _write_quotes(tmp_path, {"A": value})
    return portfolio.portfolio_report(tmp_path)


def test_single_name_below_caution_no_flag(tmp_path):
    report = _single_name_report(tmp_path, value=24, cash=76)  # weight 24%
    assert not [f for f in report["flags"] if f["kind"] == "single_name"]


def test_single_name_exactly_25_pct_is_caution(tmp_path):
    report = _single_name_report(tmp_path, value=25, cash=75)  # weight 25%
    single = [f for f in report["flags"] if f["kind"] == "single_name"]
    assert len(single) == 1
    assert single[0]["level"] == "caution"


def test_single_name_between_25_and_35_is_caution(tmp_path):
    report = _single_name_report(tmp_path, value=34, cash=66)  # weight 34%
    single = [f for f in report["flags"] if f["kind"] == "single_name"]
    assert single[0]["level"] == "caution"


def test_single_name_exactly_35_pct_is_warning(tmp_path):
    report = _single_name_report(tmp_path, value=35, cash=65)  # weight 35%
    single = [f for f in report["flags"] if f["kind"] == "single_name"]
    assert len(single) == 1
    assert single[0]["level"] == "warning"


# ---------------------------------------------------------------------------
# Group flag thresholds (40% caution / 60% warning)
# ---------------------------------------------------------------------------

def test_group_below_caution_no_flag(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=1, layer="L", thesis="tA"),
        _entry("B", shares=1, layer="L", thesis="tB"),
    ], cash_usd=61)  # 2x19 = 38% group weight
    _write_quotes(tmp_path, {"A": 19.0, "B": 19.0})
    report = portfolio.portfolio_report(tmp_path)
    assert not [f for f in report["flags"] if f["kind"] == "group"]


def test_group_exactly_40_pct_is_caution(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=1, layer="L", thesis="tA"),
        _entry("B", shares=1, layer="L", thesis="tB"),
    ], cash_usd=60)  # 20 + 20 = 40% of 100
    _write_quotes(tmp_path, {"A": 20.0, "B": 20.0})

    report = portfolio.portfolio_report(tmp_path)
    group_flags = [f for f in report["flags"] if f["kind"] == "group"]
    assert any(f["level"] == "caution" for f in group_flags)
    assert not any(f["level"] == "warning" for f in group_flags)
    # each individual name stays below the single-name caution threshold
    assert not [f for f in report["flags"] if f["kind"] == "single_name"]


def test_group_exactly_60_pct_is_warning(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=1, layer="L", thesis="tA"),
        _entry("B", shares=1, layer="L", thesis="tB"),
        _entry("C", shares=1, layer="L", thesis="tC"),
    ], cash_usd=40)  # 20 + 20 + 20 = 60% of 100
    _write_quotes(tmp_path, {"A": 20.0, "B": 20.0, "C": 20.0})

    report = portfolio.portfolio_report(tmp_path)
    group_flags = [f for f in report["flags"] if f["kind"] == "group" and f["detail"].startswith("layer")]
    assert any(f["level"] == "warning" for f in group_flags)
    assert report["groups"]["by_layer"]["L"] == pytest.approx(60.0)


def test_groups_report_by_layer_and_by_thesis(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=1, layer="memory", thesis="ai-inference"),
        _entry("B", shares=1, layer="power", thesis="ai-inference"),
    ])
    _write_quotes(tmp_path, {"A": 10.0, "B": 10.0})
    report = portfolio.portfolio_report(tmp_path)
    assert report["groups"]["by_layer"]["memory"] == pytest.approx(50.0)
    assert report["groups"]["by_layer"]["power"] == pytest.approx(50.0)
    assert report["groups"]["by_thesis"]["ai-inference"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Bear stress
# ---------------------------------------------------------------------------

def test_bear_stress_with_target_present(tmp_path):
    _write_watchlist(tmp_path, [_entry("A", shares=1)])
    _write_quotes(tmp_path, {"A": 100.0})
    _write_memo(tmp_path, "A", "2026-07-08", bear=80)

    report = portfolio.portfolio_report(tmp_path)
    bs = report["bear_stress"]
    assert bs["covered_tickers"] == ["A"]
    assert bs["uncovered_tickers"] == []
    assert bs["stressed_value"] == pytest.approx(80.0)
    assert bs["drawdown_pct"] == pytest.approx(20.0)


def test_bear_stress_with_missing_target_carries_current_value(tmp_path):
    _write_watchlist(tmp_path, [_entry("A", shares=1)])
    _write_quotes(tmp_path, {"A": 100.0})
    # no memo written for A at all

    report = portfolio.portfolio_report(tmp_path)
    bs = report["bear_stress"]
    assert bs["covered_tickers"] == []
    assert bs["uncovered_tickers"] == ["A"]
    assert bs["stressed_value"] == pytest.approx(100.0)  # carried at current value
    assert bs["drawdown_pct"] == pytest.approx(0.0)


def test_bear_stress_mixed_covered_and_uncovered(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=1),
        _entry("B", shares=1),
    ])
    _write_quotes(tmp_path, {"A": 100.0, "B": 100.0})
    _write_memo(tmp_path, "A", "2026-07-08", bear=50)
    # B has no memo -> uncovered, carried at current value 100

    report = portfolio.portfolio_report(tmp_path)
    bs = report["bear_stress"]
    assert bs["covered_tickers"] == ["A"]
    assert bs["uncovered_tickers"] == ["B"]
    assert bs["stressed_value"] == pytest.approx(150.0)  # 50 (stressed A) + 100 (carried B)
    assert bs["drawdown_pct"] == pytest.approx(25.0)  # (200-150)/200*100


def test_bear_stress_excludes_unsized_holdings(tmp_path):
    _write_watchlist(tmp_path, [
        _entry("A", shares=1),
        _entry("U"),  # unsized: holding but no shares
    ])
    _write_quotes(tmp_path, {"A": 100.0, "U": 100.0})
    _write_memo(tmp_path, "A", "2026-07-08", bear=80)

    report = portfolio.portfolio_report(tmp_path)
    bs = report["bear_stress"]
    assert "U" not in bs["covered_tickers"]
    assert "U" not in bs["uncovered_tickers"]


def test_bear_stress_below_20_pct_no_warning_flag(tmp_path):
    _write_watchlist(tmp_path, [_entry("A", shares=1)])
    _write_quotes(tmp_path, {"A": 100.0})
    _write_memo(tmp_path, "A", "2026-07-08", bear=81)  # drawdown 19%

    report = portfolio.portfolio_report(tmp_path)
    assert report["bear_stress"]["drawdown_pct"] == pytest.approx(19.0)
    assert not [f for f in report["flags"] if f["kind"] == "bear_stress"]


def test_bear_stress_exactly_20_pct_is_warning(tmp_path):
    _write_watchlist(tmp_path, [_entry("A", shares=1)])
    _write_quotes(tmp_path, {"A": 100.0})
    _write_memo(tmp_path, "A", "2026-07-08", bear=80)  # drawdown 20%

    report = portfolio.portfolio_report(tmp_path)
    bear_flags = [f for f in report["flags"] if f["kind"] == "bear_stress"]
    assert len(bear_flags) == 1
    assert bear_flags[0]["level"] == "warning"


def test_bear_stress_empty_portfolio_safe(tmp_path):
    _write_watchlist(tmp_path, [])
    _write_quotes(tmp_path, {})
    report = portfolio.portfolio_report(tmp_path)
    bs = report["bear_stress"]
    assert bs["stressed_value"] == 0.0
    assert bs["drawdown_pct"] == 0.0
    assert bs["covered_tickers"] == []
    assert bs["uncovered_tickers"] == []


# ---------------------------------------------------------------------------
# Empty watchlist
# ---------------------------------------------------------------------------

def test_empty_watchlist_safe_no_files(tmp_path):
    """No watchlist.json / quotes.json at all — must not crash."""
    report = portfolio.portfolio_report(tmp_path)
    assert report["positions"] == []
    assert report["cash_usd"] == 0.0
    assert report["total_value"] == 0.0
    assert report["groups"] == {"by_layer": {}, "by_thesis": {}}
    assert report["flags"] == []
    assert report["bear_stress"]["stressed_value"] == 0.0


def test_empty_watchlist_safe_empty_stocks(tmp_path):
    _write_watchlist(tmp_path, [], cash_usd=500)
    report = portfolio.portfolio_report(tmp_path)
    assert report["positions"] == []
    assert report["cash_usd"] == 500
    assert report["total_value"] == pytest.approx(500.0)
    assert report["flags"] == []
