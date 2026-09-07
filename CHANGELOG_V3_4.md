# dollar_watch V3.4 — Treasury Financing Transmission

## Scope
V3.4 preserves the six existing crisis regimes and adds a separate Treasury-financing transmission layer. The new layer asks two different questions: **who absorbs net Treasury issuance?** and **how is that absorption financed?** They are intentionally not collapsed into one number.

## New data
Quarterly Federal Reserve Z.1/FRED transaction series (all SAAR, $ millions):
- `BOGZ1FA313161105Q` — net marketable Treasury issuance.
- `BOGZ1FA713061103Q` — Federal Reserve / central-bank Treasury transactions.
- `BOGZ1FA763061100Q` — U.S.-chartered depository-institution Treasury transactions.
- `BOGZ1FA473061105Q` — credit-union Treasury transactions.
- `ROWTSAQ027S` — rest-of-world Treasury transactions.
- `BOGZ1FA663061105Q` — security-broker/dealer net Treasury transactions.
- `BOGZ1FA633061105Q` — money-market-fund Treasury transactions.
- `HNOTSBQ027S` — household/nonprofit Treasury transactions.
- Additional F3.2.t sector series cover foreign banking offices, affiliated-area banks, state/local governments, insurers, private/federal/state-local pensions, mutual/closed-end/exchange-traded funds, GSEs, ABS issuers, holding companies, other financial business, and nonfinancial business.

Funding/intermediation overlay (Z.1 F4.1.s levels; **not** added to Treasury demand):
- dealer repo liabilities/assets, MMF repo assets, U.S.-bank repo liabilities/assets, and foreign-bank repo liabilities/assets;
- dealer gross repo balance sheet and net repo borrowing are derived diagnostics. Repo collateral is not Treasury-only.

Higher-frequency confirmation:
- `M2SL` — M2 money stock.
- `DPSACBM027SBOG` — deposits at all commercial banks.
- `USGSEC` — Treasury + agency securities at all commercial banks (proxy only; not Treasury-only).

## Calculations
- `monetary_capable_absorption_pct = (Fed + broad U.S. banking-system/depository sector) / net marketable issuance`, where the broad bank bucket includes U.S.-chartered institutions, foreign banking offices in the U.S., affiliated-area banks, and credit unions. The eSLR rule itself applies only to covered large U.S. banking organizations, so its scope is displayed separately.
- `monetary_plus_dealer_pct` is displayed as balance-sheet/intermediation concentration, not as monetization.
- M2 and bank-deposit 3-month annualized growth are averaged into `money_confirmation` when available.
- Negative sector flows are retained.
- A displayed residual equals issuance minus only the displayed tracked holder buckets and is deliberately left unattributed.

## Financing-pressure state
The new GREEN/YELLOW/ORANGE/RED state is a heuristic pressure classification and not a probability:
- GREEN: monetary-capable absorption <20%.
- YELLOW: >=20% but monetization-like confirmation is incomplete.
- ORANGE: >=35% plus money/deposit confirmation >=5% annualized.
- RED: >=50%, money/deposit confirmation >=6%, plus at least one market-structure confirmation (dealer warehousing >=15% or foreign absorption <15%).

The financing state does **not** alter the six-regime taxonomy in V3.4.

## SLR semantics
The app records the enhanced-SLR recalibration as effective April 1, 2026 (early adoption permitted January 1, 2026). It explicitly records `treasury_exemption=false` and `reserve_exemption=false`. The rule is treated as a bank-balance-sheet-capacity overlay, not a Treasury holder flow.

## Double-counting controls
- Repo and hedge-fund basis-trade financing are funding-layer overlays and are not added as Treasury-holder demand.
- Dealer inventory is not treated as final end-buyer demand.
- Stablecoin/tokenized-Treasury exposure remains look-through context and is not added if the underlying Treasury is already represented by another holder sector.
- H.8 `USGSEC` cannot replace quarterly Treasury-only Z.1 ownership because it includes agency securities.

## UI / pipeline
- New **Treasury Financing** tab.
- New `Treasury financing / Z.1` source-health row and component confidence.
- Financing metadata is persisted into snapshots and included in local-LLM context.
- App/schema version advanced to `3.4`.
- Existing UTF-8 file reads, Streamlit `width="stretch"` usage, and 300-second local-LLM timeout configuration are retained.

## Tests
`test_v34.py` locks:
- monetary-capable absorption math,
- preservation of negative MMF flow,
- money-confirmation gating,
- RED-state confirmation requirement,
- SLR relaxed-but-not-exempt semantics.
