"""refresh_data: shared refresh logic used by both the CLI and the server."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .flows import fetch_flows
from .quotes import fetch_quotes
from .store import load_watchlist


def load_json(path: Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_data(data_dir: Path) -> dict:
    data_dir = Path(data_dir)
    tickers = [s["ticker"] for s in load_watchlist(data_dir)["stocks"]]
    quotes = fetch_quotes(tickers, load_json(data_dir / "quotes.json"))
    flows = fetch_flows(tickers, load_json(data_dir / "flows.json"))
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_json(data_dir / "quotes.json", quotes)
    _write_json(data_dir / "flows.json", flows)
    return quotes


def quotes_stale(data_dir: Path, hours: float = 12) -> bool:
    q = load_json(Path(data_dir) / "quotes.json")
    if not q or not q.get("fetched_at"):
        return True
    fetched = datetime.fromisoformat(q["fetched_at"])
    return (datetime.now(timezone.utc) - fetched).total_seconds() > hours * 3600
