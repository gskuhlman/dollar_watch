"""V3.4.27 regressions: reserve/TGA unit scaling and newest-first Japan MOF discovery."""
from unittest.mock import Mock, patch

import pandas as pd

from dollar_dashboard import __version__
from dollar_dashboard.data import FRED_SERIES
from dollar_dashboard.official_policy import MOF_FX_20260828, MOF_FX_MONTHLY_INDEX, fetch_japan_mof_intervention
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard.scoring import DEFAULT_OVERRIDES, score

COMPONENT = "Treasury / repo / funding plumbing stress"


def test_version_and_score_model_bump():
    assert __version__ == APP_VERSION == "3.4.27"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.4"


def test_reserve_and_tga_labels_match_fred_millions_units():
    assert FRED_SERIES["Reserve balances (millions)"] == "WRESBAL"
    assert FRED_SERIES["Treasury General Account (millions)"] == "WTREGEN"
    assert not any("(billions)" in k and v in {"WRESBAL", "WTREGEN"} for k, v in FRED_SERIES.items())


def _snap(reserves_3m, tga_3m, *, legacy=False):
    unit = "billions" if legacy else "millions"
    return {
        "market_summary": {"DXY": {"last": 100, "1m": 0, "3m": 0}},
        "fred_summary": {
            f"Reserve balances ({unit})": {"3m_change": reserves_3m},
            f"Treasury General Account ({unit})": {"3m_change": tga_3m},
        },
        "official_policy_meta": {},
    }


def _plumbing(snapshot):
    ov = {k: {"value": v, "note": ""} for k, v in DEFAULT_OVERRIDES.items()}
    return score(snapshot, {"scores": {}}, ov)["components"][COMPONENT]


def test_small_reserve_drain_no_longer_counts_as_300b_plumbing_stress():
    # -$50B reserves / +$60B TGA (values in millions) previously cleared the 300 threshold.
    assert _plumbing(_snap(-50_000, 60_000)) == _plumbing(_snap(0, 0))


def test_large_reserve_drain_with_tga_rebuild_still_adds_plumbing_stress():
    assert _plumbing(_snap(-350_000, 320_000)) > _plumbing(_snap(0, 0))


def test_legacy_billions_key_replays_with_millions_semantics():
    assert _plumbing(_snap(-50_000, 60_000, legacy=True)) == _plumbing(_snap(0, 0))
    assert _plumbing(_snap(-350_000, 320_000, legacy=True)) == _plumbing(_snap(-350_000, 320_000))


def _resp(url, body):
    r = Mock(); r.status_code = 200; r.url = url; r.content = body.encode("utf-8")
    r.encoding = "utf-8"; r.apparent_encoding = "utf-8"; r.headers = {"content-type": "text/html"}
    return r


NEWER = "https://www.mof.go.jp/policy/international_policy/reference/feio/data/monthly/20260930.html"


def test_newer_monthly_release_takes_precedence_over_dated_english_page():
    pages = {
        MOF_FX_MONTHLY_INDEX: f'<a href="{NEWER}">令和8年9月</a><a href="{MOF_FX_20260828}">令和8年8月</a>',
        NEWER: "<p>令和8年8月27日～令和8年9月26日 外国為替平衡操作額 5兆6,000億円</p>",
    }
    english = "<p>Total amount of foreign exchange intervention operations ¥ 15,399.3 billion</p>"
    with patch("dollar_dashboard.official_policy._get", side_effect=lambda url, timeout: _resp(url, pages.get(url, english))), \
         patch("dollar_dashboard.official_policy._cache_put"):
        out = fetch_japan_mof_intervention(timeout=1)
    assert out["fetch_mode"] == "LIVE_JAPANESE_NEWER_RELEASE"
    assert out["canonical_url"] == NEWER
    assert out["amount_trillion_yen"] == 5.6
    assert (out["period_start"], out["period_end"]) == ("2026-08-27", "2026-09-26")


def test_newer_release_without_parseable_period_does_not_inherit_august_dates():
    pages = {
        MOF_FX_MONTHLY_INDEX: f'<a href="{NEWER}">monthly</a>',
        NEWER: "<p>外国為替平衡操作額 5兆6,000億円</p>",
    }
    with patch("dollar_dashboard.official_policy._get", side_effect=lambda url, timeout: _resp(url, pages.get(url, ""))), \
         patch("dollar_dashboard.official_policy._cache_put"):
        out = fetch_japan_mof_intervention(timeout=1)
    assert out["canonical_url"] == NEWER
    assert out["period_start"] is None and out["period_end"] is None
    assert out["period_status"] == "UNKNOWN"


# ---- collection speed + MOF decoding (V3.4.27) -------------------------------------------

