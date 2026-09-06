# dollar_watch V2.3 changelog

## Evidence integrity
- Completed auction results and upcoming auctions are now separate channels.
- Auction freshness uses completed auction dates only.
- Per-regime evidence coverage is shown separately from risk.
- Treasury buyback schedule monitoring added from the official quarterly-refunding page.
- Primary-source candidates added to the verification queue.

## Run integrity
- Snapshot lineage: run ID, parent run ID, app version, schema version, run kind.
- Automatic Streamlit snapshots are deduplicated by collected-data timestamp.
- Manual and scheduled-collector saves are explicitly labeled.
- Run-change classification is supplied to the UI/LLM.

## Validation
- Existing engine tests pass.
- Existing V2.2 regression tests pass.
- New V2.3 tests pass.
