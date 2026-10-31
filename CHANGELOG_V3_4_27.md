# v3.4.27 — Reserve/TGA unit fix, live Japan MOF data, ~6× faster collection

## Fixes

- **Score-affecting unit bug.** FRED `WRESBAL` (reserve balances) and `WTREGEN` (TGA) are published in **millions** of dollars, but were labeled "(billions)" and the plumbing check `reserves_3m < -300 and tga_3m > 300` treated them as billions. The check therefore fired on a $300M reserve drain / TGA rebuild instead of $300B. Replaying the 50 stored snapshots (2026-09-06 → 2026-09-19): the false +6 plumbing points fired in 39; with the corrected $300B thresholds it fires in 0. This flowed into the funding-squeeze regime (`squeeze = 6 + 0.70 × plumbing`) and the early-warning index.
  - Labels are now `Reserve balances (millions)` / `Treasury General Account (millions)`; thresholds are `-300_000` / `300_000`.
  - Scoring falls back to the legacy "(billions)" key, which held the same millions values, so historical replays use correct semantics.
- **Japan MOF intervention pinned to August.** `fetch_japan_mof_intervention` tried the dated 2026-08-28 English page first and returned as soon as it parsed, so later monthly releases were never read while that page remained online. The Japanese monthly index is now scanned first; any release newer than 2026-08-28 takes precedence (`fetch_mode=LIVE_JAPANESE_NEWER_RELEASE`). The English page and existing fallbacks are unchanged otherwise.
  - A newer release whose period cannot be parsed no longer inherits the 2026-07-30..08-26 defaults; it reports `period_start/end=None` and `period_status=UNKNOWN` (catalyst age is then treated as stale → 0 points).

## Faster collection (≈104 s → ≈16 s measured; runs of about an hour were observed)

- **Japan MOF fetch was the likely cause of the hour-long runs.** Every Japanese page was decoded as ISO-8859-1 (the `requests` default when no charset header is sent). As a result, no live Japanese release ever parsed, and the fetcher walked the full ~40-page monthly index, each page with up to 3 user-agent retries × 12 s timeout. Fixes:
  - `_decode_response_text` tries UTF-8 (with BOM), the declared charset, the detected charset, then cp932/Shift-JIS. It ignores the ISO-8859-1 default.
  - Zero-intervention months (`外国為替平衡操作額 0円`, English `¥ 0`) parse as 0 instead of "missing".
  - Each scan reads at most `MOF_MAX_MONTHLY_PAGES = 6` releases, newest first.
  - The result reports the most recent nonzero intervention (currently 2026-07-30..08-26, ¥15.40T). It also reports the newest release as `latest_release_*` (currently 2026-09-29..10-28, ¥0). There was no September intervention; the Sep and Oct releases are both ¥0.
  - The live fetch now takes about 3.5 s.
- **Pipeline stages run concurrently.** `collect_live_bundle` runs 12 independent stage functions (`COLLECTION_STAGES`) on 8 threads. Each stage writes to private dicts, which are merged in a fixed order, so the snapshot is deterministic. A programming error in one stage shows up as a `Collector stage <name>` Data Health row instead of aborting the run.
  - TIC now runs with FRED (it needs FRED history), so its Data Health rows follow FRED.
  - On the same day, the 16 Data Health sources, all FRED keys and every automatic sub-score matched the sequential run.
- **FRED series** fetch on 6 threads and **Z.1 / Treasury-financing series** prefetch on 6 threads.
- `snapshot["collection_timing"]` records total and per-stage seconds. In the current run the slowest stages are official policy (~13 s) and buybacks (~11 s).
- `conftest.py` points `DOLLAR_POLICY_CACHE` at a temp file, so mocked tests no longer write into `data/official_policy_cache.json`. A 75-character test-fixture entry that an earlier test run had left in that cache was removed.

## Automatic daily update while the app runs

- New `dollar_dashboard/daily_refresh.py`: one background thread per server process runs the headless collector every day at a configurable New York time (default **18:30 ET**, after the U.S. close and the day's FRED/Treasury/NY Fed releases). It runs whether or not a browser tab is open, and on startup it runs a catch-up collection when the newest snapshot is more than 20 hours old. If the computer was asleep at the scheduled time, it runs on wake. The schedule is DST-aware.
- `collector.py` refactored into `run_collection(run_kind, verbose)`, shared by the CLI and the in-app thread (`run_kind=SCHEDULED_IN_APP`). The CLI is unchanged.
- Open pages refresh automatically: a sidebar fragment polls every 2 minutes and reruns the page when a newer daily run has finished. The page reuses that run's data rather than collecting again, and does not save a duplicate snapshot.
- If a page loads while an update is running, it waits for that update instead of starting a parallel collection. The startup catch-up is claimed before the thread starts, so there is no race.
- Sidebar "Automatic daily update": on/off toggle, update time, "Run update now", plus next/last run status and any error. Settings are stored in the database (`daily_refresh_enabled`, `daily_refresh_time`); defaults are in `config/settings.json`.
- A "Data collected …" timestamp now shows under the title.
- "Refresh all live data" still forces a live fetch, which is used until the next daily run.

## Charts tab

- New `dollar_dashboard/charts.py` and a **Charts** tab with a 3M/6M/1Y/2Y/All window:
  - risk indices over time (from saved snapshots; lines break where no snapshot was saved for more than 4 days)
  - Treasury yields 2Y/10Y/30Y
  - dollar, gold, oil and TLT, indexed to 100 at the window start
  - real yields, breakevens and 5Y5Y
  - curve and term premium, with the 0.70 kill threshold
  - repo spreads vs IORB in bp, with the 10bp trigger
  - reserves, TGA and ON RRP in $T
  - Fed balance sheet composition
  - foreign custody YoY, with the −$300B trigger
- One unit per y-axis (no dual axes). Fixed palette slot per series, validated for colorblind separation in light and dark. Direct end-of-line labels for up to 4 series, a crosshair tooltip, dashed lines at the model's own trigger thresholds, and a data table under every chart.

## Versioning

- App 3.4.27, **score model 3.4.4** (fixed-horizon comparisons against 3.4.3 snapshots return `INCOMPARABLE_SCORE_MODEL` or use current-model replay, as designed), schema 3.4.1, DB migration 2. No database migration; persistent `data/` untouched.

## Tests

- `test_v3427_daily_charts.py`: schedule/DST math, run-once-per-day, wake-after-sleep, disable/time change, stale catch-up and its start-up race, failure handling, single-flight runs, panel units/windows, indexing, gap breaks, fixed slot colors, single axis, label de-collision, table view.
- `test_v3427.py`: unit labels, small-drain non-trigger, large-drain trigger, legacy-key replay, newer-MOF precedence, no inherited period defaults, mis-declared charset decoding, ¥0 parsing, latest-zero vs most-recent-intervention reporting, bounded MOF scan, and concurrent stages with deterministic merge.
- New `pytest.ini`: plain `python -m pytest` now works from the repo root. It skips `old/` (duplicate test basenames) and disables the unrelated global `langsmith` plugin, which crashed collection under pydantic < 2.7.4 on Python ≥ 3.12.4 (`ForwardRef._evaluate() missing ... 'recursive_guard'`).
