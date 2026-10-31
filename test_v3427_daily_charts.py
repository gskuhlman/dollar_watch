"""V3.4.27: in-app daily refresher and Charts-tab figure builders."""
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from dollar_dashboard import charts
from dollar_dashboard.daily_refresh import DailyRefresher, next_run_after, parse_time

UTC = timezone.utc


class Clock:
    def __init__(self, t): self.t = t
    def __call__(self): return self.t


def _refresher(clock, *, newest="2026-10-30T22:00:00+00:00", enabled=True, at="18:30", run=None):
    calls = []
    def run_fn():
        calls.append(clock())
        if run: return run()
        return {"bundle": {"snapshot": {"timestamp": clock().isoformat()}}, "snapshot_id": len(calls)}
    r = DailyRefresher(run_fn, lambda: {"enabled": enabled, "time": at}, lambda: newest, now_fn=clock)
    return r, calls


def test_parse_time_falls_back_to_default_on_garbage():
    assert parse_time("07:05") == (7, 5)
    assert parse_time("25:99") == (18, 30)
    assert parse_time(None) == (18, 30)


def test_next_run_is_new_york_wall_clock_across_dst():
    # 2026-10-31 is EDT (UTC-4); 2026-11-02 is EST (UTC-5) after the Nov 1 change.
    before = next_run_after(datetime(2026, 10, 31, 12, 0, tzinfo=UTC), "18:30")
    assert before.astimezone(UTC) == datetime(2026, 10, 31, 22, 30, tzinfo=UTC)
    after = next_run_after(datetime(2026, 11, 2, 12, 0, tzinfo=UTC), "18:30")
    assert after.astimezone(UTC) == datetime(2026, 11, 2, 23, 30, tzinfo=UTC)
    # Past today's time -> tomorrow.
    rolled = next_run_after(datetime(2026, 10, 31, 23, 0, tzinfo=UTC), "18:30")
    assert rolled.astimezone(UTC) == datetime(2026, 11, 1, 23, 30, tzinfo=UTC)


def test_tick_runs_once_at_scheduled_time_then_waits_for_tomorrow():
    clock = Clock(datetime(2026, 10, 31, 22, 0, tzinfo=UTC))  # 18:00 ET
    r, calls = _refresher(clock)
    assert r.tick() is False and calls == []
    clock.t = datetime(2026, 10, 31, 22, 31, tzinfo=UTC)
    assert r.tick() is True and len(calls) == 1
    assert r.tick() is False and len(calls) == 1
    assert r.status()["next_run"].startswith("2026-11-01T18:30")
    assert r.generation == 1


def test_missed_time_while_asleep_runs_on_wake():
    clock = Clock(datetime(2026, 10, 31, 20, 0, tzinfo=UTC))
    r, calls = _refresher(clock)
    r.tick()
    clock.t = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)  # woke at 22:00 ET, after 18:30
    assert r.tick() is True and len(calls) == 1


def test_disabled_never_runs_and_time_change_applies_without_restart():
    clock = Clock(datetime(2026, 10, 31, 22, 31, tzinfo=UTC))
    cfg = {"enabled": False, "time": "18:30"}
    calls = []
    r = DailyRefresher(lambda: calls.append(1) or {}, lambda: cfg, lambda: None, now_fn=clock)
    assert r.tick() is False and calls == []
    cfg.update(enabled=True, time="19:00")
    assert r.tick() is False
    assert r.status()["next_run"].startswith("2026-10-31T19:00")


