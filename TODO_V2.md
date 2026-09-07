# dollar_watch roadmap

## V3.3 — production bug-fix / feature freeze completed
- [x] English-first Japan MOF monthly intervention ingestion.
- [x] Validate before caching and purge invalid MOF cached content.
- [x] Monthly intervention totals are occurrence/amount only; direction remains UNKNOWN until detailed operations data.
- [x] Smooth JPY/EUR/CHF spot-confirmation ramps; remove threshold cliffs.
- [x] Carry Treasury Sep 9-Nov 4 long-end buyback-capacity announcement into the forward-event calendar.
- [x] Full inherited regression suite plus V3.3 tests.

## Feature freeze after V3.3
Use live history to calibrate thresholds and decision performance before adding new architecture.

# dollar_watch roadmap

## V3.2 — Official-source resilience / intervention history completed
- [x] Normalize Japanese full-width digits/punctuation and parse `兆` / `億` MOF intervention amounts robustly.
- [x] Add retry/backoff, Treasury Readouts index resolution, and auditable last-known-official cache fallback for transient 503/403 failures.
- [x] Track U.S. FX intervention by quarter, actor, currency, direction/purpose, and broad-dollar implication.
- [x] Preserve Q4 2025 Treasury/ESF Argentina intervention as targeted stabilization rather than broad-dollar evidence.
- [x] Add lagged NY Fed Q2 2026 official FX-swap/basis validation without inflating live offshore-funding coverage.
- [x] Add V3.2 UI/audit fields and regressions.

## Feature freeze after V3.2
No new regime or broad indicator family. Next work is calibration, false-positive measurement, forecast/decision performance, and source maintenance.


## V3.1 — Canonical policy / FX evidence hotfix completed
- [x] Direct Japan MOF monthly FX-intervention ingestion.
- [x] Deterministic NY Fed U.S. FX-intervention finding ingestion.
- [x] Canonical exact-source routing for Bessent/Ueda, Japan-U.S. finance-ministerial, GENIUS Act, and NY Fed FX reports.
- [x] Separate bilateral FX policy from direct intervention and broad-dollar intent.
- [x] Add policy-evidence action taxonomy and target-specific score effects.
- [x] Seed canonical sources into the persistent verification queue without repeatedly resetting checked rows.
- [x] Add V3.1 regressions.

## Feature freeze after V3.1
Focus next on calibration, forecast/decision performance, source reliability, and live event behavior. Do not add a new regime without evidence that the current taxonomy cannot represent the failure mode.

# dollar_watch — Prioritized Product Backlog

The backlog is ranked by **decision value**, not by ease of implementation. A feature is high priority if it can warn earlier, disprove the thesis, identify the transmission mechanism, or materially change what the portfolio should do.


## V3.0 — Feature-freeze baseline completed

- [x] Route policy research to actual official news/remarks/policy surfaces before semantic ranking; reject privacy/help/assistance pages.
- [x] Rewrite standing policy probes as narrow, falsifiable propositions.
- [x] Add bounded **positive and negative** managed-devaluation score effects from human-approved, source-relevant, LLM-SUPPORTED primary evidence.
- [x] Allow approved policy evidence to raise managed-devaluation critical coverage.
- [x] Add stateful funding-stress hysteresis and a recovery KILL that is valid only after a prior stress episode.
- [x] Treat swap-line/FIMA draws as dollar-funding stress, never a reason to add non-USD exposure.
- [x] Add funding-stress pre-commitment toward T-bills and away from BTC/unhedged ex-US risk.
- [x] Split funding-squeeze alignment into direct, conditional/unreliable, USD-rate-sensitive, and vulnerable exposure.
- [x] Reconcile completed vs upcoming long-end buyback capacity fields.
- [x] Add V3.0 regressions for all of the above.

### Feature-freeze rule

Do not add another regime or broad indicator family until the model has accumulated enough live history to evaluate trigger precision, false positives, portfolio turnover and event-response quality. New work should first improve **data quality or calibration**.

## V2.6 — Completed from fourth red-team review

- [x] Discover completed TreasuryDirect buyback result XMLs independently of the dynamic webpage; derive official result filenames from operation date/start time and use a bounded fallback probe.
- [x] Separate buyback schedule health from buyback-results health so announced capacity cannot masquerade as observed completed activity.
- [x] Track total par offered, total par accepted, completed-operation count, attempted result URLs and missing-result diagnostics.
- [x] Separate median `SOFR-IORB` funding stress from `SOFR99-IORB` repo-tail stress.
- [x] Add repo-tail percentile, z-score and persistence logic rather than treating a tail reading as distance to the median trigger.
- [x] Split domestic-dollar funding visibility from offshore FX-swap/cross-currency-basis coverage; reduce effective funding-squeeze coverage while offshore basis data are unavailable.
- [x] Add red-team language discipline: low critical coverage must be described as unknown/unverified, never as affirmative absence.
- [x] Add official-source-family discovery and claim-relevance ranking for the verification queue.
- [x] Add Ollama/OpenAI-compatible claim checks against top primary-source candidates while preserving the human VERIFIED gate.
- [x] Persist primary-source verification checks in SQLite with verdict, source tier, model and provenance.
- [x] Add V2.6 regression tests for buyback URL generation/discovery, repo-tail separation, offshore funding coverage and verification persistence/relevance.


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
- [ ] **Cross-currency basis.** EUR/USD, JPY/USD and CHF/USD basis as direct dollar-funding-pressure gauges. V2.6 now exposes this absence explicitly in coverage rather than pretending global funding is fully observed.
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
- [~] **Automatic policy-document ingestion.** V2.6 can discover/rank/fetch primary-source candidates for queued claims; dedicated structured feeds and full change detection remain open.
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