def test_utf8_page_reported_as_latin1_decodes_correctly():
    from dollar_dashboard.official_policy import _decode_response_text
    r = Mock(); r.content = "外国為替平衡操作額 0円".encode("utf-8"); r.encoding = "ISO-8859-1"; r.apparent_encoding = "utf-8"
    assert _decode_response_text(r) == "外国為替平衡操作額 0円"
    sj = Mock(); sj.content = "平衡操作".encode("cp932"); sj.encoding = "ISO-8859-1"; sj.apparent_encoding = "SHIFT_JIS"
    assert _decode_response_text(sj) == "平衡操作"


def test_zero_intervention_months_parse_as_zero_not_missing():
    from dollar_dashboard.official_policy import _parse_english_yen_intervention_amount, _parse_yen_intervention_amount
    assert _parse_yen_intervention_amount("○令和8年8月27日～令和8年9月28日における外国為替平衡操作額 0円 問い合わせ先") == 0
    assert _parse_english_yen_intervention_amount(
        "Total amount of foreign exchange intervention operations for the period from August 27, 2026 through September 28, 2026 ¥　 0") == 0
    assert _parse_yen_intervention_amount("送料 0円") is None  # bare 0円 elsewhere on a page is not a reading


def _mof_pages(n_old=40):
    from dollar_dashboard.official_policy import MOF_FX_20260828, MOF_FX_MONTHLY_INDEX
    base = "https://www.mof.go.jp/policy/international_policy/reference/feio/data/monthly/"
    oct_, sep_ = base + "20261030.html", base + "20260930.html"
    old = [f"{base}{2023 + i // 12}{(i % 12) + 1:02d}28.html" for i in range(n_old)]
    links = "".join(f'<a href="{u}">x</a>' for u in [oct_, sep_, MOF_FX_20260828, *old])
    pages = {
        MOF_FX_MONTHLY_INDEX: links,
        oct_: "令和8年9月29日～令和8年10月28日 外国為替平衡操作額 0円",
        sep_: "令和8年8月27日～令和8年9月28日 外国為替平衡操作額 0円",
        MOF_FX_20260828: "令和8年7月30日～令和8年8月26日 外国為替平衡操作額 15兆3,993億円",
    }
    return pages, oct_


def test_mof_reports_latest_zero_release_and_most_recent_intervention():
    pages, oct_ = _mof_pages()
    with patch("dollar_dashboard.official_policy._get", side_effect=lambda url, timeout: _resp(url, pages.get(url, ""))):
        out = fetch_japan_mof_intervention(timeout=1)
    assert out["amount_trillion_yen"] == 15.3993 and out["intervention_occurred"] is True
    assert (out["period_start"], out["period_end"]) == ("2026-07-30", "2026-08-26")
    assert out["latest_release_url"] == oct_ and out["latest_release_amount_yen"] == 0
    assert out["latest_release_period_end"] == "2026-10-28"


def test_mof_scan_is_bounded_even_when_nothing_parses():
    from dollar_dashboard.official_policy import MOF_MAX_MONTHLY_PAGES
    pages, _ = _mof_pages()
    pages = {k: v for k, v in pages.items() if "index" in k}  # every release page unparseable
    calls = []
    def fake_get(url, timeout):
        calls.append(url)
        return _resp(url, pages.get(url, ""))
    with patch("dollar_dashboard.official_policy._get", side_effect=fake_get):
        fetch_japan_mof_intervention(timeout=1)
    monthly = [u for u in calls if "/data/monthly/20" in u]
    # newer-first scan + older fallback scan, each capped; never the full ~40-page index
    assert len(monthly) <= 2 * MOF_MAX_MONTHLY_PAGES


def test_pipeline_runs_stages_concurrently_with_deterministic_merge(monkeypatch):
    import time as _time
    from dollar_dashboard import pipeline

    def slow(name):
        def stage(bundle, status):
            _time.sleep(0.3)
            status[f"src {name}"] = {"ok": True, "weight": 1.0}
            bundle[f"k_{name}"] = name
        return stage

    names = [n for n, _ in pipeline.COLLECTION_STAGES]
    stages = [(n, slow(n)) for n in names]
    stages[0] = (names[0], lambda b, s: (_ for _ in ()).throw(RuntimeError("boom")))  # programming error
    merged = {}
    def fake_health(status):
        merged["order"] = list(status)
        return pd.DataFrame(columns=["source", "confidence"]), 0.0
    monkeypatch.setattr(pipeline, "COLLECTION_STAGES", stages)
    monkeypatch.setattr(pipeline, "build_data_health", fake_health)
    t = _time.perf_counter()
    try:
        pipeline.collect_live_bundle()
    except Exception:
        pass  # snapshot assembly needs real keys; timing and merge order are what is under test
    assert _time.perf_counter() - t < 0.3 * len(names) / 2  # concurrent, not sequential
    assert merged["order"][0].startswith("Collector stage")
    assert merged["order"][1:] == [f"src {n}" for n in names[1:]]
