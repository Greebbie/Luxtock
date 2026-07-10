"""Export tests: self-contained HTML rendering (PDF needs a local browser; not unit-tested)."""
import json
from pathlib import Path

import pytest

from luxtock.export import export_memo, render_html
from luxtock import store


def test_export_memo_writes_selfcontained_html(data_dir, tmp_path):
    out = tmp_path / "out"
    result = export_memo(data_dir, "ON", out, pdf=False)
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert result["pdf"] is None
    assert "<style>" in html                      # inline CSS, self-contained
    assert "ON" in html and "enter" in html       # verdict card content
    assert "38–55" in html                    # buy range
    assert "Analysis, not advice" in html
    assert "http" not in html.split("</style>")[1].split("<div")[0]  # no external resources


def test_export_missing_memo_raises(data_dir):
    with pytest.raises(FileNotFoundError):
        export_memo(data_dir, "ZZZZ", data_dir / "out", pdf=False)


def test_render_html_markdown_table():
    memo = {"meta": {"ticker": "T", "date": "2026-07-04", "action": "watch_only",
                     "confidence": "low", "price_at_analysis": 10,
                     "price_targets": {"bear": 8, "base": 12, "bull": 15,
                                       "horizon": "12mo"}},
            "body": "| a | b |\n|---|---|\n| 1 | 2 |", "errors": []}
    html = render_html(memo, {"price": 11.0})
    assert "<table>" in html and "<td>1</td>" in html   # tables extension works
    assert "bear 8" in html and "base 12" in html


# ---------------------------------------------------------------------------
# quant snapshot section
# ---------------------------------------------------------------------------


def _quant_payload(ticker: str, *, coverage=0.8636, composite=85.3, band="strong") -> dict:
    return {
        "computed_at": "2026-07-10T18:52:07.837756+00:00",
        "tickers": {
            ticker: {
                "features": {
                    "valuation_gap_pct": -22.111718749999998,
                    "ev_return_pct": 28.639778528942685,
                    "rr_ratio": 0.5114492279013526,
                },
                "scores": {
                    "valuation": 99.31988926447134,
                    "momentum": 94.228,
                    "positioning": 61.9644,
                    "trend": 63.666666666666664,
                    "composite": composite,
                    "band": band,
                    "coverage": coverage,
                    "components_used": ["momentum", "positioning", "trend", "valuation"],
                },
            }
        },
    }


def test_export_appends_quant_section_when_ticker_present(data_dir, tmp_path):
    (data_dir / "quant.json").write_text(
        json.dumps(_quant_payload("ON")), encoding="utf-8")
    out = tmp_path / "out"
    result = export_memo(data_dir, "ON", out, pdf=False)
    html = Path(result["html"]).read_text(encoding="utf-8")

    assert "Quant snapshot" in html
    assert "<td>85</td>" in html          # composite, 0 decimals
    assert "<td>strong</td>" in html      # band
    assert "<td>86%</td>" in html         # coverage as %
    assert "momentum, positioning, trend, valuation" in html  # components_used
    assert "<td>99</td>" in html          # valuation sub-score, 0 decimals
    assert "-22.1%" in html               # valuation_gap_pct, 1 decimal
    assert "28.6%" in html                # ev_return_pct, 1 decimal
    assert "<td>0.5</td>" in html         # rr_ratio, 1 decimal
    assert "computed_at 2026-07-10T18:52:07.837756+00:00" in html
    assert "deterministic; see framework/quant.md" in html


def test_export_no_quant_section_when_quant_json_missing(data_dir, tmp_path):
    out = tmp_path / "out"
    result = export_memo(data_dir, "ON", out, pdf=False)
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "Quant snapshot" not in html


def test_export_no_quant_section_when_ticker_absent_from_quant_json(data_dir, tmp_path):
    (data_dir / "quant.json").write_text(
        json.dumps(_quant_payload("SOME_OTHER_TICKER")), encoding="utf-8")
    out = tmp_path / "out"
    result = export_memo(data_dir, "ON", out, pdf=False)
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "Quant snapshot" not in html


def test_export_no_quant_section_when_quant_json_malformed(data_dir, tmp_path):
    (data_dir / "quant.json").write_text("{not valid json", encoding="utf-8")
    out = tmp_path / "out"
    result = export_memo(data_dir, "ON", out, pdf=False)
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "Quant snapshot" not in html


def test_export_html_identical_shape_without_quant_json(data_dir, tmp_path):
    """No quant.json anywhere in scope -> export is byte-identical to the
    pre-quant-section behavior (no section, no stray whitespace/markup)."""
    without = tmp_path / "out-without"
    result_without = export_memo(data_dir, "ON", without, pdf=False)
    html_without = Path(result_without["html"]).read_text(encoding="utf-8")

    (data_dir / "quant.json").write_text(
        json.dumps(_quant_payload("SOME_OTHER_TICKER")), encoding="utf-8")
    with_absent_ticker = tmp_path / "out-with"
    result_with = export_memo(data_dir, "ON", with_absent_ticker, pdf=False)
    html_with = Path(result_with["html"]).read_text(encoding="utf-8")

    assert html_without == html_with


def test_render_html_quant_section_falls_back_to_placeholders_for_nulls():
    memo = {"meta": {"ticker": "T", "date": "2026-07-04", "action": "watch_only",
                     "confidence": "low", "price_at_analysis": 10},
            "body": "body", "errors": []}
    quant_data = {
        "computed_at": "2026-07-10T00:00:00+00:00",
        "tickers": {"T": {
            "features": {"valuation_gap_pct": None, "ev_return_pct": None, "rr_ratio": None},
            "scores": {"valuation": None, "momentum": None, "positioning": None,
                       "trend": None, "composite": None, "band": None,
                       "coverage": 0.0, "components_used": []},
        }},
    }
    html = render_html(memo, None, quant_data)
    assert "Quant snapshot" in html
    assert "<td>n/a</td>" in html   # band
    assert "<td>0%</td>" in html    # coverage
    assert "<td>—</td>" in html     # composite / sub-scores / components_used all fall back


def test_render_html_quant_section_absent_without_quant_data():
    memo = {"meta": {"ticker": "T", "date": "2026-07-04", "action": "watch_only",
                     "confidence": "low", "price_at_analysis": 10},
            "body": "body", "errors": []}
    html = render_html(memo, None, None)
    assert "Quant snapshot" not in html
