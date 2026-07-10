"""Export: render an analysis memo as a self-contained HTML report,
optionally printed to PDF via headless Edge/Chrome.

The HTML is fully self-contained (inline CSS, no external requests) and opens
offline; PDF uses the local browser's --headless --print-to-pdf.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import markdown

from . import quant, store
from .refresh import load_json

_EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font: 13px/1.75 "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
       color: #1c2330; max-width: 860px; margin: 0 auto; padding: 40px 32px; }
h1 { font-size: 21px; letter-spacing: 1px; border-bottom: 2px solid #b8860b;
     padding-bottom: 8px; }
h2 { font-size: 16px; color: #8a6510; margin-top: 28px; border-bottom: 1px solid #e3ddce;
     padding-bottom: 4px; }
h3 { font-size: 14px; color: #444; margin-top: 20px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12.5px; }
th, td { border: 1px solid #d8d2c4; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #f4f0e6; }
code { background: #f1eee6; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
blockquote { border-left: 3px solid #b8860b; margin: 10px 0; padding: 4px 14px;
             color: #555; background: #faf8f2; }
.verdict-card { border: 1px solid #d8d2c4; border-left: 4px solid #b8860b;
                background: #faf8f2; padding: 14px 18px; margin: 18px 0;
                display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px 20px; }
.verdict-card .k { color: #8a8471; font-size: 11px; }
.verdict-card .v { font-weight: 600; }
.meta-line { color: #8a8471; font-size: 11.5px; margin-bottom: 4px; }
.disclaimer { margin-top: 32px; padding-top: 10px; border-top: 1px solid #e3ddce;
              color: #999; font-size: 11px; }
@media print { body { padding: 0; } }
"""


def _fmt_targets(pt: dict | None) -> str:
    if not isinstance(pt, dict):
        return "—"
    horizon = pt.get("horizon", "12mo")
    return (f"bear {pt.get('bear', '—')} / base {pt.get('base', '—')} / "
            f"bull {pt.get('bull', '—')} ({horizon})")


