# dollar_watch V2.7 changelog

## Reliability fixes

- Fixed Treasury buyback maximum-capacity loss during schedule/result merging.
- Added maximum-par XML aliases and explicit `UNKNOWN` buyback intensity when capacity cannot be established.
- Buyback intensity scoring confidence is now zero when capacity is unknown, while descriptive offered/accepted result data remains visible.
- Added a deterministic semantic relevance gate before any primary-source page is sent to the local LLM.
- Official but unrelated pages are labeled `IRRELEVANT_SOURCE`; reachability is never treated as evidence relevance.
- Verification queue now persists candidate relevance score/status and human APPROVED / REJECTED / DISPUTED review state.

## Auction lifecycle

- Canonicalizes reopened remaining maturities to benchmark tenors (e.g. 9Y11M -> 10-Year; 29Y11M -> 30-Year).
- Keeps TIPS and FRNs distinct from nominal coupon benchmarks.
- Supplements FiscalData's upcoming-auctions convenience endpoint with future rows from the full Treasury auction table when needed.

## Distribution context

- Adds 1-year and 3-year percentile, z-score and observation-count fields to sufficiently populated FRED indicators.
- Retains separate SOFR99 persistence diagnostics for repo-tail stress.
- Extends the default FRED collection window to 2023 for better historical context.

## Verification workflow

- Auto-verification only sends `RELEVANT` primary-source candidates to Ollama.
- `IRRELEVANT_SOURCE` candidates are persisted as research failures rather than misleading `INCONCLUSIVE` factual checks.
- Policy/Evidence UI shows candidate relevance separately from LLM verdict and human approval.

## Tests

- Added `test_v27.py` covering buyback capacity recovery/UNKNOWN behavior, semantic relevance rejection, benchmark-tenor canonicalization, generalized FRED distribution context, and verification queue relevance/approval persistence.
