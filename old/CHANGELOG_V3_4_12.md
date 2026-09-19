# V3.4.12

## Verification accounting
- Authoritative verification counts now come from full-database aggregates, not the capped 50-row persisted-check and 100-row queue detail windows.
- Canonicalizes legacy verification verdict variants for analytical counting (for example `CONTRICTED` -> `CONTRADICTED` and formatting variants of `INCONCLUSIVE` -> `INCONCLUSIVE`). Raw variants remain visible as audit metadata only.
- Keeps factual verdict counts, queue workflow statuses, and relevance-gate statuses separate so overlapping lifecycle categories are not presented as evidence outcomes.
- Future persisted/queue LLM verdict writes are canonicalized at write time.

## Red-team language hardening
- Spot/yield/asset-price moves may be described as consistent with a mechanism, but cannot establish what the market is pricing/believes without an explicit implied-pricing measure.
- Positioning normalization may reduce a squeeze contribution, but squeezes are no longer described as categorically self-limiting.
- Large historical returns are observations; only an action taken primarily because of the move may be described as chasing.

## Compatibility
- Score model remains `3.4.1`; schema remains `3.4.1`. No regime scores, trigger thresholds, Treasury-financing math, or portfolio formulas changed.
