import json
from datetime import date

from stocklux import calibrate

AS_OF = date(2025, 1, 15)  # > memo_date 2024-01-01 + 365d (2024-12-31) => matured


def write_memo(tmp_path, ticker, memo_date, *, bear, base, bull,
                p_bear=0.3, p_base=0.4, p_bull=0.3, price_at_analysis=100.0,
                action="watch_only", horizon="12mo"):
    d = tmp_path / "analyses" / ticker
    d.mkdir(parents=True, exist_ok=True)
    text = f"""---
ticker: "{ticker}"
date: {memo_date.isoformat()}
thesis: test-thesis
action: {action}
confidence: medium
buy_range: [{bear}, {bull}]
price_targets:
  bear: {bear}
  base: {base}
  bull: {bull}
  p_bear: {p_bear}
  p_base: {p_base}
  p_bull: {p_bull}
  horizon: {horizon}
price_at_analysis: {price_at_analysis}
verdict: in_range
thesis_health: intact
top_risks: [x]
review_trigger: "test trigger"
signals:
  chain: favorable
  narrative: favorable
  fundamentals: favorable
  valuation: favorable
  flows: neutral
  sentiment: neutral
  competition: neutral
  macro: neutral
---
# {ticker} test memo
"""
    (d / f"{memo_date.isoformat()}.md").write_text(text, encoding="utf-8")


def append_history(tmp_path, rows):
    p = tmp_path / "history.jsonl"
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def write_quotes(tmp_path, prices: dict):
    (tmp_path / "quotes.json").write_text(
        json.dumps({"quotes": {t: {"price": p} for t, p in prices.items()}}),
        encoding="utf-8")


# ---------------------------------------------------------------------------
# Empty-safe
# ---------------------------------------------------------------------------

def test_empty_data_is_safe(tmp_path):
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    assert result["matured"] == []
    assert result["tracking"] == []
    assert result["aggregate"] == {"n": 0, "mean_brier": None}
    assert result["as_of"] == AS_OF.isoformat()
    # file was written
    on_disk = json.loads((tmp_path / "calibration.json").read_text(encoding="utf-8"))
    assert on_disk == result


def test_as_of_defaults_to_today(tmp_path):
    result = calibrate.calibrate(tmp_path)
    assert result["as_of"] == date.today().isoformat()


# ---------------------------------------------------------------------------
# Realized tier branches (bear / base / bull, incl. midpoint boundaries)
# ---------------------------------------------------------------------------

MEMO_DATE = date(2024, 1, 1)
MATURITY = date(2024, 12, 31)  # memo_date + 365d


def _matured_case(tmp_path, ticker, realized_price):
    write_memo(tmp_path, ticker, MEMO_DATE, bear=80, base=100, bull=140)
    append_history(tmp_path, [
        {"date": MATURITY.isoformat(), "ticker": ticker, "price": realized_price},
    ])


def test_realized_tier_bear_below_midpoint(tmp_path):
    _matured_case(tmp_path, "BEARX", 85)  # < (80+100)/2 = 90
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "BEARX")
    assert entry["realized_tier"] == "bear"


def test_realized_tier_bear_at_lower_midpoint_boundary(tmp_path):
    _matured_case(tmp_path, "BOUNDBEAR", 90)  # == (80+100)/2, bear per <=
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "BOUNDBEAR")
    assert entry["realized_tier"] == "bear"


def test_realized_tier_base_between_midpoints(tmp_path):
    _matured_case(tmp_path, "BASEX", 100)  # strictly between 90 and 120
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "BASEX")
    assert entry["realized_tier"] == "base"


def test_realized_tier_bull_at_upper_midpoint_boundary(tmp_path):
    _matured_case(tmp_path, "BOUNDBULL", 120)  # == (100+140)/2, bull per >=
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "BOUNDBULL")
    assert entry["realized_tier"] == "bull"


