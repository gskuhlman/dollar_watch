# dollar_watch V2.9 changelog

## Scope

Correctness/data-pipeline release. The six causal regimes and baseline portfolio architecture are unchanged.

## Treasury buybacks

- Result XMLs can now infer a missing operation maturity bucket from repeated result-level security maturity dates.
- Long-end means **nominal 10Y–20Y and 20Y–30Y** sectors; TIPS are excluded from this specific metric.
- Added completed long-end operation count, offered amount, accepted amount, max capacity, and accepted/max-capacity ratio.
- Prevents a missing bucket from being interpreted as zero long-end operations.
- Added a regression fixture covering the official June 3, June 9, June 25, July 1, July 16, July 23, July 28, and August 11 2026 long-end schedule pattern.

## Policy / verification funnel

- Fixed the bucket mismatch between news discovery (`US policy`, `Japan`, `BRICS`, etc.) and primary-source verification families.
- Added `verification_rows_from_news()` as a pure shared mapper for Streamlit and the headless collector.
- Added bounded systematic policy probes so primary-source research remains active even when RSS/news discovery is empty.
- Added an Administration / White House primary-source family for currency/rate-policy claims.
- Standing probes are propositions to test, not factual evidence. Existing semantic relevance, LLM verdict, quarantine, and human approval gates remain mandatory.

## Tests

- Added `test_v29.py`.
- All inherited V2.2–V2.8 regressions and V2.9 tests pass.
