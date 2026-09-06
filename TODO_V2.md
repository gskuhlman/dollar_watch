# dollar_watch — Prioritized Product Backlog

The backlog is ranked by **decision value**, not by ease of implementation. A feature is high priority if it can warn earlier, disprove the thesis, identify the transmission mechanism, or materially change what the portfolio should do.


## V2.4 — Completed from third red-team review

- [x] Rebuild Treasury buyback monitoring around official TreasuryDirect schedule/results evidence; separate announced capacity, offered par and accepted par.
- [x] Treat partial buyback coverage as partial/missing evidence rather than a benign zero.
- [x] Add Fed Treasury bill / nominal note-bond / TIPS composition series and classify bill-heavy accumulation separately from QE/fiscal-rescue claims.
- [x] Add aging, replacement and expiration states to auction-based machine triggers.
- [x] Prevent stale clean-auction KILL evidence from staying fully active immediately before replacement auctions.
- [x] Add Generic / Critical / Effective regime evidence coverage; missing verified policy intent now materially lowers managed-devaluation coverage.
- [x] Add scenario hedge-alignment reporting instead of a misleading single “percent defensive” label.
- [x] Label pre-lineage snapshots `LEGACY_BASELINE` and suppress false taxonomy comparisons.
- [x] Reject incomplete verification-queue rows before analysis.
- [x] Replace raw serialized-payload truncation with record-safe LLM payload compaction.
- [x] Add V2.4 regression tests for buybacks, Fed composition classification, trigger aging, critical coverage, scenario alignment, legacy lineage and JSON-safe LLM compaction.


## V2.3 — Completed from second red-team review

- [x] Rebuild Treasury auction ingestion without brittle `fields=` requests; normalize legacy/current FiscalData field aliases locally.
- [x] Add dedicated Treasury `upcoming_auctions` catalyst feed independent of historical results scoring.
- [x] Treat auction-feed failure as missing evidence, never as benign zero-stress evidence.
- [x] Separate transactional $1 stablecoins from yield-bearing/tokenized Treasury-RWA products before peg testing.
- [x] Track tokenized Treasury/RWA supply as a distinct structural digital-dollar/Treasury-demand channel.
- [x] Filter future-dated FRED historical observations and flag any remaining source-date-ahead condition in Data Health.
- [x] Pass prior saved snapshot context and explicit regime deltas to the local LLM for true run-to-run analysis.
- [x] Prevent the red-team prompt from treating `2Y > SOFR` alone as proof of Fed hike pricing.
- [x] Add a prioritized headline verification queue with preferred primary-source families.
- [x] Replace boilerplate portfolio `Why` text with live regime/driver-based rationale.
- [x] Add regression tests for auction schema aliases, RWA/stablecoin classification, future source-date hygiene, prior-run deltas and rationale output.


## V2.1 — Completed from first red-team review

- [x] Split fiscal/Treasury supply stress from inflation/monetary debasement.
- [x] Add a separate FX positioning-squeeze regime.
- [x] Apply source freshness/confidence before an indicator enters regime math.
- [x] Use actual IMF COFER observation-quarter freshness rather than retrieval time.
- [x] Fix stablecoin depeg alert/display-universe inconsistency.
- [x] Suppress token positions and enforce a minimum actionable dollar trade.
- [x] Add machine-readable 10Y/30Y auction confirmation and reversal triggers.
- [x] Add SOFR-IORB, SOFR99-IORB, TGCR-IORB and repo-dispersion signals.
- [x] Fix FRED trend windows to use calendar time across daily/weekly/monthly series.
- [x] Add Treasury Monthly Statement fiscal-flow parsing.
- [x] Add IMF COFER reserve-share ingestion.
- [x] Add Fed H.4.1 asset decomposition (Treasuries, MBS, lending, swaps, residual).
- [x] Add source-credibility tiers, provenance, verification status and score gate.
- [x] Prevent unverified AI/headline findings from changing hard policy scores.
- [x] Add LLM-assisted claim-vs-cited-source checker; human verification remains mandatory.
- [x] Add machine-evaluated confirmation/reversal conditions to alerts.
- [x] Expand stress tests and portfolio targets from four to six regimes.