def test_realized_tier_bull_above_midpoint(tmp_path):
    _matured_case(tmp_path, "BULLX", 130)  # > 120
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "BULLX")
    assert entry["realized_tier"] == "bull"


# ---------------------------------------------------------------------------
# Brier score correctness (hand-computed)
# ---------------------------------------------------------------------------

def test_brier_score_hand_computed(tmp_path):
    write_memo(tmp_path, "BRIERX", MEMO_DATE, bear=80, base=100, bull=140,
               p_bear=0.5, p_base=0.3, p_bull=0.2)
    append_history(tmp_path, [
        {"date": MATURITY.isoformat(), "ticker": "BRIERX", "price": 85},  # realized: bear
    ])
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "BRIERX")
    assert entry["realized_tier"] == "bear"
    # one-hot [1, 0, 0]; brier = (0.5-1)^2 + (0.3-0)^2 + (0.2-0)^2
    expected = (0.5 - 1) ** 2 + (0.3 - 0) ** 2 + (0.2 - 0) ** 2
    assert abs(entry["brier"] - expected) < 1e-9
    assert abs(expected - 0.38) < 1e-9
    assert result["aggregate"]["n"] == 1
    assert abs(result["aggregate"]["mean_brier"] - expected) < 1e-9


def test_uninformative_uniform_prior_brier_is_two_thirds(tmp_path):
    write_memo(tmp_path, "UNIFORMX", MEMO_DATE, bear=80, base=100, bull=140,
               p_bear=1 / 3, p_base=1 / 3, p_bull=1 / 3)
    append_history(tmp_path, [
        {"date": MATURITY.isoformat(), "ticker": "UNIFORMX", "price": 85},
    ])
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "UNIFORMX")
    assert abs(entry["brier"] - 0.6667) < 1e-3


# ---------------------------------------------------------------------------
# +/-14 day skip path
# ---------------------------------------------------------------------------

def test_realized_price_skipped_outside_14_day_window(tmp_path):
    write_memo(tmp_path, "SKIPX", MEMO_DATE, bear=80, base=100, bull=140)
    # 20 days away from maturity 2024-12-31 -> outside +/-14d window
    far_date = date(2025, 1, 20)
    append_history(tmp_path, [
        {"date": far_date.isoformat(), "ticker": "SKIPX", "price": 95},
    ])
    result = calibrate.calibrate(tmp_path, as_of=date(2025, 2, 1))
    entry = next(m for m in result["matured"] if m["ticker"] == "SKIPX")
    assert entry["realized_price"] is None
    assert entry["realized_tier"] is None
    assert entry["brier"] is None
    assert entry["note"] is not None
    # excluded from the graded aggregate
    assert result["aggregate"]["n"] == 0
    assert result["aggregate"]["mean_brier"] is None


def test_realized_price_found_within_14_day_window(tmp_path):
    write_memo(tmp_path, "NEARX", MEMO_DATE, bear=80, base=100, bull=140)
    near_date = date(2025, 1, 10)  # 10 days after maturity, within window
    append_history(tmp_path, [
        {"date": near_date.isoformat(), "ticker": "NEARX", "price": 95},
    ])
    result = calibrate.calibrate(tmp_path, as_of=date(2025, 2, 1))
    entry = next(m for m in result["matured"] if m["ticker"] == "NEARX")
    assert entry["realized_price"] == 95
    assert entry["note"] is None


def test_no_history_rows_at_all_is_skipped_with_note(tmp_path):
    write_memo(tmp_path, "NOHIST", MEMO_DATE, bear=80, base=100, bull=140)
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "NOHIST")
    assert entry["realized_price"] is None
    assert entry["note"] is not None


# ---------------------------------------------------------------------------
# MAE / MFE path stats
# ---------------------------------------------------------------------------

