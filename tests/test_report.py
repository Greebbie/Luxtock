"""Desk-level report tests: whole-portfolio HTML render + export.

Follows tests/test_export.py / test_portfolio.py conventions: local
_write_* helpers building watchlist.json / quotes.json / memo fixtures
directly under tmp_path (data_dir), no shared conftest fixture (the repo's
`data_dir` fixture already carries an unrelated ON/CHPT fixture).
"""
import json
from datetime import date, timedelta
from pathlib import Path

from luxtock import check, report

TODAY = date.today()


def _write_watchlist(data_dir, stocks, cash_usd=None):
    wl = {"stocks": stocks}
    if cash_usd is not None:
        wl["cash_usd"] = cash_usd
    (data_dir / "watchlist.json").write_text(json.dumps(wl, ensure_ascii=False), encoding="utf-8")


def _write_quotes(data_dir, prices: dict, fetched_at="2026-07-10T19:00:00+00:00"):
    (data_dir / "quotes.json").write_text(json.dumps({
        "fetched_at": fetched_at,
        "quotes": {t: {"price": p} for t, p in prices.items()},
    }, ensure_ascii=False), encoding="utf-8")


def _entry(ticker, holding=True, shares=None, layer="l", thesis="t"):
    e = {"ticker": ticker, "name": ticker, "thesis": thesis, "layer": layer,
         "added": "2026-07-01", "note": "", "holding": holding}
    if shares is not None:
        e["shares"] = shares
    return e


