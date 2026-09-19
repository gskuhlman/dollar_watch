# dollar_watch V3.4.5 — semantic/calendar hardening

- Fixed the silently broken CFTC calendar calculation (`scoring.py` used `pd.Timestamp` without importing pandas; the broad try/except had hidden the `NameError`).
- Added explicit four-date CFTC release lifecycle: latest Tuesday position-as-of, latest expected Friday publication, next Tuesday position-as-of, and next expected Friday publication.
- Retained `latest_cftc_report_date` and `expected_publication_date` as backward-compatible aliases.
- Added `funding_observation_scope` with a PARTIAL_OFFSHORE language gate when live offshore coverage is below 70%.
- Hardened LLM instructions so domestic funding calm cannot be generalized into globally benign dollar funding when true cross-currency basis / OTC FX-swap coverage is missing.
- Hardened TGA semantics: cash-balance rebuild/liquidity drain, not automatic proof of prefunding future Treasury supply.
- No change to six-regime scoring or Treasury-financing state thresholds.
