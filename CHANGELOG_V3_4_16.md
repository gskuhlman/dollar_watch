# V3.4.16

## CFTC crowding-semantics hardening

- Added deterministic crowding labels to CFTC summary rows so absolute net shorts cannot be confused with historically crowded shorts.
- For EUR/JPY/CHF, low `leveraged_3y_percentile` means unusually short; high percentile means relatively longer / less historically short.
- Added `leveraged_short_crowding_score` = 100 - percentile for foreign-currency contracts.
- Added LLM guardrail prohibiting "crowded short" language when `leveraged_crowding_state` says otherwise.
- Treasury-financing summarization accepts an optional `as_of` timestamp for deterministic release-timeliness tests; production behavior is unchanged when omitted.
- No changes to score model 3.4.1, schema 3.4.1, trigger thresholds, portfolio logic, or Treasury-financing math.
