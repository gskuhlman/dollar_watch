# dollar_watch — Dollar Crisis Early Warning Dashboard V3.4.5

## V3.4.5 semantic/calendar hardening

- Fixes a silent CFTC-calendar bug: `scoring.py` used `pd.Timestamp` without importing pandas, so derived publication/calendar fields were being swallowed by the existing error guard and returned as null.
- Separates the CFTC lifecycle into latest position-as-of, latest expected Friday publication, next Tuesday position-as-of, and next expected Friday publication.
- Adds an explicit funding-observation scope object so strong domestic repo/facility coverage cannot be narrated as globally benign when live offshore cross-currency-basis/FX-swap coverage is partial.
- Tightens TGA language: a TGA rebuild is a cash-balance rebuild/liquidity drain while funds remain at the Fed; it is not automatically "prefunding future supply."
- Keeps all six regimes and V3.4 Treasury-financing score math unchanged.


## V3.4.4 chart compatibility patch

Treasury Financing history now normalizes mixed historical numeric/string fields and plots in Plotly long form, preventing wide-form dtype failures when snapshots span multiple app versions. Persisted history is not mutated.
A local Python/Streamlit research application that monitors U.S. dollar regime risk and translates changing evidence into bounded, auditable portfolio actions.

## V3.4.4 release-aware financing calibration

V3.4.4 keeps the six-regime model unchanged and tightens the V3.4 Treasury-financing interpretation. Z.1 timeliness is now measured against expected release availability rather than calendar-quarter distance; eSLR inference uses a narrower U.S.-chartered-bank proxy instead of the broad depository bucket; CFTC Tuesday position dates are separated from Friday publication dates; and generated dollar amounts are escaped before Streamlit markdown rendering so currency text is not mistaken for LaTeX.


## V3.4.2 runtime-hardening patch

V3.4.2 keeps the V3.4.1 Treasury-financing model and adds targeted hardening for malformed official PDF xref tables. Recoverable pypdf pointer warnings are suppressed locally; genuine extraction failures still flow to Data Health/cache fallback.

## V3.4.1 Treasury-financing transmission release

V3.4.2 keeps the six crisis regimes intact and adds a separate **Who Is Financing the Deficit?** analytical layer. The purpose is to detect a shift from conventional private/foreign Treasury absorption toward Fed/bank/dealer balance-sheet absorption without falsely calling every Treasury purchase monetization.

- **Quarterly Z.1 holder-flow engine.** Tracks net marketable Treasury issuance across the full major F3.2.t holder map: Fed/central bank, U.S. and foreign-bank offices, credit unions, foreign sector, dealers, MMFs, households, mutual funds/ETFs/CEFs, insurers, pensions, state/local buyers, nonfinancial business, GSEs and other financials.
- **Monetary-capable absorption.** Calculates Fed + U.S. bank/credit-union absorption as a share of issuance. This is explicitly a capacity/transmission measure, not proof of money creation.
- **Money confirmation.** Uses 3-month annualized M2 and commercial-bank deposit growth to confirm whether Treasury absorption is occurring alongside broad-money expansion. H.8 Treasury+agency holdings are displayed as a high-frequency proxy only.
- **Financing regime classifier.** GREEN/YELLOW/ORANGE/RED states combine monetary-capable absorption with money confirmation and market-structure confirmation such as elevated dealer net absorption. The state is a heuristic pressure classification, not a probability.
- **SLR policy state.** Records the April 1, 2026 enhanced-SLR recalibration as `RELAXED`, while explicitly recording that neither Treasuries nor Fed reserve balances were exempted from total leverage exposure.
- **Repo funding layer.** Z.1 F4.1.s dealer, MMF, U.S.-bank and foreign-bank repo levels are shown separately from ownership, including dealer gross repo balance sheet and net repo borrowing. Repo collateral is not Treasury-only, so these values diagnose funding/leverage rather than deficit absorption.
- **Double-counting guardrail.** Holder flows and funding/intermediation are separate layers. Repo, hedge-fund basis trades, stablecoin look-through exposure and SLR capacity are never added as extra Treasury-holder demand on top of Z.1 holders.
- **Negative flows preserved.** Net sellers such as MMFs remain negative in charts and calculations; values are never clamped to zero merely to make shares sum neatly.
- **Historical financing mix.** Adds quarter-by-quarter Fed, bank, dealer, foreign, MMF and monetary-capable absorption shares for backtesting and regime-change analysis.