## V2.6 completed

- [x] Buyback-result completeness gating and max-amount parse status.
- [x] Link expired 10Y/30Y auction evidence to next announced same-tenor auction.
- [x] Separate Fed central-bank liquidity swaps from FIMA foreign-official repo.
- [x] Add TIC Treasury net-transaction and long-term valuation-change decomposition.
- [x] Stop treating changes in holdings as equivalent to transaction demand.
- [x] Auto-persist complete discovery claims into a deduplicated verification queue.
- [x] Optional bounded automatic P0/P1 primary-source + LLM claim checking, still human-gated for VERIFIED scoring.
- [x] Conditional weak-auction portfolio response: inflationary fiscal vs real-yield fiscal stress.
- [x] V2.6 regression tests.

## Freeze / observe next

- [ ] Accumulate live history through Treasury auctions, CFTC updates, TIC/COFER releases and FOMC events before changing core regime architecture again.
- [ ] Calibrate trigger thresholds against accumulated and historical event data.
- [ ] Add dependable cross-currency-basis/FX-swap feeds if a trustworthy accessible source is available.
- [ ] Replace static scenario asset shocks with empirically estimated regime/event betas after sufficient history exists.


## V2.7 completed

- [x] Preserve buyback result maximum capacity through the schedule/results merge.
- [x] Treat missing buyback capacity/intensity as `UNKNOWN`, not 0.
- [x] Add deterministic semantic relevance gating before LLM source verification.
- [x] Persist candidate relevance score/status and human source-check approval state.
- [x] Add verification queue review controls for APPROVED / REJECTED / DISPUTED checks.
- [x] Canonicalize reopened coupon maturities to benchmark tenors without conflating TIPS/FRNs.
- [x] Supplement the upcoming-auction convenience feed from Treasury's full future auction table.
- [x] Generalize 1Y/3Y historical percentile and z-score context across populated FRED indicators.
- [x] Add V2.7 regression tests.

## Freeze / observe after V2.7

- [ ] Accumulate live history through Treasury auctions, CFTC updates, TIC/COFER releases and FOMC events before changing the six-regime architecture.
- [ ] Add dependable cross-currency-basis / FX-swap data only when a trustworthy accessible source is identified.
- [ ] Calibrate trigger thresholds against historical and newly accumulated event data.
- [ ] Replace static scenario sensitivities with empirical event/regime betas once enough observations exist.


## V2.8 completed

- [x] Harden TreasuryDirect buyback maximum-capacity parsing for nested XML shapes.
- [x] Keep buyback intensity `UNKNOWN` whenever capacity remains unavailable.
- [x] Quarantine legacy persisted source checks that fail current semantic relevance rules.
- [x] Add high-specificity hard topic anchors for stablecoin/gold/BRICS/FX-intervention verification.
- [x] Add a free EUR/JPY/CHF front-futures-vs-spot dislocation proxy without mislabeling it cross-currency basis.
- [x] Raise offshore funding observation coverage only modestly when proxy pairs are available.
- [x] Surface quarantined source checks separately in the verification UI.
- [x] Add V2.8 regression tests.

## Freeze / observe after V2.8

- [ ] Accumulate real run history across Treasury auctions, CFTC releases, TIC/COFER updates and Fed events before changing the six-regime architecture.
- [ ] Add true cross-currency-basis / FX-swap data only if a dependable accessible source becomes available.
- [ ] Calibrate thresholds and portfolio reactions against historical and newly observed event outcomes.
- [ ] Replace static scenario sensitivities with empirical regime/event betas after enough observations accumulate.


## V3.0 completed

- [x] Repair long-end nominal Treasury buyback sector attribution when result XML omits `maturity_bucket`.
- [x] Report completed long-end offered/accepted/max-capacity and acceptance-vs-capacity separately.
- [x] Normalize discovery-news buckets to primary-source verification families before P0/P1 prioritization.
- [x] Add standing policy probes so the verification queue cannot go dark when RSS/news discovery is unavailable.
- [x] Share headline-to-verification mapping between Streamlit and the headless collector.
- [x] Add V3.0 regressions for known 2026 long-end operations and guaranteed research-lead generation.

## Freeze / observe after V3.0

Do not change the six-regime architecture merely because a single live event disagrees with the model. Accumulate history through auctions, CFTC, TIC/COFER, funding events, and verified policy statements; adjust thresholds only when repeated observed behavior justifies calibration.
