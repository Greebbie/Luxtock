"""Export tests: self-contained HTML rendering (PDF needs a local browser; not unit-tested)."""
from pathlib import Path

import pytest

from stocklux.export import export_memo, render_html
from stocklux import store


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
