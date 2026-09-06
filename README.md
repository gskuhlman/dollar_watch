# dollar_watch — Dollar Crisis Early Warning Dashboard V2.7

A local Python/Streamlit research application that monitors U.S. dollar regime risk and translates changing evidence into bounded, auditable portfolio actions.

## V2.7 evidence-integrity / distribution-context release

V2.7 keeps the six-regime architecture frozen and fixes the remaining reliability gaps surfaced by the V2.6 red-team run.

### New in V2.7

- **Buyback capacity recovery.** Completed TreasuryDirect result XML `max_amount` now survives the schedule/results merge. Additional maximum-par aliases are recognized. If maximum capacity still cannot be determined, policy-response intensity is explicitly `UNKNOWN` and receives zero scoring confidence — never a false numeric zero.
- **Semantic source relevance gate.** Official-source discovery now measures claim-token overlap plus topic-specific anchors. Candidates that fail are labeled `IRRELEVANT_SOURCE` and are rejected **before** Ollama claim verification. A reachable government URL is no longer enough to become an `INCONCLUSIVE` check.
- **Verification review dashboard.** Persistent queue rows expose candidate relevance score/status, LLM verdict, source URL and human approval state. Checks can be approved, rejected or disputed; approval still does not silently promote them into hard scoring.
- **Benchmark-auction lifecycle hardening.** Reopened coupon maturities such as 9Y11M are canonicalized back to the 10-Year benchmark, 29Y11M to 30-Year, etc. The upcoming-auction collector supplements Treasury FiscalData's convenience endpoint from the full auction table when benchmark tenors are missing. TIPS/FRNs remain distinct.
- **Generalized FRED historical context.** Sufficiently populated FRED indicators now receive 1-year and 3-year percentile/z-score context rather than only SOFR99. This gives term premium, reserves, TGA, custody, breakevens, real yields and other series a common distributional frame.
- **Longer FRED history window.** Default FRED collection begins in 2023 to improve percentile/z-score context while remaining lightweight.
- **Human source-check state persists.** SQLite schema migrations preserve candidate relevance and approval decisions across upgrades.

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

## V2.7 risk regimes

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

- Yahoo Finance via `yfinance`: DXY proxy, gold, Bitcoin, equities, Treasury/TIPS/commodity/CHF proxies and FX crosses.
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

The V2.7 collector evaluates all six risk regimes, machine triggers, guarded portfolio actions and alerts. A webhook can be configured with:

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

The V2.7 regression suite additionally covers TreasuryDirect buyback-result URL generation across daylight-saving/standard time, fallback result discovery, separation of median repo stress from repo-tail stress, honest offshore-dollar funding coverage, persisted primary-source verification checks and claim-relevance ranking. Earlier V2.2–V2.4 correctness tests remain in the package.

## Important limitations

- Auction absorption is now restored from official FiscalData, but **true auction tails** still require a dependable live when-issued yield source; bid-to-cover/bidder mix are not the same as a tail.
- FX option risk reversals, cross-currency basis and deep Treasury order-book data are still high-priority institutional-data additions.
- `check_source_url()` validates reachability and source class only; it does **not** prove a claim is true. High-impact facts must still be verified against the source before they are marked VERIFIED.
- TIC and COFER are lagged by design; V2.7 discounts that lag rather than pretending the data are current.
- Stress-test returns are explicit scenario assumptions, not forecasts.
- The app is research/decision support, not a fiduciary or autonomous trading system.

See `TODO_V2.md` for the ranked roadmap.
