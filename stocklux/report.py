"""Desk-level report: one self-contained HTML document combining quant
setup scores, desk verdicts, active alerts and calibration into a single
analysis read for the whole book. This is an analysis document, not a
reflection of the owner's positions -- it carries no sizing, weights, or
holdings data.

Reuses stocklux.export's machinery (inline CSS, formatting helpers, and the
headless Edge/Chrome PDF-printing path) by import rather than duplicating
it. Pure orchestration over the other modules' public functions — no new
scoring or business logic lives here.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import calibrate, check, quant, store
from .export import (
    _CSS,
    _fmt0,
    _fmt1pct,
    _fmt_coverage_pct,
    _fmt_ratio1,
    _is_number,
    _print_to_pdf,
)
from .refresh import load_json

_REPORT_CSS = """
.flag-warning { color: #c0392b; font-weight: 600; margin: 4px 0; }
.flag-caution { color: #b8860b; font-weight: 600; margin: 4px 0; }
.flag-info { color: #555; margin: 4px 0; }
"""


def _fmt_money(x: object) -> str:
    return f"${x:,.2f}" if _is_number(x) else "—"


def _flag_css_class(level: str) -> str:
    if level == "warning":
        return "flag-warning"
    if level == "caution":
        return "flag-caution"
    return "flag-info"


# ---------------------------------------------------------------------------
# 1. Header
# ---------------------------------------------------------------------------


def _render_header(quotes_data: dict, quant_data: dict | None) -> str:
    fetched_at = quotes_data.get("fetched_at", "—")
    computed_at = quant_data.get("computed_at", "—") if isinstance(quant_data, dict) else "—"
    return f"""<h1>Desk Report {date.today().isoformat()}</h1>
<div class="meta-line">quotes.json fetched_at {fetched_at} · quant.json computed_at {computed_at}</div>
"""


# ---------------------------------------------------------------------------
# 2. Quant setup
# ---------------------------------------------------------------------------


def _quant_row(ticker: str, entry: dict) -> str:
    features = entry.get("features") if isinstance(entry.get("features"), dict) else {}
    scores = entry.get("scores") if isinstance(entry.get("scores"), dict) else {}
    band = scores.get("band")
    return (
        "<tr>"
        f"<td>{ticker}</td>"
        f"<td>{_fmt_money(features.get('price'))}</td>"
        f"<td>{_fmt1pct(features.get('valuation_gap_pct'))}</td>"
        f"<td>{_fmt1pct(features.get('ev_return_pct'))}</td>"
        f"<td>{_fmt_ratio1(features.get('rr_ratio'))}</td>"
        f"<td>{_fmt1pct(features.get('paired_premium_pct'))}</td>"
        f"<td>{_fmt0(scores.get('valuation'))}</td>"
        f"<td>{_fmt0(scores.get('momentum'))}</td>"
        f"<td>{_fmt0(scores.get('positioning'))}</td>"
        f"<td>{_fmt0(scores.get('trend'))}</td>"
        f"<td>{_fmt0(scores.get('composite'))}</td>"
        f"<td>{band if band else 'n/a'}</td>"
        f"<td>{_fmt_coverage_pct(scores.get('coverage'))}</td>"
        "</tr>"
    )


def _render_quant_setup_section(quant_data: dict | None) -> str:
    """Returns "" (section omitted entirely) when quant.json is missing or
    malformed -- load_json already collapses both cases to None."""
    if not isinstance(quant_data, dict):
        return ""
    tickers = quant_data.get("tickers")
    if not isinstance(tickers, dict) or not tickers:
        return ""
    header = (
        "<tr><th>Ticker</th><th>Price</th><th>Val gap</th><th>EV return</th>"
        "<th>R/R</th><th>Paired premium</th><th>Valuation</th><th>Momentum</th>"
        "<th>Positioning</th><th>Trend</th><th>Composite</th><th>Band</th>"
        "<th>Coverage</th></tr>"
    )
    rows = "".join(_quant_row(t, tickers[t]) for t in sorted(tickers))
    return f"<h2>Quant setup</h2><table>{header}{rows}</table>\n"


# ---------------------------------------------------------------------------
# 3. Desk verdicts
# ---------------------------------------------------------------------------


def _fmt_targets_with_probs(pt: dict | None) -> str:
    if not isinstance(pt, dict):
        return "—"
    bear, base, bull = pt.get("bear", "—"), pt.get("base", "—"), pt.get("bull", "—")
    p_bear, p_base, p_bull = pt.get("p_bear"), pt.get("p_base"), pt.get("p_bull")
    if _is_number(p_bear) and _is_number(p_base) and _is_number(p_bull):
        return (f"bear {bear} ({p_bear * 100:.0f}%) / base {base} ({p_base * 100:.0f}%) / "
                f"bull {bull} ({p_bull * 100:.0f}%)")
    return f"bear {bear} / base {base} / bull {bull}"


def _verdict_row(ticker: str, meta: dict) -> str:
    br = meta.get("buy_range")
    buy_range = f"{br[0]}–{br[1]}" if isinstance(br, list) and len(br) == 2 else "—"
    targets = _fmt_targets_with_probs(meta.get("price_targets"))
    return (
        "<tr>"
        f"<td>{ticker}</td>"
        f"<td>{meta.get('date', '—')}</td>"
        f"<td>{meta.get('action', '—')}</td>"
        f"<td>{meta.get('confidence', '—')}</td>"
        f"<td>{meta.get('verdict', '—')}</td>"
        f"<td>{buy_range}</td>"
        f"<td>{targets}</td>"
        f"<td>{meta.get('price_at_analysis', '—')}</td>"
        f"<td>{meta.get('thesis_health', '—')}</td>"
        "</tr>"
    )


def _render_verdicts_section(data_dir: Path) -> str:
    wl = store.load_watchlist(data_dir)
    rows = []
    for stock in wl.get("stocks", []):
        ticker = stock["ticker"]
        memo = store.latest_memo(data_dir, ticker)
        if memo is None:
            continue
        rows.append(_verdict_row(ticker, memo["meta"]))

    if not rows:
        return "<h2>Desk verdicts</h2><p>no desk verdicts</p>\n"

    header = (
        "<tr><th>Ticker</th><th>Memo date</th><th>Action</th><th>Confidence</th>"
        "<th>Verdict</th><th>Buy range</th><th>Bear/Base/Bull</th>"
        "<th>Price at analysis</th><th>Thesis health</th></tr>"
    )
    return f"<h2>Desk verdicts</h2><table>{header}{''.join(rows)}</table>\n"


# ---------------------------------------------------------------------------
# 4. Active alerts
# ---------------------------------------------------------------------------


def _render_alerts_section(data_dir: Path) -> str:
    """Per-ticker price alerts only. "PORTFOLIO" alerts are derived from the
    owner's sizing (portfolio.portfolio_report flags), not from analysis, so
    they are filtered out of this analysis document."""
    result = check.run_checks(data_dir)
    alerts = [a for a in result.get("alerts", []) if a["ticker"] != "PORTFOLIO"]
    if not alerts:
        return "<h2>Active alerts</h2><p>no alerts</p>\n"
    lines = (
        f'<div class="{_flag_css_class(a["level"])}">[{a["level"]}] {a["ticker"]} · '
        f'{a["kind"]} · {a["detail"]}</div>'
        for a in alerts
    )
    return f"<h2>Active alerts</h2>{''.join(lines)}\n"


# ---------------------------------------------------------------------------
# 5. Calibration
# ---------------------------------------------------------------------------


def _tracking_row(t: dict) -> str:
    above = t.get("above_base")
    above_str = "above" if above is True else "below" if above is False else "—"
    return (
        "<tr>"
        f"<td>{t.get('ticker', '—')}</td>"
        f"<td>{t.get('memo_date', '—')}</td>"
        f"<td>{t.get('months_elapsed', '—')}</td>"
        f"<td>{_fmt1pct(t.get('pct_between_bear_bull'))}</td>"
        f"<td>{above_str}</td>"
        "</tr>"
    )


def _render_calibration_section(data_dir: Path) -> str:
    result = calibrate.calibrate(data_dir)
    aggregate = result.get("aggregate", {})
    n = aggregate.get("n", 0)
    mean_brier = aggregate.get("mean_brier")
    mean_brier_str = f"{mean_brier:.3f}" if _is_number(mean_brier) else "—"
    agg_html = f'<div class="meta-line">n={n} · mean Brier {mean_brier_str}</div>'

    tracking = result.get("tracking", [])
    if tracking:
        header = (
            "<tr><th>Ticker</th><th>Memo date</th><th>Months elapsed</th>"
            "<th>Bear→bull percentile</th><th>Vs base</th></tr>"
        )
        tracking_html = f"<table>{header}{''.join(_tracking_row(t) for t in tracking)}</table>"
    else:
        tracking_html = "<p>no tracking entries</p>"

    return f"<h2>Calibration</h2>{agg_html}{tracking_html}\n"


# ---------------------------------------------------------------------------
# 6. Footer
# ---------------------------------------------------------------------------


def _render_footer() -> str:
    return (
        '<div class="disclaimer">Generated by Luxtock — deterministic data + recorded '
        "analyst inferences; see framework/quant.md and framework/operating-contract.md</div>"
    )


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def build_report(data_dir: Path) -> str:
    """Render the desk-level report as a self-contained HTML document. This
    is an analysis document, not a reflection of the owner's positions --
    it carries no portfolio/sizing section. Every section degrades
    gracefully on missing/empty data; see the module-level sections above
    for the per-section contract."""
    data_dir = Path(data_dir)
    quotes_data = load_json(data_dir / "quotes.json") or {}
    quant_data = load_json(data_dir / quant.QUANT_FILE)

    sections = "\n".join([
        _render_header(quotes_data, quant_data),
        _render_quant_setup_section(quant_data),
        _render_verdicts_section(data_dir),
        _render_alerts_section(data_dir),
        _render_calibration_section(data_dir),
        _render_footer(),
    ])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Desk Report · {date.today().isoformat()} · Luxtock</title>
<style>{_CSS}{_REPORT_CSS}</style></head><body>
{sections}
</body></html>"""


def export_report(data_dir: Path, out_dir: Path, pdf: bool = False) -> dict:
    """Write output/desk-<YYYY-MM-DD>.html (today's date), optionally
    printed to PDF via the same headless Edge/Chrome path export.py uses.

    Returns {"html", "pdf" | None, "pdf_error" | None} -- same contract as
    export.export_memo.
    """
    data_dir = Path(data_dir)
    html = build_report(data_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"desk-{date.today().isoformat()}"
    html_path = out_dir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")

    result: dict = {"html": str(html_path), "pdf": None, "pdf_error": None}
    if pdf:
        pdf_path = out_dir / f"{stem}.pdf"
        result["pdf"], result["pdf_error"] = _print_to_pdf(html_path, pdf_path)
    return result
