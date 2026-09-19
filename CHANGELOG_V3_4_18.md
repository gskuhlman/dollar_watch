# V3.4.18

## Treasury auction calendar integrity

- Treats Treasury auction dates as date-only **America/New_York** calendar events instead of UTC-midnight timestamps, preventing the prior U.S. evening from being mislabeled as the auction day after UTC rolls over.
- Merges FiscalData's `upcoming_auctions` convenience feed with the richer `auctions_query` future rows by CUSIP/date and **prefers the general table's inflation-index/FRN classification** when both exist.
- Carries `instrument_class`, inflation-index/FRN flags, and source channel into the nominal upcoming-auction payload.
- Future nominal auction claims in local-LLM output are linted against the deterministic `snapshot.upcoming_auctions` calendar. The model may not invent a future date from cadence/prior runs, and may not treat a TIPS/FRN auction as a nominal replacement.
- Generated analysis is told to use absolute Treasury auction dates rather than `today`/`tomorrow` so UTC rollover cannot misstate U.S. event timing.
- Score model remains **3.4.2**; this fixes event-calendar/lifecycle integrity rather than regime scoring math.

## Period-specific verification integrity

- Adds a deterministic claim/source temporal-consistency gate for explicit months/quarters.
- A source passage about July cannot return `SUPPORTED` for an August-specific claim merely because the page was published in August or contains unrelated August text.
- Period mismatches are downgraded to `INCONCLUSIVE`, not `CONTRADICTED`, because the source can still be true for the other period.
- Existing persisted `SUPPORTED` checks whose verifier explanation reveals an explicit claim/source period mismatch are quarantined from active evidence; matching queue rows are downgraded to `INCONCLUSIVE`.
- This specifically prevents country/month evidence such as a July PBoC gold purchase from being promoted into an August verified fact without an August source.

No regime weights, portfolio rules, Treasury-financing formulas, or fixed-horizon score-model lineage changed.