See `CHANGELOG_V3_4.md` and `test_v34.py`.


## V3.3.1 evidence-semantics patch / production baseline

V3.3.1 does not change the six-regime architecture. It closes two semantic gaps found in the V3.3 live red-team run:

- **Spot confirmation is not observed position unwind.** FX price action may strengthen the FX-positioning-squeeze score, but the dashboard now exposes `observed_position_unwind` separately. `CONFIRMED` requires newer CFTC report-over-report shrinkage in at least two crowded foreign-currency shorts; otherwise the narrative must say spot action is only *consistent with* short-covering.
- **Deterministic facts are distinct from interpretations.** Exact canonical official statements must pass source-specific anchor validation before becoming `DETERMINISTIC_VERIFIED`. Those facts can automatically increase evidence coverage and receive only a 25%-scaled mechanical effect. Motive/intent interpretations remain `HUMAN_APPROVED_INTERPRETATION` and retain the full bounded score effect only after source relevance, LLM support, and explicit approval.
- **Managed-devaluation coverage is more honest.** Direct U.S. intervention facts, bilateral FX-policy facts, and structural-dollar-support facts can raise critical coverage automatically, but broad weak-dollar intent remains human-gated. With current deterministic context alone the design intentionally remains below the 50% broad-intent language gate.
- **Canonical facts no longer need redundant LLM verification.** Deterministically validated exact-source rows enter the queue as `STRUCTURED_VERIFIED`; interpretive claims continue through the LLM/human review workflow.
- **Audit UI added.** The Policy/Evidence tab shows deterministic score-eligible facts separately from approved interpretations; the Positioning tab shows the observed CFTC unwind state and report date.

See `CHANGELOG_V3_3_1.md` and `test_v331.py`.



## V3.3 production bug-fix / feature-freeze release

V3.3 fixes the remaining production discrepancies without changing the six-regime model. Japan MOF ingestion now uses the English monthly release first, validates content before caching, purges unparseable cached MOF pages, and treats monthly intervention totals as non-directional until detailed currency bought/sold data is available. FX spot-confirmation scoring is ramped rather than cliff-triggered at exactly +/-3%. Treasury's announced Sep 9-Nov 4 long-end buyback-capacity increase is carried as a forward policy event even if operation-schedule rows have not yet appeared.

## V3.2 official-source resilience / intervention-history freeze release

V3.2 keeps the six-regime model frozen and hardens the last deterministic policy-data paths. Japan MOF intervention amounts now parse Japanese large-number notation after Unicode normalization; canonical Treasury pages use retry/index-resolution plus a transparent dated last-known-official cache; U.S. FX intervention is represented as a quarter-level actor/currency/purpose timeline rather than a single boolean; and the latest NY Fed quarterly FX report supplies a lagged official validation layer for offshore FX-swap funding conditions without increasing live cross-currency-basis coverage or firing a live funding trigger.

See `CHANGELOG_V3_2.md` and `test_v32.py`.

## V3.1 canonical policy / FX evidence hotfix

V3.1 keeps the six-regime model frozen and replaces the last weak generic-policy-search path with deterministic official-source ingestion. Japan MOF intervention amounts and NY Fed U.S. FX-operation findings are collected directly; canonical Treasury/Japan/NY-Fed policy pages are seeded into the verification queue before generic crawling. Bilateral yen policy, direct FX intervention, broad-dollar policy, dollar-funding stress, reserve-confidence stress, fiscal debt management, and structural dollar support now have separate action classes so they cannot share an inappropriate one-size-fits-all portfolio response.

See `CHANGELOG_V3_1.md` for implementation details and `test_v31.py` for the new correctness regressions.