## P0 — Critical decision features

These are required before treating the dashboard as a serious decision-support system.

- [x] **Separate leading indicators from market confirmation.** Early Warning and Confirmation indexes are now distinct.
- [x] **Six independent regimes.** Managed devaluation, fiscal/Treasury supply stress, inflation/monetary debasement, dollar funding squeeze, reserve-confidence crisis, FX positioning squeeze.
- [x] **CFTC FX positioning.** Leveraged-money and asset-manager positioning in major currency futures with historical percentile pressure.
- [x] **Country-level TIC Treasury holdings.** China, Japan, foreign official holdings, major BRICS/Gulf holders, monthly changes and YoY direction.
- [x] **Treasury auction absorption.** Bid-to-cover and primary/direct/indirect bidder mix versus prior same-tenor auctions.
- [x] **Term-premium monitoring.** Adds the 10Y term premium so rising long yields can be separated from expected short-rate changes.
- [x] **Dollar funding/liquidity signals.** VIX, high-yield spreads, NFCI, reserve balances, TGA and Federal Reserve foreign swap usage.
- [x] **Stablecoin structural-dollar signal.** Total USD stablecoin supply, growth, large stablecoins and USD1 visibility.
- [x] **Data-health / freshness engine.** Each source reports availability, age and confidence; portfolio overlay is reduced when confidence is poor.
- [x] **Anti-chasing guardrail.** Large recent moves in gold, Bitcoin, foreign equities, CHF or commodities cap new buys.
- [x] **Portfolio turnover guardrail.** Maximum one-run turnover prevents a single model change from forcing an all-in repositioning.
- [x] **Hard recommendations with reversal triggers.** BUY/HOLD/REDUCE, dollar trade amount, reason and explicit condition that would reverse the trade.
- [x] **Scenario stress testing.** Current vs recommended portfolio under all six modeled regimes.
- [x] **Policy/foreign-actor evidence journal.** Manual events retain actor, source, impact and notes for auditability.
- [x] **Change alerts.** Regime jumps, acute levels, phase changes, weak data confidence and large portfolio trades.
- [x] **Headless collector.** Scheduled snapshots can run without Streamlit.
- [x] **Generic webhook alert delivery.** Optional environment-variable webhook for external notification workflows.
- [x] **Local LLM red-team analysis.** Full V2 snapshot is sent to the configured local OpenAI-compatible model.
- [x] **Disconfirming-evidence architecture.** Stablecoin demand, hawkish rates, strong Treasury demand and dollar-squeeze dynamics can lower/offset devaluation conviction.

## P1 — High priority next additions

These are the next features most likely to improve warning time or portfolio decisions.

