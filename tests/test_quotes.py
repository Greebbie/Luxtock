from stocklux import quotes

GOOD_INFO = {
    "currentPrice": 100.0, "trailingPE": 20.0, "forwardPE": 10.0,
    "trailingEps": 5.0, "forwardEps": 10.0, "marketCap": 1_000_000,
    "fiftyTwoWeekHigh": 120.0, "fiftyTwoWeekLow": 80.0,
}


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def info(self):
        if self.symbol == "FAIL":
            raise RuntimeError("network down")
        return dict(GOOD_INFO)


def test_fetch_quotes_maps_fields(monkeypatch):
    monkeypatch.setattr(quotes.yf, "Ticker", FakeTicker)
    out = quotes.fetch_quotes(["ON"])
    q = out["quotes"]["ON"]
    assert q["price"] == 100.0
    assert q["ttm_pe"] == 20.0
    assert q["fwd_pe"] == 10.0
    assert q["high_52w"] == 120.0
    assert q["stale"] is False
    assert out["fetched_at"]
    expected_keys = set(quotes.FIELDS) | {"stale", "fetched_at"}
    assert set(q) == expected_keys


def test_fetch_quotes_failure_keeps_prev_and_marks_stale(monkeypatch):
    monkeypatch.setattr(quotes.yf, "Ticker", FakeTicker)
    prev = {"quotes": {"FAIL": {"price": 99.0, "ttm_pe": 18.0, "stale": False}}}
    out = quotes.fetch_quotes(["FAIL"], prev)
    assert out["quotes"]["FAIL"]["price"] == 99.0
    assert out["quotes"]["FAIL"]["stale"] is True
    expected_keys = set(quotes.FIELDS) | {"stale", "fetched_at"}
    assert set(out["quotes"]["FAIL"]) == expected_keys


def test_fetch_quotes_failure_without_prev_gives_nulls(monkeypatch):
    monkeypatch.setattr(quotes.yf, "Ticker", FakeTicker)
    out = quotes.fetch_quotes(["FAIL"])
    assert out["quotes"]["FAIL"]["price"] is None
    assert out["quotes"]["FAIL"]["stale"] is True
    expected_keys = set(quotes.FIELDS) | {"stale", "fetched_at"}
    assert set(out["quotes"]["FAIL"]) == expected_keys


def test_missing_price_falls_back_to_market_price(monkeypatch):
    class NoCurrentPrice(FakeTicker):
        @property
        def info(self):
            d = dict(GOOD_INFO)
            del d["currentPrice"]
            d["regularMarketPrice"] = 101.5
            return d

    monkeypatch.setattr(quotes.yf, "Ticker", NoCurrentPrice)
    out = quotes.fetch_quotes(["SPY"])
    assert out["quotes"]["SPY"]["price"] == 101.5