## V3.0 correctness / feature-freeze release

V3.0 keeps the six-regime model frozen and closes the remaining policy-verification, trigger-state, portfolio-direction and buyback-field consistency gaps.

### New in V3.0

- **Route-aware official-source retrieval.** Treasury/White House/Fed/MOF claims are routed toward actual press releases, statements, speeches and policy pages; privacy/help/financial-assistance pages are rejected before semantic ranking.
- **Narrow falsifiable standing probes.** Research questions now ask testable propositions such as whether Treasury advocates broad dollar depreciation, supports a strong/stable dollar, or frames stablecoins as strengthening the dollar's reserve role.
- **Bidirectional approved policy evidence.** Human-approved + source-relevant + LLM-SUPPORTED primary evidence can move managed-devaluation policy intent either up or down. INCONCLUSIVE/CONTRADICTED checks are not automatically inverted.
- **Critical coverage from approved evidence.** Managed-devaluation critical coverage can now rise when approved policy evidence exists rather than staying mechanically at zero.
- **Stateful funding hysteresis.** Funding stress enters above the hard stress thresholds; the new normalization KILL is valid only after a prior stress episode and requires persistent normalization.
- **Correct swap-line direction.** Large central-bank dollar-swap/FIMA usage is treated as dollar-funding stress: more T-bills/liquidity, less BTC/unhedged ex-US risk—not a reason to add non-USD exposure.
- **Funding-squeeze hedge classes.** Scenario alignment distinguishes direct, conditional/unreliable, USD-denominated rate-sensitive and vulnerable assets.
- **Long-end buyback capacity reconciliation.** Completed long-end capacity and upcoming capacity are separately scoped; the legacy `long_end_max_amount` field can no longer contradict known completed capacity.
- **V3.0 regression suite.** `test_v30.py` locks these behaviors.

V3.0 is intended as the **feature-freeze baseline**. Future work should prioritize live calibration, forecast/decision performance, and data-source upgrades rather than adding new regimes.

## V2.8 cleanup / freeze release

V2.8 keeps the six-regime model unchanged and fixes the remaining localized data-layer issues found in the V2.7 red-team run.

### New in V2.8

- **Buyback max-amount parser hardened.** TreasuryDirect aggregate fields are now recovered even when XML wraps values beneath semantic parent tags. Capacity remains `UNKNOWN` rather than zero whenever Treasury's maximum amount still cannot be established.
- **Legacy verification mismatch quarantine.** Persisted LLM checks tied to a queue candidate that now fails the semantic relevance gate are automatically quarantined, excluded from red-team context, and shown separately for audit.
- **Stronger topic relevance rules.** High-specificity buckets such as stablecoins, central-bank gold, BRICS and FX intervention require discriminating topic anchors; generic words such as `dollar` or `reserve` are insufficient.
- **Indicative offshore FX-forward proxy.** The app optionally uses liquid EUR/JPY/CHF front currency futures versus spot, locally de-trended, to detect unusual forward/spot dislocations. It modestly improves offshore observation coverage when available but is explicitly **not cross-currency basis** and never substitutes for institutional basis data.
- **Verification review hygiene.** Quarantined legacy checks cannot be approved or silently re-enter LLM evidence context.
- **V2.8 regression tests** cover nested buyback XML amounts, unknown capacity behavior, source mismatch rejection/quarantine, and the offshore proxy labeling/coverage rules.

## V2.7 foundations retained

- Benchmark-auction lifecycle hardening and reopened-tenor canonicalization.
- Generalized 1Y/3Y FRED percentile/z-score context.
- Semantic primary-source relevance gate and persistent human approval states.
- Buyback schedule/results completeness gates and `UNKNOWN` intensity semantics.

### V2.6 foundations retained

- TIC holdings changes are separated from active net transactions, valuation effects and residual/custody changes.
- Central-bank liquidity swaps and FIMA foreign-official repo remain separate stress channels.
- Buyback schedule/results completeness gates, mechanism-aware weak-auction actions, automatic claim persistence and policy coverage gates remain active.
- Offshore cross-currency basis remains an explicit blind spot until a dependable accessible feed is configured.