def _is_number(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _fmt0(x: object) -> str:
    """0-decimal score, or the null placeholder."""
    return f"{x:.0f}" if _is_number(x) else "—"


def _fmt1pct(x: object) -> str:
    """1-decimal percentage, or the null placeholder."""
    return f"{x:.1f}%" if _is_number(x) else "—"


def _fmt_ratio1(x: object) -> str:
    """1-decimal ratio, or the null placeholder."""
    return f"{x:.1f}" if _is_number(x) else "—"


def _fmt_coverage_pct(x: object) -> str:
    return f"{x * 100:.0f}%" if _is_number(x) else "—"


def _render_quant_section(ticker: str, quant_data: dict | None) -> str:
    """Compact 'Quant snapshot' section sourced from data/quant.json.

    Returns "" when quant.json is missing or does not carry this ticker —
    the export must then look exactly as it did before this feature.
    """
    if not isinstance(quant_data, dict):
        return ""
    entry = quant_data.get("tickers", {}).get(ticker) if ticker else None
    if not isinstance(entry, dict):
        return ""

    scores = entry.get("scores") if isinstance(entry.get("scores"), dict) else {}
    features = entry.get("features") if isinstance(entry.get("features"), dict) else {}
    components_used = scores.get("components_used")
    components_str = ", ".join(components_used) if components_used else "—"
    band = scores.get("band")

    rows = [
        ("Composite", _fmt0(scores.get("composite"))),
        ("Band", band if band else "n/a"),
        ("Coverage", _fmt_coverage_pct(scores.get("coverage"))),
        ("Components used", components_str),
        ("Valuation", _fmt0(scores.get("valuation"))),
        ("Momentum", _fmt0(scores.get("momentum"))),
        ("Positioning", _fmt0(scores.get("positioning"))),
        ("Trend", _fmt0(scores.get("trend"))),
        ("Valuation gap", _fmt1pct(features.get("valuation_gap_pct"))),
        ("EV return", _fmt1pct(features.get("ev_return_pct"))),
        ("R/R ratio", _fmt_ratio1(features.get("rr_ratio"))),
    ]
    body = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    computed_at = quant_data.get("computed_at", "—")
    return f"""<h2>Quant snapshot</h2>
<table>{body}</table>
<div class="meta-line">computed_at {computed_at} — deterministic; see framework/quant.md</div>
"""


def render_html(memo: dict, quote: dict | None, quant_data: dict | None = None) -> str:
    meta = memo["meta"]
    body_html = markdown.markdown(memo["body"], extensions=["tables", "fenced_code"])
    br = meta.get("buy_range")
    buy = f"{br[0]}–{br[1]}" if isinstance(br, list) and len(br) == 2 else "—"
    price = (quote or {}).get("price", meta.get("price_at_analysis", "—"))
    cells = [
        ("Verdict", f"{meta.get('action', '—')} (confidence: {meta.get('confidence', '—')})"),
        ("Price at analysis", f"{meta.get('price_at_analysis', '—')}"),
        ("Current price", f"{price}"),
        ("Good-buy range", buy),
        ("Price targets", _fmt_targets(meta.get("price_targets"))),
        ("Range verdict", str(meta.get("verdict", "—"))),
        ("Thesis health", str(meta.get("thesis_health", "—"))),
        ("Multiple basis", str(meta.get("multiple_basis", "—"))),
        ("Review trigger", str(meta.get("review_trigger", "—"))),
    ]
    card = "".join(f'<div><div class="k">{k}</div><div class="v">{v}</div></div>'
                   for k, v in cells)
    quant_section = _render_quant_section(meta.get("ticker", ""), quant_data)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{meta.get('ticker', '')} · {meta.get('date', '')} · Luxtock</title>
<style>{_CSS}</style></head><body>
<div class="meta-line">STOCKLUX · thesis: {meta.get('thesis', '—')} · layer:
{meta.get('layer', '—')} · {meta.get('date', '')}</div>
<div class="verdict-card">{card}</div>
{body_html}
{quant_section}<div class="disclaimer">Generated by Luxtock · Analysis, not advice · Not
investment advice · Prices and P/E are a quotes.json snapshot from export time</div>
</body></html>"""


def export_memo(data_dir: Path, ticker: str, out_dir: Path,
                pdf: bool = False) -> dict:
    """Export the ticker's latest memo. Returns {"html", "pdf" | None, "pdf_error" | None}."""
    memo = store.latest_memo(data_dir, ticker)
    if memo is None:
        raise FileNotFoundError(f"no analysis memo found for {ticker}")
    quotes = load_json(Path(data_dir) / "quotes.json") or {"quotes": {}}
    quant_data = load_json(Path(data_dir) / quant.QUANT_FILE)
    html = render_html(memo, quotes["quotes"].get(ticker), quant_data)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{ticker}-{memo['meta'].get('date', 'memo')}"
    html_path = out_dir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    result: dict = {"html": str(html_path), "pdf": None, "pdf_error": None}
    if pdf:
        pdf_path = out_dir / f"{stem}.pdf"
        result["pdf"], result["pdf_error"] = _print_to_pdf(html_path, pdf_path)
    return result


def _print_to_pdf(html_path: Path, pdf_path: Path) -> tuple[str | None, str | None]:
    """Print html_path to pdf_path via headless Edge/Chrome.

    Returns (pdf_path_str, None) on success or (None, error_message) on
    failure — the shared {"pdf", "pdf_error"} contract used by export_memo
    and (via reuse) stocklux.report.export_report. Extracted, unchanged in
    behavior, so it can be imported instead of duplicated.
    """
    browser = _find_browser()
    if browser is None:
        return None, "Edge/Chrome not found — open the HTML and print (Ctrl+P)"
    try:
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu",
             f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer",
             html_path.resolve().as_uri()],
            check=True, capture_output=True, timeout=60)
        return str(pdf_path), None
    except (subprocess.SubprocessError, OSError) as e:
        return None, f"headless print failed: {e}; open the HTML and print (Ctrl+P)"


def _find_browser() -> str | None:
    for name in ("msedge", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in _EDGE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None