def test_mae_mfe_from_price_path(tmp_path):
    write_memo(tmp_path, "PATHX", MEMO_DATE, bear=80, base=100, bull=140,
               price_at_analysis=100.0)
    append_history(tmp_path, [
        {"date": "2024-01-01", "ticker": "PATHX", "price": 100.0},   # 0%
        {"date": "2024-02-20", "ticker": "PATHX", "price": 110.0},   # +10%
        {"date": "2024-04-10", "ticker": "PATHX", "price": 90.0},    # -10%
        {"date": "2024-07-19", "ticker": "PATHX", "price": 105.0},   # +5%
        {"date": "2024-12-31", "ticker": "PATHX", "price": 102.0},   # +2% (also realized price)
    ])
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "PATHX")
    assert abs(entry["mae_pct"] - (-10.0)) < 1e-9
    assert abs(entry["mfe_pct"] - 10.0) < 1e-9
    assert entry["realized_price"] == 102.0


def test_mae_mfe_none_when_price_at_analysis_missing(tmp_path):
    d = tmp_path / "analyses" / "NOPRICEX"
    d.mkdir(parents=True)
    text = f"""---
ticker: "NOPRICEX"
date: {MEMO_DATE.isoformat()}
thesis: test-thesis
action: watch_only
confidence: medium
buy_range: [80, 140]
price_targets:
  bear: 80
  base: 100
  bull: 140
  p_bear: 0.3
  p_base: 0.4
  p_bull: 0.3
  horizon: 12mo
price_at_analysis: null
verdict: in_range
thesis_health: intact
top_risks: [x]
review_trigger: "test trigger"
signals:
  chain: favorable
  narrative: favorable
  fundamentals: favorable
  valuation: favorable
  flows: neutral
  sentiment: neutral
  competition: neutral
  macro: neutral
---
# NOPRICEX test memo
"""
    (d / f"{MEMO_DATE.isoformat()}.md").write_text(text, encoding="utf-8")
    # realized price is found (row at maturity date), but price_at_analysis
    # is null so path stats can't be computed against a baseline.
    append_history(tmp_path, [
        {"date": MATURITY.isoformat(), "ticker": "NOPRICEX", "price": 95},
    ])
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    entry = next(m for m in result["matured"] if m["ticker"] == "NOPRICEX")
    assert entry["realized_price"] == 95
    assert entry["mae_pct"] is None
    assert entry["mfe_pct"] is None


# ---------------------------------------------------------------------------
# price_targets missing/null memos are skipped entirely
# ---------------------------------------------------------------------------

def test_memo_without_full_price_targets_excluded_from_matured(tmp_path):
    d = tmp_path / "analyses" / "NULLTARGET"
    d.mkdir(parents=True)
    text = f"""---
ticker: "NULLTARGET"
date: {MEMO_DATE.isoformat()}
thesis: test-thesis
action: watch_only
confidence: medium
buy_range: null
price_targets: null
price_at_analysis: 100.0
verdict: in_range
thesis_health: intact
top_risks: [x]
review_trigger: "test trigger"
signals:
  chain: favorable
  narrative: favorable
  fundamentals: favorable
  valuation: favorable
  flows: neutral
  sentiment: neutral
  competition: neutral
  macro: neutral
---
# NULLTARGET test memo
"""
    (d / f"{MEMO_DATE.isoformat()}.md").write_text(text, encoding="utf-8")
    append_history(tmp_path, [
        {"date": MATURITY.isoformat(), "ticker": "NULLTARGET", "price": 95},
    ])
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    assert all(m["ticker"] != "NULLTARGET" for m in result["matured"])


# ---------------------------------------------------------------------------
# Tracking: percentile math, incl. clamping outside [bear, bull]
# ---------------------------------------------------------------------------

TRACK_MEMO_DATE = date(2026, 6, 1)  # immature relative to AS_OF (2025-01-15 wouldn't work; use later as_of)
TRACK_AS_OF = date(2026, 7, 11)