- [ ] **True Treasury auction tails.** Capture when-issued yield immediately before auction versus stop-out yield. Requires a dependable intraday WI source.
- [ ] **Treasury market-depth / bid-ask data.** Track order-book depth and price impact, especially 10Y/30Y.
- [ ] **Repo fails and fails-to-deliver.** Add NY Fed primary-dealer Treasury settlement/fails data.
- [x] **SOFR distribution / repo dispersion baseline.** SOFR99-IORB, TGCR-IORB and TGCR dispersion are implemented; richer transaction-level repo detail remains P1.
- [ ] **Cross-currency basis.** EUR/USD, JPY/USD and CHF/USD basis as direct dollar-funding-pressure gauges.
- [ ] **FX options risk reversals.** 1W/1M/3M USD downside skew for EUR, JPY, CHF and broad dollar indexes.
- [ ] **FX implied volatility term structure.** Detect demand for near-term crisis protection before spot moves.
- [ ] **Treasury futures basis-trade monitor.** Futures/cash dislocation, hedge-fund leverage proxies and dealer repo exposure.
- [ ] **CFTC Treasury futures positioning.** Leveraged-fund shorts and asset-manager longs by tenor.
- [ ] **TIC monthly transaction flows.** Purchases/sales of Treasuries, agencies, equities and corporate bonds in addition to holdings.
- [ ] **Expanded historical TIC country database.** Preserve monthly country series locally rather than only the rolling Table 5 window.
- [ ] **Foreign FX-hedge-cost model.** Estimate hedged Treasury yields for Japanese and European investors.
- [ ] **Treasury auction calendar/event risk.** Flag unusually large refunding weeks and maturity concentrations before auctions occur.
- [ ] **Debt-service/fiscal engine.** Interest expense/revenue, weighted average maturity, refinancing wall, deficit/GDP and issuance requirements.
- [ ] **Debt scenario calculator.** Project annual interest cost under alternative yield curves and deficit paths.
- [ ] **Fed reaction-function model.** Compare current policy rate with inflation/labor conditions and estimate easing/tightening pressure.
- [ ] **Market-implied Fed path.** Futures/OIS-derived expected policy path rather than only spot Treasury yields.
- [ ] **Commodity settlement tracker.** Quantify material oil/LNG/metals contracts settling outside USD rather than relying on headlines.
- [ ] **CIPS / alternative-payment usage metrics.** Transaction counts/value, geographic growth and interoperability milestones.
- [ ] **SWIFT currency-share data.** Track actual payment usage by USD/EUR/CNY rather than announcements.
- [ ] **Central-bank gold accumulation database.** Country-level monthly/quarterly changes with reserve share and valuation adjustment.
- [x] **IMF COFER USD reserve-share ingestion.** USD share and lag-aware confidence are implemented. [ ] Add fuller EUR/CNY decomposition and FX-valuation adjustment.
- [ ] **Stablecoin Treasury-demand estimator.** Apply issuer-specific reserve composition instead of treating supply as a generic dollar-demand proxy.
- [ ] **Stablecoin issuer concentration / redemption risk.** USDT, USDC, USD1 and others scored for reserve/custodian/peg concentration.
- [x] **Tokenized Treasury/RWA monitoring baseline.** Separate RWA products from stablecoins and track observed supply. [ ] Add issuer-specific reserve/on-chain composition and flows.
- [ ] **Automatic policy-document ingestion.** Treasury/Fed/White House/CEA/USTR speeches and releases parsed directly, not through headlines.
- [ ] **Actor statement-change detection.** Compare current wording with each actor's prior statements and identify shifts in policy language.
- [ ] **Financial-disclosure change monitor.** Track new public disclosures for senior officials and relevant business/economic interests while keeping exposure separate from motive claims.
- [ ] **Foreign-policy actor profiles.** China PBOC/SAFE, BOJ/MOF, ECB, SNB, Saudi/UAE monetary authorities, BRICS institutions.
- [ ] **Sanctions / reserve-freeze tracker.** New sanctions that increase incentives for reserve diversification.
- [ ] **Geopolitical event severity model.** Taiwan, Middle East, Russia/Europe and cyber incidents scored by financial transmission channel.
- [x] **Verification gate baseline.** Unverified/headline/AI findings cannot affect hard policy scores; verified sourced evidence can. [ ] Add automatic claim-content corroboration across primary/two independent sources.
- [x] **Source credibility registry baseline.** Primary > major news > research > other; expand source catalog and domain-specific rules over time.
- [ ] **Recommendation attribution.** Exact contribution of every signal to every percentage-point portfolio change.
- [ ] **Tax-aware trading mode.** Optional capital-gain/tax-lot friction before recommending reallocations.
- [ ] **Account-type constraints.** Taxable/IRA/401(k), no-crypto, no-physical-gold, ETF-only, Treasury-direct, etc.
- [ ] **Maximum/minimum asset constraints.** User-configurable hard bands per asset.
- [ ] **Liquidity reserve constraint.** Preserve user-defined operating/emergency cash regardless of macro signal.
- [ ] **Rebalancing bands / hysteresis.** Require a signal to remain beyond threshold for N observations before repeated trading.
- [ ] **Alert cooldown/deduplication.** Prevent repeated identical alerts on every collector run.
- [ ] **Email/Slack/Telegram delivery adapters.** Optional notification channels in addition to generic webhook.