### V2.4 foundations retained

- Fed Treasury purchase taxonomy separates bill accumulation/MBS runoff from automatic QE or fiscal-rescue claims.
- Auction CONFIRM/KILL evidence ages through FRESH, AGING, PENDING_REPLACEMENT and EXPIRED states.
- Generic / Critical / Effective regime coverage, scenario hedge alignment, legacy lineage handling and record-safe LLM compaction remain active.

### Run-history behavior

The interactive app automatically saves one `AUTO_STREAMLIT` record per unique live-data timestamp. Manual saves are `MANUAL`; the headless collector uses `SCHEDULED_COLLECTOR`. Legacy records are labeled rather than silently pretending they belong to the current schema.

## V3.0 risk regimes

Each is an independent **0–100 risk index, not a probability**:

1. **Managed dollar devaluation** — verified policy intent plus positioning/price confirmation.
2. **Fiscal / Treasury supply stress** — term premium, fiscal flows, auction absorption and duration/supply pressure.
3. **Inflation / monetary debasement** — inflation expectations, real-rate/inflation interaction and verified monetary/institutional evidence.
4. **Dollar funding squeeze** — repo/funding stress and forced global demand for dollars.
5. **Reserve-confidence crisis** — official/private dollar demand deterioration with market confirmation.
6. **FX positioning squeeze** — crowded EUR/JPY/CHF shorts unwinding into mechanical USD weakness without a fundamental confidence break.

The dashboard also reports **Early Warning**, **Market Confirmation**, **Data Confidence**, and a normalized **regime mix explicitly labeled NOT A PROBABILITY**.

## Earlier V2.2/V2.1 foundations retained

### Correctness / data plumbing

- **Treasury auction collector rebuilt.** Historical auction results no longer send a brittle `fields=` list. The app fetches Treasury's returned schema, normalizes legacy/current aliases locally (including `announcemt_date`), paginates safely, and keeps failed-source state distinct from a benign zero reading.
- **Dedicated upcoming-auctions endpoint.** Future catalysts use Treasury FiscalData's `upcoming_auctions` table rather than assuming the historical results table is the calendar.
- **Transactional stablecoins separated from tokenized Treasury/RWA products.** USDY/USYC/OUSG/BUIDL-like products can count as structural digital-dollar/Treasury demand, but accumulating NAV above $1 is never treated as a depeg solely because price != $1.
- **Future-dated observations are data-hygiene flags.** FRED historical rows ahead of the machine date are filtered; any other source date that remains ahead is marked `SOURCE_DATE_AHEAD`, age-clamped to zero and confidence-discounted rather than treated as extra-fresh.
- **FRED change windows remain calendar-based.** Daily, weekly and monthly series use approximately 7/30/91/365 calendar-day comparisons.

### Analysis quality

- **True run-to-run LLM context.** The red-team model receives the prior saved scores, triggers, portfolio, market/FRED summaries, auctions/flows and explicit regime deltas. “What Changed” no longer has to be inferred only from rolling-return fields.
- **Rate-path wording hardened.** The LLM is explicitly told that `2Y Treasury > current SOFR` is a carry/rate-path signal, not proof of Fed hike pricing because term/risk premia also matter.
- **Automatic verification queue.** Current headlines are converted to prioritized claims-to-check with preferred primary-source families. They remain discovery leads until explicitly verified.
- **Evidence-based portfolio rationale.** The `Why` column now cites the top live regime indices and active causal drivers, and explains why the asset belongs in the current decision. Generic “highest regime is X” boilerplate was removed.

### V2.1 foundations retained

- Six independent risk regimes: managed devaluation, fiscal/Treasury supply stress, inflation/debasement, dollar funding squeeze, reserve-confidence crisis and FX positioning squeeze.
- Freshness/confidence is applied before TIC/COFER/CFTC/fiscal/auction/stablecoin inputs enter hard scoring.
- Verified-evidence gate: unverified headlines/AI findings cannot silently change hard policy scores.
- Source tiers/provenance and LLM claim-vs-cited-source checking.
- SOFR-IORB/SOFR99-IORB/TGCR plumbing, fiscal flows, COFER, Fed balance-sheet decomposition, machine reversal triggers, anti-chasing, minimum position/trade rules and six-regime stress testing.