def test_catchup_due_only_when_newest_snapshot_is_stale_or_missing():
    clock = Clock(datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
    assert _refresher(clock, newest="2026-10-31T00:00:00+00:00")[0].catchup_due() is False
    assert _refresher(clock, newest="2026-09-19T19:25:12+00:00")[0].catchup_due() is True
    assert _refresher(clock, newest=None)[0].catchup_due() is True


def test_startup_catchup_is_marked_running_before_start_returns():
    clock = Clock(datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
    gate = threading.Event()
    r, calls = _refresher(clock, newest="2026-09-19T19:25:12+00:00",
                          run=lambda: gate.wait(5) and {"bundle": {}, "snapshot_id": 1})
    r.tick_seconds = 0.01
    r.start()
    try:
        assert r.status()["running"] is True  # no window where a page could start its own collection
        gate.set()
        assert r.wait_idle(timeout=5) and r.generation == 1 and len(calls) == 1
    finally:
        r.stop()


def test_fresh_history_skips_startup_catchup():
    clock = Clock(datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
    r, calls = _refresher(clock, newest="2026-10-31T11:00:00+00:00")
    r.tick_seconds = 0.01
    r.start()
    try:
        assert r.status()["running"] is False and calls == []
    finally:
        r.stop()


def test_failed_run_records_error_and_keeps_generation():
    clock = Clock(datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
    def boom(): raise RuntimeError("FRED down")
    r, _ = _refresher(clock, run=boom)
    assert r.run_now("test") is True
    s = r.status()
    assert s["last_ok"] is False and "FRED down" in s["last_error"] and s["generation"] == 0 and not s["running"]


def test_bundle_only_served_for_latest_generation():
    clock = Clock(datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
    r, _ = _refresher(clock)
    assert r.bundle_for(0) is None
    r.run_now(); r.run_now()
    assert r.bundle_for(1) is None and r.bundle_for(2) is not None


def test_concurrent_run_is_skipped_and_wait_idle_blocks_until_done():
    clock = Clock(datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
    gate = threading.Event(); started = threading.Event()
    def slow():
        started.set(); gate.wait(5); return {"bundle": {}, "snapshot_id": 1}
    r, _ = _refresher(clock, run=slow)
    t = threading.Thread(target=r.run_now); t.start(); started.wait(5)
    assert r.run_now("second") is False
    assert r.wait_idle(timeout=0.05) is False
    gate.set(); t.join(5)
    assert r.wait_idle(timeout=1) is True and r.generation == 1


# ---- charts ---------------------------------------------------------------

def _fred_hist():
    idx = pd.date_range("2025-01-01", "2026-10-30", freq="B")
    hist = pd.DataFrame(index=idx)
    hist["2Y Treasury"] = 4.0; hist["10Y Treasury"] = 4.5; hist["30Y Treasury"] = 5.0
    hist["SOFR-IORB spread"] = -0.05
    weekly = pd.Series(np.nan, index=idx); weekly[idx.dayofweek == 2] = 3_000_000.0
    hist["Reserve balances (millions)"] = weekly
    hist["ON RRP (billions)"] = 0.5
    return hist


def test_panel_units_and_window():
    hist = _fred_hist()
    liq = charts.fred_panel_frame(hist, next(p for p in charts.FRED_PANELS if p["key"] == "liquidity"), "3M")
    reserves = liq[liq["series"] == "Reserves"]
    assert reserves["value"].round(6).eq(3.0).all()  # $3,000,000M -> $3.0T
    assert liq[liq["series"] == "ON RRP"]["value"].round(6).eq(0.0005).all()  # $0.5B -> $0.0005T
    assert reserves["date"].min() >= pd.Timestamp("2026-07-30")
    assert len(reserves) < 20  # weekly series keeps only its own release dates
    funding = charts.fred_panel_frame(hist, next(p for p in charts.FRED_PANELS if p["key"] == "funding"), "All")
    assert funding["value"].round(6).eq(-5.0).all()  # -0.05 pct -> -5bp


def test_market_panel_indexes_to_100_at_window_start():
    idx = pd.date_range("2026-01-01", periods=300, freq="D")
    mh = pd.DataFrame({"DXY": np.linspace(100, 110, 300), "Gold": np.linspace(4000, 3000, 300)}, index=idx)
    df = charts.market_panel_frame(mh, "All")
    for name in ("DXY", "Gold"):
        s = df[df["series"] == name]
        assert abs(s["value"].iloc[0] - 100.0) < 1e-9
    assert abs(df[df["series"] == "DXY"]["value"].iloc[-1] - 110.0) < 1e-9


def test_risk_history_frame_orders_oldest_first_and_skips_missing():
    hist = [{"_captured_at": "2026-09-19T19:00:00+00:00", "scores": {"regimes": {"A": 30, "B": 10}}},
            {"_captured_at": "2026-09-06T13:00:00+00:00", "scores": {"regimes": {"A": 20}}},
            {"_captured_at": None, "scores": {"regimes": {"A": 99}}}]
    df = charts.risk_history_frame(hist, ["A", "B"])
    assert df["date"].is_monotonic_increasing
    assert len(df) == 3 and 99 not in df["value"].tolist()


def test_figure_is_single_axis_with_fixed_slot_colors_and_threshold():
    hist = _fred_hist()
    panel = next(p for p in charts.FRED_PANELS if p["key"] == "yields")
    df = charts.fred_panel_frame(hist, panel, "1Y")
    order = [n for n, _ in panel["columns"].values()]
    fig = charts.line_figure(df, title="t", unit="%", fmt=".2f", order=order, thresholds=[(5.0, "five")])
    lines = [t for t in fig.data if t.mode == "lines"]
    assert [t.name for t in lines] == ["2Y", "10Y", "30Y"]
    assert [t.line.color for t in lines] == charts.SERIES_LIGHT[:3]
    assert all(getattr(t, "yaxis", None) in (None, "y") for t in fig.data)  # no secondary axis
    assert any(a.text == "five" for a in fig.layout.annotations)
    # Filtering out a series must not repaint the survivors.
    fig2 = charts.line_figure(df[df["series"] != "2Y"], title="t", unit="%", fmt=".2f", order=order)
    assert [t.line.color for t in fig2.data if t.mode == "lines"] == charts.SERIES_LIGHT[1:3]


def test_line_breaks_across_long_snapshot_gaps_and_axis_hugs_data():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-09-18", "2026-09-19", "2026-10-31"], utc=True),
                       "series": "A", "value": [10.0, 11.0, 12.0]})
    fig = charts.line_figure(df, title="t", unit="", fmt=".0f", max_gap=pd.Timedelta(days=4))
    line = next(t for t in fig.data if t.mode == "lines")
    ys = list(line.y)
    assert len(ys) == 4 and pd.isna(ys[2]) and line.connectgaps is False
    assert pd.Timestamp(fig.layout.xaxis.range[1]) == pd.Timestamp("2026-10-31", tz="UTC")


def test_direct_labels_do_not_collide():
    placed = charts._spread_labels([("a", 1.00), ("b", 1.01), ("c", 1.02)], span=1.0)
    ys = sorted(placed.values())
    assert all(b - a >= 0.07 - 1e-9 for a, b in zip(ys, ys[1:]))


def test_wide_table_has_date_column_newest_first():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-01"]),
                       "series": ["x", "x", "y"], "value": [1.0, 2.0, 3.0]})
    out = charts.wide_table(df)
    assert list(out.columns) == ["Date", "x", "y"] and out["Date"].iloc[0] == "2026-10-02"


def test_app_wires_refresher_and_charts_tab():
    src = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
    assert "get_or_start(" in src and '"Charts"' in src and "@st.fragment(run_every=" in src
    assert "def run_collection(" in Path(__file__).with_name("collector.py").read_text(encoding="utf-8")