def _write_memo(data_dir, ticker, memo_date, *, action="hold", confidence="high",
                 buy_range=None, price_targets=None, price_at_analysis=100,
                 verdict="in_range", thesis_health="intact"):
    d = data_dir / "analyses" / ticker
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f'ticker: "{ticker}"',
        f"date: {memo_date.isoformat()}",
        "thesis: t",
        f"action: {action}",
        f"confidence: {confidence}",
    ]
    if buy_range is not None:
        lines.append(f"buy_range: [{buy_range[0]}, {buy_range[1]}]")
    if price_targets is not None:
        lines.append("price_targets:")
        for k, v in price_targets.items():
            lines.append(f"  {k}: {v}")
    lines += [
        f"price_at_analysis: {price_at_analysis}",
        f"verdict: {verdict}",
        f"thesis_health: {thesis_health}",
        'review_trigger: "test trigger"',
        "---",
        f"# {ticker} memo body",
    ]
    (d / f"{memo_date.isoformat()}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _quant_payload(entries: dict) -> dict:
    """entries: {ticker: {...overrides...}}"""
    tickers = {}
    for ticker, over in entries.items():
        tickers[ticker] = {
            "features": {
                "price": over.get("price", 100.0),
                "valuation_gap_pct": over.get("valuation_gap_pct", -22.111718749999998),
                "ev_return_pct": over.get("ev_return_pct", 28.639778528942685),
                "rr_ratio": over.get("rr_ratio", 0.5114492279013526),
                "paired_premium_pct": over.get("paired_premium_pct", None),
            },
            "scores": {
                "valuation": over.get("valuation", 99.31988926447134),
                "momentum": over.get("momentum", 94.228),
                "positioning": over.get("positioning", 61.9644),
                "trend": over.get("trend", 63.666666666666664),
                "composite": over.get("composite", 85.3),
                "band": over.get("band", "strong"),
                "coverage": over.get("coverage", 0.8636),
                "components_used": ["momentum", "positioning", "trend", "valuation"],
            },
        }
    return {"computed_at": "2026-07-10T18:52:07.837756+00:00", "tickers": tickers}


def _full_data_dir(tmp_path, *, with_quant=True) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    _write_watchlist(d, [
        _entry("A", shares=10, layer="L1", thesis="T1"),
        _entry("B", shares=5, layer="L2", thesis="T2"),
    ], cash_usd=1000)
    _write_quotes(d, {"A": 100.0, "B": 200.0})
    memo_date = TODAY - timedelta(days=10)
    _write_memo(
        d, "A", memo_date, action="hold", confidence="high",
        buy_range=[90, 120],
        price_targets={"bear": 100, "base": 110, "bull": 150,
                        "p_bear": 0.3, "p_base": 0.4, "p_bull": 0.3, "horizon": "12mo"},
        price_at_analysis=95, verdict="in_range", thesis_health="intact",
    )
    _write_memo(
        d, "B", memo_date, action="hold", confidence="medium",
        buy_range=[150, 250],
        price_targets={"bear": 150, "base": 220, "bull": 300,
                        "p_bear": 0.2, "p_base": 0.5, "p_bull": 0.3, "horizon": "12mo"},
        price_at_analysis=190, verdict="in_range", thesis_health="weakening",
    )
    if with_quant:
        (d / "quant.json").write_text(
            json.dumps(_quant_payload({
                "A": {"price": 100.0, "composite": 85.3, "band": "strong", "coverage": 0.8636},
                "B": {"price": 200.0, "composite": 55.0, "band": "fair", "coverage": 0.5},
            })), encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# build_report: full data
# ---------------------------------------------------------------------------

def test_full_render_has_all_sections_and_numbers(tmp_path):
    d = _full_data_dir(tmp_path)
    html = report.build_report(d)

    # self-contained
    assert "<style>" in html

    # 1. Header
    assert f"Desk Report {TODAY.isoformat()}" in html
    assert "2026-07-10T19:00:00+00:00" in html  # quotes fetched_at
    assert "2026-07-10T18:52:07.837756+00:00" in html  # quant computed_at

    # 2. Portfolio section is removed entirely -- this is an analysis
    # document, not a reflection of the owner's positions.
    assert "Portfolio" not in html
    assert "Bear-stress" not in html

    # 3. Quant setup
    assert "Quant setup" in html
    assert "<td>85</td>" in html  # A composite
    assert "<td>strong</td>" in html
    assert "<td>55</td>" in html  # B composite
    assert "<td>fair</td>" in html

    # 4. Desk verdicts
    assert "Desk verdicts" in html
    assert "90–120" in html  # A buy range
    assert "bear 100 (30%) / base 110 (40%) / bull 150 (30%)" in html  # A targets w/ probs
    assert "weakening" in html  # B thesis_health

    # 5. Active alerts (A's price 100 == bear 100 -> through_bear warning)
    assert "Active alerts" in html
    assert "through_bear" in html
    assert "flag-warning" in html

    # 6. Calibration
    assert "Calibration" in html
    assert "n=0" in html  # nothing matured yet
    assert "A" in html  # tracking row ticker

    # 7. Footer
    assert "Generated by Luxtock" in html
    assert "framework/quant.md" in html
    assert "framework/operating-contract.md" in html


def test_portfolio_alerts_are_filtered_from_active_alerts(tmp_path):
    """_full_data_dir sizes A and B at ~33.3% each (>= 25% caution
    threshold), which trips portfolio.portfolio_report's single_name flag
    and, via check.run_checks, surfaces as a ticker="PORTFOLIO" alert. The
    desk report is an analysis document, not a reflection of the owner's
    sizing, so that alert must never reach the rendered page even though
    the underlying flag condition is genuinely tripped."""
    d = _full_data_dir(tmp_path)

    # sanity: the underlying check does produce a PORTFOLIO alert here
    alerts = check.run_checks(d)["alerts"]
    assert any(a["ticker"] == "PORTFOLIO" for a in alerts)

    html = report.build_report(d)
    assert "PORTFOLIO" not in html
    assert "single_name" not in html
    assert "33.3% of portfolio" not in html
    # the per-ticker alert from the same fixture still renders
    assert "through_bear" in html


def test_missing_quant_json_skips_section_but_renders_rest(tmp_path):
    d = _full_data_dir(tmp_path, with_quant=False)
    html = report.build_report(d)
    assert "Quant setup" not in html
    assert "Portfolio" not in html
    assert "Desk verdicts" in html
    assert "Active alerts" in html
    assert "Calibration" in html
    assert "Generated by Luxtock" in html


def test_malformed_quant_json_skips_section_safely(tmp_path):
    d = _full_data_dir(tmp_path, with_quant=False)
    (d / "quant.json").write_text("{not valid json", encoding="utf-8")
    html = report.build_report(d)
    assert "Quant setup" not in html


# ---------------------------------------------------------------------------
# empty / missing data
# ---------------------------------------------------------------------------

def test_empty_watchlist_and_missing_files_safe(tmp_path):
    """No data files at all under data_dir -- must not crash."""
    d = tmp_path / "data"
    d.mkdir()
    html = report.build_report(d)
    assert "Portfolio" not in html
    assert "no desk verdicts" in html
    assert "no alerts" in html
    assert "n=0" in html
    assert "Quant setup" not in html
    assert "Generated by Luxtock" in html


def test_empty_watchlist_stocks_list_safe(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    _write_watchlist(d, [], cash_usd=500)
    html = report.build_report(d)
    assert "Portfolio" not in html
    assert "no desk verdicts" in html


# ---------------------------------------------------------------------------
# export_report
# ---------------------------------------------------------------------------

def test_export_report_writes_html_with_todays_date_in_name(tmp_path):
    d = _full_data_dir(tmp_path)
    out = tmp_path / "out"
    result = report.export_report(d, out, pdf=False)

    expected_path = out / f"desk-{TODAY.isoformat()}.html"
    assert Path(result["html"]) == expected_path
    assert expected_path.exists()
    html = expected_path.read_text(encoding="utf-8")
    assert f"Desk Report {TODAY.isoformat()}" in html


def test_export_report_pdf_false_returns_pdf_none(tmp_path):
    d = _full_data_dir(tmp_path)
    out = tmp_path / "out"
    result = report.export_report(d, out, pdf=False)
    assert result["pdf"] is None
    assert result["pdf_error"] is None
    assert set(result.keys()) == {"html", "pdf", "pdf_error"}


def test_export_report_empty_data_safe(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    out = tmp_path / "out"
    result = report.export_report(d, out, pdf=False)
    assert Path(result["html"]).exists()