## P2 — Medium priority analytical features

- [ ] **Historical backtest engine.** Reconstruct regime scores daily/weekly over multiple crises.
- [ ] **Walk-forward calibration.** Tune thresholds only using information available at each historical date.
- [ ] **Probability calibration.** Convert heuristic 0–100 scores into empirical event frequencies after enough history exists.
- [ ] **False-positive/false-negative report.** Identify which signals cried wolf and which crises were missed.
- [ ] **Change-point detection.** Detect structural breaks in DXY, term premium, foreign holdings and correlations.
- [ ] **Correlation-regime monitor.** Gold/yields/USD/stocks correlations often flip in crises; detect those flips explicitly.
- [ ] **Principal-component / factor model.** Separate global risk-off, U.S. fiscal, inflation and dollar-specific factors.
- [ ] **Volatility-adjusted momentum.** Use return divided by realized volatility rather than raw percentage changes.
- [ ] **Cross-sectional reserve-alternative score.** Compare USD, EUR, JPY, CHF, CNY and gold on yield, liquidity, capital controls and fiscal credibility.
- [ ] **Relative real-yield model.** U.S. real yields versus Europe/Japan/Switzerland as a currency driver.
- [ ] **Purchasing-power model.** CPI/PCE and trade-weighted import-price effects on domestic cash/savings.
- [ ] **Bank-deposit risk module.** FDIC limits, uninsured deposit concentration and bank funding conditions.
- [ ] **Money-market/T-bill spread monitor.** Detect distortions in very-short-dollar instruments.
- [ ] **Commercial-paper / FRA-OIS style stress proxies.** Additional private dollar-funding indicators.
- [ ] **Corporate USD debt wall.** Foreign corporate dollar maturities and refinancing needs.
- [ ] **Sovereign USD debt stress.** Emerging-market external debt service as a potential dollar-squeeze amplifier.
- [ ] **ETF/fund-flow monitoring.** Gold, Treasury, international equity and crypto fund flows.
- [ ] **Bitcoin liquidity/funding monitor.** ETF flows, stablecoin liquidity, futures basis and liquidation risk.
- [ ] **Gold physical-premium monitor.** Shanghai/London/COMEX spreads and central-bank/Asian physical demand.
- [ ] **Commodity inventory/supply shock module.** Separate dollar weakness from real supply shocks.
- [ ] **U.S. equity factor decomposition.** Exporters, pricing power, energy/materials, duration/growth, banks.
- [ ] **Foreign equity regional allocation.** Europe/Japan/Canada/Australia rather than one EFA bucket.
- [ ] **Currency basket hedge.** CHF/EUR/JPY weighting based on relative policy and valuation.
- [ ] **TIPS maturity optimizer.** 5Y vs 10Y vs individual TIPS ladder based on real curve/breakevens.
- [ ] **Treasury-bill ladder generator.** Concrete maturities and roll schedule from current auction calendar.
- [ ] **Physical-gold vs ETF allocation mode.** User preference, storage/spread/liquidity tradeoffs.
- [ ] **Execution checklist.** Suggested limit orders, staged entries and maximum daily trade size without brokerage automation.
- [ ] **Portfolio drawdown budget.** User-defined maximum modeled loss per scenario.
- [ ] **Expected-regret optimizer.** Balance cost of hedging a crisis that never occurs against damage from being unhedged.
- [ ] **Monte Carlo stress simulator.** Correlated distributions around each scenario rather than fixed shocks.
- [ ] **Scenario builder UI.** User changes USD decline, inflation, yields, gold, equities and FX assumptions.
- [ ] **Narrative consistency check.** Flag when analyst notes assert something contradicted by current data.
- [ ] **LLM evidence citations.** Force local-model analysis to cite source IDs/URLs carried in the snapshot.
- [ ] **LLM structured output.** JSON schema for thesis, counter-thesis, trades, confidence and reversal triggers.
- [ ] **LLM ensemble.** Optional second local model as independent red-team reviewer.
- [ ] **Manual “known fact” lock.** Facts can be marked verified so headline noise cannot overwrite them.
- [x] **Headline verification queue baseline.** Prioritized claims-to-check with primary-source hints. [ ] Extend to signal-jump investigation TODOs when a quantitative indicator moves without an identified cause.

