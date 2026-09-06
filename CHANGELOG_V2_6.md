# dollar_watch V2.6 changelog

V2.6 is the final major feature release before a planned period of live-history accumulation and calibration.

## Correctness and evidence integrity

- Added buyback-result completeness gating. A partial result set cannot support conclusions such as “no long-end operations,” “zero uptake,” or “low intensity.”
- Expanded TreasuryDirect buyback maximum-amount field aliases and added explicit `PARSE_FAILED_OR_ZERO` status when capacity cannot be parsed.
- Buyback schedule and results confidence are capped separately by parse/completeness quality.
- Fixed orphan TreasuryDirect result rows so completed result XMLs remain marked as results even when the current tentative schedule no longer contains the operation.
- Upcoming 10Y/30Y auction linkage now uses robust tenor matching and feeds the auction lifecycle / replacement-event state.

## Dollar funding plumbing

- Added the H.4.1/FRED **FIMA foreign-official repo** series separately from central-bank liquidity swaps.
- The funding trigger now fires on median SOFR-IORB stress, central-bank USD liquidity swaps, or FIMA repo usage, while reporting swaps and FIMA independently.
- Offshore cross-currency-basis coverage remains explicitly incomplete; domestic plumbing is not labeled full global-dollar-funding coverage.

## Foreign Treasury demand / TIC

- Added monthly TIC/FRED series for total, official, and private Treasury net transactions.
- Added long-term Treasury valuation-change series for grand-total and foreign-official sectors.
- New transaction decomposition separates:
  - reported holdings change,
  - active net transactions (purchases/sales),
  - long-term price valuation change,
  - residual/custody/reclassification/short-term effects.
- Scoring and red-team instructions no longer equate a holdings increase with “demand.”
- TIC transaction evidence receives its own observation-date freshness/confidence rather than inheriting the freshness of the FRED retrieval itself.

## Verification workflow

- News claims are automatically persisted into a deduplicated SQLite verification queue.
- Optional bounded automatic P0/P1 primary-source research is available when the configured Ollama/OpenAI-compatible endpoint is enabled.
- Automatic checks can discover official candidates, fetch a source, run the claim-vs-source verifier, and persist SUPPORTED / CONTRADICTED / INCONCLUSIVE results.
- Automatic research **never** promotes a claim into VERIFIED hard-scoring evidence. Human approval remains required.

## Portfolio engine

- Fresh weak 10Y+30Y auction stress now branches by mechanism:
  - **Inflationary fiscal stress:** +2pp TIPS, +1pp gold, -3pp T-bills.
  - **Real-yield fiscal stress with anchored breakevens:** +2pp T-bills, +1pp gold, and reductions to TIPS / rate-sensitive equity sleeves rather than mechanically adding duration.
- Aging, expired, and pending-replacement auction triggers remain non-trading states.

## Tests

Added `test_v26.py` covering TIC decomposition, buyback completeness gating, auction replacement linkage, FIMA-vs-swap separation, real-yield portfolio pre-commitments, and verification-queue deduplication.
