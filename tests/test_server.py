import json

from fastapi.testclient import TestClient

from stocklux import store
from stocklux.server import build_overview, create_app


def client(data_dir):
    return TestClient(create_app(data_dir))


def test_overview_joins_quote_memo_staleness(data_dir):
    ov = build_overview(data_dir)
    mu = next(r for r in ov["rows"] if r["ticker"] == "ON")
    assert mu["quote"]["price"] == 1032.0
    assert mu["memo"]["action"] == "enter"
    assert mu["memo"]["buy_range"] == [38, 55]
    # (1032/900 - 1) * 100 = 14.7
    assert mu["staleness"]["price_deviation_pct"] == 14.7
    # analysis date 2026-06-01: days only grows, so >30 holds forever
    assert mu["staleness"]["needs_reanalysis"] is True
    assert ov["quotes_fetched_at"] == "2026-07-04T00:00:00+00:00"


def test_overview_flags_broken_memo_without_crashing(data_dir):
    ov = build_overview(data_dir)
    ceg = next(r for r in ov["rows"] if r["ticker"] == "CHPT")
    assert ceg["memo_errors"]  # validation errors present
    assert ceg["memo"]["action"] == "yolo"  # passed through as-is; UI shows a warning


def test_overview_flags_holding_action_mismatch(data_dir):
    # memo says `enter`, but the user actually holds the name → format warning
    wl = json.loads((data_dir / "watchlist.json").read_text(encoding="utf-8"))
    wl["stocks"][0]["holding"] = True  # ON
    (data_dir / "watchlist.json").write_text(json.dumps(wl), encoding="utf-8")
    ov = build_overview(data_dir)
    on = next(r for r in ov["rows"] if r["ticker"] == "ON")
    assert any("holding" in e for e in on["memo_errors"])


def test_get_overview_endpoint(data_dir):
    res = client(data_dir).get("/api/overview")
    assert res.status_code == 200
    assert len(res.json()["rows"]) == 2


def test_overview_survives_datetime_date_in_memo(data_dir):
    memo = (data_dir / "analyses" / "ON" / "2026-06-01.md").read_text(encoding="utf-8")
    (data_dir / "analyses" / "ON" / "2026-06-02.md").write_text(
        memo.replace("date: 2026-06-01", "date: 2026-06-02T10:00:00"), encoding="utf-8")
    res = client(data_dir).get("/api/overview")
    assert res.status_code == 200
    mu = next(r for r in res.json()["rows"] if r["ticker"] == "ON")
    assert mu["staleness"]["days_since_analysis"] is not None


def test_get_stock_detail(data_dir):
    res = client(data_dir).get("/api/stocks/ON")
    body = res.json()
    assert body["quote"]["price"] == 1032.0
    assert body["flows"]["signals"]["accumulation_hint"] is True
    assert body["memos"][0]["body"].startswith("# ON analysis body")


def test_get_stock_detail_rejects_path_traversal_ticker(data_dir):
    res = client(data_dir).get("/api/stocks/..%5C..")
    assert res.status_code == 422


def test_overview_survives_malformed_price_at_analysis(data_dir):
    memo = (data_dir / "analyses" / "ON" / "2026-06-01.md").read_text(encoding="utf-8")
    (data_dir / "analyses" / "ON" / "2026-06-03.md").write_text(
        memo.replace("price_at_analysis: 900", 'price_at_analysis: "$1,032"'),
        encoding="utf-8")
    res = client(data_dir).get("/api/overview")
    assert res.status_code == 200
    mu = next(r for r in res.json()["rows"] if r["ticker"] == "ON")
    assert mu["staleness"]["price_deviation_pct"] is None


def test_add_stock_endpoint_validates_thesis(data_dir):
    c = client(data_dir)
    res = c.post("/api/watchlist", json={"ticker": "WOLF", "thesis": "nope"})
    assert res.status_code == 422
    res = c.post("/api/watchlist", json={"ticker": "WOLF", "thesis": "ev-adoption",
                                          "layer": "power-semis"})
    assert res.status_code == 200
    assert any(s["ticker"] == "WOLF" for s in store.load_watchlist(data_dir)["stocks"])


def test_add_stock_endpoint_rejects_bad_ticker(data_dir):
    res = client(data_dir).post("/api/watchlist",
                                 json={"ticker": "bad!!", "thesis": "ev-adoption"})
    assert res.status_code == 422


def test_delete_stock(data_dir):
    c = client(data_dir)
    assert c.delete("/api/watchlist/CHPT").status_code == 200
    assert all(s["ticker"] != "CHPT" for s in store.load_watchlist(data_dir)["stocks"])


def test_put_thesis_writes_file(data_dir):
    c = client(data_dir)
    content = "---\nid: dc-power\nname: Power\nstatus: intact\ncreated: 2026-07-04\n---\nnew thesis body"
    assert c.put("/api/theses/dc-power", json={"content": content}).status_code == 200
    assert (data_dir / "theses" / "dc-power.md").read_text(encoding="utf-8") == content
    assert c.put("/api/theses/../evil", json={"content": "x"}).status_code in (404, 405, 422)
    assert not (data_dir / "theses" / "evil.md").exists()
    assert not (data_dir.parent / "evil.md").exists()


def test_status_returns_data_version(data_dir):
    res = client(data_dir).get("/api/status")
    assert res.json()["data_version"] > 0


def test_static_dashboard_served(data_dir):
    res = client(data_dir).get("/")
    assert res.status_code == 200
    assert "StockLux" in res.text


def test_static_assets_served(data_dir):
    c = client(data_dir)
    assert c.get("/app.js").status_code == 200
    assert c.get("/style.css").status_code == 200


def test_overview_includes_price_targets(data_dir):
    memo = (data_dir / "analyses" / "ON" / "2026-06-01.md").read_text(encoding="utf-8")
    memo = memo.replace("buy_range: [38, 55]",
                        "buy_range: [38, 55]\nprice_targets: {bear: 30, base: 48, bull: 66, horizon: 12mo}")
    (data_dir / "analyses" / "ON" / "2026-07-01.md").write_text(memo, encoding="utf-8")
    res = client(data_dir).get("/api/overview")
    mu = next(r for r in res.json()["rows"] if r["ticker"] == "ON")
    assert mu["memo"]["price_targets"]["base"] == 48
