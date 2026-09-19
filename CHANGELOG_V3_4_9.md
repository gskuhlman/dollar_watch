# dollar_watch V3.4.9 — fixed-horizon change measurement

V3.4.9 replaces previous-run analytical deltas with fixed-period comparisons so dashboard conclusions do not depend on how often Streamlit or the collector is run.

## Changes

- Adds first-class fixed horizon comparisons: **1D, 7D, 1M, 3M, 6M, 1Y**.
- Each horizon queries the database directly around its target date and chooses the nearest historical snapshot only within an explicit tolerance. Frequent same-day runs therefore cannot crowd 3M/6M/1Y references out of a "last N runs" buffer. Missing/incomparable history is reported as **N/A**, never silently replaced by an unrelated run.
- Stores the actual reference timestamp, actual age, target-date error, source app version and schema for auditability.
- Headline regime cards now show the **1D delta** when available instead of change since the immediately previous run.
- Adds a fixed-horizon regime-change table and a reference-date audit table to the dashboard.
- Local LLM `What Changed` analysis now uses only `fixed_horizon_changes`; adjacent-run context is operational/debug-only.
- Regime-change alerts use the fixed **1D** comparison. Adjacent-run state is still used where it is appropriate: phase changes, trigger state transitions, source/update lineage and debugging.
- Headless collector output reports the 1D change instead of previous-run change.
- No changes to six-regime scoring formulas, Treasury-financing formulas, portfolio allocation math, or machine trigger thresholds.

## Comparison tolerances

- 1D: target ±8 hours
- 7D: target ±1 day
- 1M: target ±3 days
- 3M: target ±7 days
- 6M: target ±14 days
- 1Y: target ±21 days

The actual historical reference timestamp is always exposed so a user can see what observation produced each delta.