## P3 — Useful / experimental / lower-priority features

- [ ] **Intraday dashboard mode.** Higher-frequency market/funding refresh for acute events.
- [ ] **Mobile layout / PWA packaging.** Better phone monitoring.
- [ ] **Desktop executable packaging.** PyInstaller/Nuitka Windows package.
- [ ] **Multi-user authentication.** Useful if hosted outside the LAN.
- [ ] **Encrypted secrets vault.** Store API keys/webhooks outside plain environment variables.
- [ ] **PostgreSQL option.** SQLite remains preferable for one-user local deployment.
- [ ] **Grafana/Prometheus export.** Operational monitoring integration.
- [ ] **REST API.** Expose current scores/recommendations to other local tools or n8n.
- [ ] **n8n workflow templates.** Alerts, research requests, Gmail summaries and archival flows.
- [ ] **Telegram bot interface.** Ask “what changed?” from a phone.
- [ ] **Voice summary.** Local TTS of daily/weekly risk changes.
- [ ] **PDF/HTML weekly report export.** Archive an investment-committee-style report.
- [ ] **CSV/JSON evidence export.** Portable audit archive.
- [ ] **Git-versioned methodology.** Every scoring-rule change carries a model version and migration note.
- [ ] **Model comparison mode.** Run V1/V2/future scoring systems on the same snapshot.
- [ ] **Shadow portfolio.** Track recommended trades without actually changing the user's baseline.
- [ ] **Performance attribution.** Did the hedge decisions add value relative to a benchmark?
- [ ] **Benchmark portfolio comparison.** 60/40, all-T-bill, S&P 500, permanent portfolio, etc.
- [ ] **Custom asset universe.** User adds specific ETFs/funds/individual Treasuries.
- [ ] **Broker read-only integration.** Import actual positions; no trading authority by default.
- [ ] **Optional broker execution.** Only after extensive safeguards and explicit user confirmation; deliberately low priority.
- [ ] **Prediction-market signals.** Use only as weak external probability inputs.
- [ ] **Social-media anomaly monitor.** Very low-confidence early-warning channel with strict corroboration requirements.
- [ ] **Cyber/financial-infrastructure status feeds.** Fedwire, CHIPS, SWIFT, major exchange and bank outage monitoring.
- [ ] **Shipping/trade-nowcast signals.** Commodity and trade-flow changes before official data.
- [ ] **Satellite/alternative data.** Experimental geopolitical/commodity indicators.

## Features intentionally *not* treated as automatic facts

- A policymaker's financial exposure is **not evidence of motive**.
- BRICS rhetoric is **not de-dollarization** unless settlement, reserve or infrastructure usage changes.
- Gold rising is **not automatically a dollar crisis**.
- A Treasury buyback is **not automatically QE**.
- Stablecoin supply is **not equivalent dollar-for-dollar to Treasury demand**.
- DXY falling is **not enough to call a reserve-confidence crisis**.
- A crisis can initially cause a **dollar squeeze and stronger USD**, even if the long-run problem is dollar confidence.
