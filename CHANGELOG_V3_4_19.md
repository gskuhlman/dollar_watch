# V3.4.19 — TIC path independence + data-quality-aware fixed horizons

## Why this release exists

The V3.4.18 Sep. 15 run exposed an internal inconsistency when Treasury's direct TIC country-holdings table failed: the FRED-hosted TIC transaction/valuation series were still present in `fred_summary`, but the pipeline zeroed `tic_transaction_meta` and its confidence because both feeds were inside one exception block. The red-team model could therefore narrate transaction figures that scoring simultaneously treated as unavailable.

The same run also showed why fixed-horizon score deltas need measurement-quality context: overall confidence fell by more than 12 points as TIC/buyback sources changed availability. A regime-score move across that horizon is not necessarily a pure economic move.

## Changes

- Direct Treasury TIC country holdings and FRED-hosted TIC transaction/valuation decomposition are now collected as **independent evidence paths**.
- A direct TIC table outage no longer erases a valid FRED TIC transaction decomposition.
- Conversely, active foreign purchases/sales may not be narrated when `tic_transaction_meta` is unavailable or `tic_transactions` confidence is zero.
- Fixed-horizon comparisons now include:
  - `component_confidence_deltas`
  - `material_data_quality_changes`
  - `data_quality_status` (`STABLE` or `DATA_QUALITY_AFFECTED`)
  - an explicit interpretation guard.
- A material component-confidence move (>=20pp or a zero/nonzero transition), or an overall confidence move >=5 points, marks the horizon `DATA_QUALITY_AFFECTED`.
- Regime-change alerts across a data-quality-affected horizon are downgraded to WATCH and explicitly state that the delta is not a pure market move.
- The Executive tab shows a warning and exposes source-quality changes alongside fixed-horizon reference dates.
- Added deterministic LLM lint preventing TIC active-transaction claims when the transaction decomposition is unavailable.

## Lineage

- App version: **3.4.19**
- Schema version: **3.4.1**
- Score model version: **3.4.3**

The score-model bump is intentional because TIC transaction evidence can now remain score-eligible when the independent direct country-holdings table is unavailable. Comparisons across score model 3.4.2 -> 3.4.3 are therefore `INCOMPARABLE_SCORE_MODEL` rather than market deltas.