## Data sources

The app is designed to fail sources independently rather than crash the whole dashboard.

- Yahoo Finance via `yfinance`: DXY proxy, gold, Bitcoin, equities, Treasury/TIPS/commodity/CHF proxies, FX crosses, and front currency futures used only for the V2.8 offshore dislocation proxy.
- FRED/H.4.1: Treasury yields, TIPS, breakevens, term premium, SOFR/IORB/TGCR, Fed assets/liabilities, reserve balances, TGA, swaps and foreign-custody series.
- U.S. Treasury FiscalData: auction absorption and Monthly Treasury Statement fiscal flows.
- U.S. Treasury TIC: major foreign Treasury holders.
- CFTC public TFF dataset: leveraged-money and asset-manager FX positioning.
- IMF COFER: reserve-currency composition.
- DefiLlama: stablecoin supply/history/peg data.
- Google News RSS: discovery/triage only; headlines do not become verified evidence automatically.

## Windows setup

Python 3.11 or 3.12 is recommended.

```powershell
cd dollar_watch
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Or double-click `run_windows.bat`.

Open `http://localhost:8501` if Streamlit does not open it automatically.

## Ollama / local OpenAI-compatible LLM

For your current setup use:

```text
Base URL: http://localhost:11434/v1
Model: glm-5.3:cloud
Timeout: 300 seconds
```

The sidebar exposes all three settings, so no source edit is required. Other OpenAI-compatible endpoints such as LM Studio also work.

Environment variables are optional:

```text
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=glm-5.3:cloud
LOCAL_LLM_TIMEOUT=300
```

The local model receives deterministic scores plus data/evidence context. Its prose never directly changes hard regime math.

## Docker / Portainer

```bash
docker compose up -d --build
```

Open `http://<docker-host>:8501`. SQLite data persist in `./data`.

## Scheduled collection

```bash
python collector.py
```

The V3.0 collector evaluates all six risk regimes, machine triggers, guarded portfolio actions and alerts. A webhook can be configured with:

```text
DOLLAR_DASHBOARD_WEBHOOK=https://your-webhook-endpoint
```

## Portfolio guardrails

Defaults in `config/settings.json`:

- 1.0 percentage-point signal threshold.
- 2.0% minimum new position.
- $1,000 minimum actionable trade on the configured portfolio value.
- 25% maximum one-way turnover per run.
- Anti-chasing caps for recently surging hedges.
- Low data confidence reduces overlay aggressiveness.

A mathematical drift below the action floor is shown as **HOLD**, not as a fake $200–$300 trade.

## Tests

```bash
python test_engine.py
python test_v2.py
python test_v23.py
python test_v24.py
python test_v25.py
python test_v26.py
python test_v27.py
```

The V3.0 regression stack additionally covers TreasuryDirect buyback-result URL generation across daylight-saving/standard time, fallback result discovery, separation of median repo stress from repo-tail stress, honest offshore-dollar funding coverage, persisted primary-source verification checks and claim-relevance ranking. Earlier V2.2–V2.4 correctness tests remain in the package.

## Important limitations

- Auction absorption is now restored from official FiscalData, but **true auction tails** still require a dependable live when-issued yield source; bid-to-cover/bidder mix are not the same as a tail.
- FX option risk reversals, cross-currency basis and deep Treasury order-book data are still high-priority institutional-data additions.
- `check_source_url()` validates reachability and source class only; it does **not** prove a claim is true. High-impact facts must still be verified against the source before they are marked VERIFIED.
- TIC and COFER are lagged by design; V3.0 discounts that lag rather than pretending the data are current.
- Stress-test returns are explicit scenario assumptions, not forecasts.
- The app is research/decision support, not a fiduciary or autonomous trading system.

See `TODO_V2.md` for the ranked roadmap.
