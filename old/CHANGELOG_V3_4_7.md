# dollar_watch V3.4.7 — TIC decomposition integrity patch

- Fixes a red-team arithmetic/lineage failure where the LLM could combine the **grand-total** TIC transaction figure with the **foreign-official** holdings-change figure and then quote the foreign-official transaction amount in the same paragraph.
- `tic_transaction_meta` now carries a self-contained sector label, deterministic transaction-share percentage, reconstructed position change, reconciliation error, and reconciliation status for each decomposition.
- The red-team prompt explicitly forbids cross-sector TIC arithmetic and directs the model to use the supplied same-sector transaction-share percentage rather than recomputing it from nested fields.
- The Positioning & Foreign Flows dashboard now exposes a deterministic TIC transaction/valuation decomposition table with holdings change, transactions, long-term valuation, residual, transaction share, and reconciliation status.
- No six-regime scoring, Treasury-financing score, triggers, or portfolio rules changed. Persisted schema remains 3.4.1.
