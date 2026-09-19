# V3.4.17

## Nominal Treasury auction integrity (score-model 3.4.2)

- Corrects FiscalData auction classification so TIPS and FRNs are identified from `inflation_index_security` / `floating_rate` flags before nominal tenor assignment.
- Keeps TIPS (`5-Year TIPS`, `10-Year TIPS`, `30-Year TIPS`) and `2-Year FRN` out of nominal benchmark auction-stress history.
- Upcoming-auction lifecycle matching now exact-matches the same nominal canonical tenor and explicitly excludes TIPS/FRNs. A 10-Year TIPS reopening can no longer age/replace the nominal 10-Year note result.
- This can revise historical fiscal/auction stress, so `SCORE_MODEL_VERSION` advances from 3.4.1 to **3.4.2**. The persisted schema remains 3.4.1. Fixed-horizon score deltas across the model boundary are intentionally `INCOMPARABLE_SCORE_MODEL`.

## Z.1 hedge-fund transaction fallback

- If FRED has not yet exposed the new hedge-fund Treasury transaction series, use the Federal Reserve's official current F3.2.t HTML row `FA623061103`.
- Converts official-table billions-SAAR values to millions-SAAR so the fallback is unit-compatible with the FRED-backed holder layer.
- Records whether the optional holder row came from FRED or the official Fed F3.2.t fallback.
- Market-value Treasury holdings remain forbidden as a substitute for transaction flow.

## Narrative integrity

- A 99th/100th percentile reading may be called extreme/top-of-window only for its supplied lookback; it is not an all-time “record” without separate evidence.
- Adds deterministic narrative lint and one repair pass when generated red-team text incorrectly groups Fed bill accumulation/MBS runoff under structural dollar support or promotes finite-window percentiles to unsupported record/all-time language.

No portfolio-allocation thresholds or non-auction regime formulas changed.
