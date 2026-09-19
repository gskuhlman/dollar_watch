# dollar_watch V2.2 changelog

## Correctness fixes

- Rebuilt Treasury FiscalData auction ingestion to avoid brittle `fields=` queries and normalize legacy/current schema aliases locally.
- Added the dedicated FiscalData `upcoming_auctions` endpoint for future auction catalysts.
- Auction source failures remain missing evidence and cannot be interpreted as benign auction conditions.
- Split transactional $1 stablecoins from tokenized Treasury/RWA dollar products before peg testing.
- Yield-accumulating RWA products such as USDY/USYC no longer create false depeg warnings solely because NAV is above $1.
- Future-dated FRED observations are filtered; any surviving source-date-ahead condition is explicitly flagged and confidence-discounted.

## Analysis improvements

- Local red-team LLM receives compact prior-run context plus true regime deltas.
- Prompt explicitly prevents `2Y Treasury > current SOFR` from being described as proof of Fed hike pricing.
- Added prioritized headline claim-verification queue with preferred primary-source families.
- Portfolio `Why` text now uses current regime scores and active causal drivers.

## Tests added

- Treasury legacy/current auction field normalization.
- Stablecoin vs tokenized-RWA classification.
- Future source-date hygiene.
- Prior-run regime deltas.
- Evidence-based portfolio rationale.

Validation: `test_engine.py` and `test_v2.py` pass under V2.2.