def test_tracking_percentile_within_range(tmp_path):
    write_memo(tmp_path, "TRACKMID", TRACK_MEMO_DATE, bear=80, base=100, bull=140)
    write_quotes(tmp_path, {"TRACKMID": 90.0})
    result = calibrate.calibrate(tmp_path, as_of=TRACK_AS_OF)
    entry = next(t for t in result["tracking"] if t["ticker"] == "TRACKMID")
    # (90-80)/(140-80)*100 = 16.666...
    assert abs(entry["pct_between_bear_bull"] - 16.6667) < 1e-3
    assert entry["above_base"] is False
    assert entry["current_price"] == 90.0


def test_tracking_percentile_clamps_above_bull(tmp_path):
    write_memo(tmp_path, "TRACKHIGH", TRACK_MEMO_DATE, bear=80, base=100, bull=140)
    write_quotes(tmp_path, {"TRACKHIGH": 200.0})
    result = calibrate.calibrate(tmp_path, as_of=TRACK_AS_OF)
    entry = next(t for t in result["tracking"] if t["ticker"] == "TRACKHIGH")
    assert entry["pct_between_bear_bull"] == 100.0
    assert entry["above_base"] is True


def test_tracking_percentile_clamps_below_bear(tmp_path):
    write_memo(tmp_path, "TRACKLOW", TRACK_MEMO_DATE, bear=80, base=100, bull=140)
    write_quotes(tmp_path, {"TRACKLOW": 20.0})
    result = calibrate.calibrate(tmp_path, as_of=TRACK_AS_OF)
    entry = next(t for t in result["tracking"] if t["ticker"] == "TRACKLOW")
    assert entry["pct_between_bear_bull"] == 0.0
    assert entry["above_base"] is False


def test_tracking_months_elapsed(tmp_path):
    write_memo(tmp_path, "TRACKMONTHS", TRACK_MEMO_DATE, bear=80, base=100, bull=140)
    write_quotes(tmp_path, {"TRACKMONTHS": 100.0})
    result = calibrate.calibrate(tmp_path, as_of=TRACK_AS_OF)
    entry = next(t for t in result["tracking"] if t["ticker"] == "TRACKMONTHS")
    days = (TRACK_AS_OF - TRACK_MEMO_DATE).days
    assert entry["months_elapsed"] == round(days / 30.4375, 1)


def test_tracking_excludes_already_matured_memo(tmp_path):
    # memo dated far enough back that as_of makes it matured -> not tracked
    write_memo(tmp_path, "OLDMATURED", MEMO_DATE, bear=80, base=100, bull=140)
    append_history(tmp_path, [
        {"date": MATURITY.isoformat(), "ticker": "OLDMATURED", "price": 95},
    ])
    write_quotes(tmp_path, {"OLDMATURED": 95.0})
    result = calibrate.calibrate(tmp_path, as_of=AS_OF)
    assert all(t["ticker"] != "OLDMATURED" for t in result["tracking"])
    # but it does show up matured
    assert any(m["ticker"] == "OLDMATURED" for m in result["matured"])


def test_tracking_skips_ticker_missing_from_quotes(tmp_path):
    write_memo(tmp_path, "NOQUOTE", TRACK_MEMO_DATE, bear=80, base=100, bull=140)
    # no quotes.json written at all
    result = calibrate.calibrate(tmp_path, as_of=TRACK_AS_OF)
    assert all(t["ticker"] != "NOQUOTE" for t in result["tracking"])


def test_tracking_uses_latest_memo_per_ticker(tmp_path):
    write_memo(tmp_path, "MULTI", date(2026, 1, 1), bear=50, base=70, bull=90)
    write_memo(tmp_path, "MULTI", TRACK_MEMO_DATE, bear=80, base=100, bull=140)
    write_quotes(tmp_path, {"MULTI": 90.0})
    result = calibrate.calibrate(tmp_path, as_of=TRACK_AS_OF)
    entries = [t for t in result["tracking"] if t["ticker"] == "MULTI"]
    assert len(entries) == 1
    assert entries[0]["memo_date"] == TRACK_MEMO_DATE.isoformat()
