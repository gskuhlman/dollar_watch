# dollar_watch — Dollar Crisis Early Warning Dashboard V2.1

A local Python/Streamlit research application that monitors U.S. dollar regime risk and translates changing evidence into bounded, auditable portfolio actions.

## Why V2.1 exists

The first V2 red-team run exposed exactly the weaknesses the app is supposed to find: a relative regime mix could be mistaken for a probability, stale TIC data could contribute too much, fiscal-duration stress was mixed together with inflation, a positioning unwind could masquerade as fundamental dollar weakness, a stablecoin warning was inconsistent with its displayed universe, and tiny mathematical portfolio changes were being presented as trades.

V2.1 changes the analytical foundation rather than merely adding charts.

## V2.1 risk regimes

Each is an independent **0–100 risk index, not a probability**:

1. **Managed dollar devaluation** — verified policy intent plus positioning/price confirmation.
2. **Fiscal / Treasury supply stress** — term premium, fiscal flows, auction absorption and duration/supply pressure.
3. **Inflation / monetary debasement** — inflation expectations, real-rate/inflation interaction and verified monetary/institutional evidence.
4. **Dollar funding squeeze** — repo/funding stress and forced global demand for dollars.
5. **Reserve-confidence crisis** — official/private dollar demand deterioration with market confirmation.
6. **FX positioning squeeze** — crowded EUR/JPY/CHF shorts unwinding into mechanical USD weakness without a fundamental confidence break.

The dashboard also reports **Early Warning**, **Market Confirmation**, **Data Confidence**, and a normalized **regime mix explicitly labeled NOT A PROBABILITY**.

## Major V2.1 changes

- **Freshness is applied before scoring.** TIC, COFER, CFTC, fiscal, auction and stablecoin inputs are confidence-discounted before they enter regime math.
- **COFER freshness uses the observation quarter**, not the time the API call happened.
- **Verified-evidence gate.** Analyst inputs affect hard scores only when marked VERIFIED and backed by a classified source URL. Unverified/headline/AI findings remain visible but cannot silently change the policy score.
- **Source provenance and tiers.** Primary sources, major news, research and other sources are labeled; URL reachability is explicitly not treated as factual verification. A claim-verification assistant can compare a claim against the cited page using the configured local LLM, but a human must still mark the evidence VERIFIED.
- **CFTC FX squeeze detector.** Crowded foreign-currency shorts are classified separately from fundamental USD-downside positioning.
- **Stablecoin peg bug fixed.** The alert and displayed maximum deviation use the exact same >$1B USD-stablecoin universe.
- **Actionable trade floor.** Default new-position minimum is 2% and default actionable trade minimum is $1,000; token trades are suppressed.
- **Machine-readable reversal/confirmation triggers.** 10Y/30Y auction pair rules, fiscal+inflation confirmation, foreign-demand breaks, DXY/CFTC confirmation, repo/swap stress, term-premium normalization and dollar-strength reversal.
- **Repo internals.** SOFR-IORB, SOFR99-IORB, TGCR-IORB and TGCR dispersion are derived from FRED series. FRED change windows are calendar-based so weekly H.4.1 data are not accidentally measured over 63 weeks when labeled “3m.”
- **Fiscal-flow module.** Monthly Treasury Statement receipts/outlays/deficit data are parsed into an auditable fiscal stress component.
- **IMF COFER module.** USD reserve-share data are used as a lagged confirmation source and discounted for age.
- **Fed H.4.1 decomposition.** Total assets, Treasury holdings, MBS, lending, central-bank swaps, identified assets and residual assets are shown separately so a WALCL change is not automatically called QE.
- **Portfolio stress tests now cover all six regimes.**
- **LLM prompt hardened.** New claims must be labeled unverified, conflicting evidence must be surfaced, source/staleness limits must be discussed, and the model is explicitly told that risk indexes are not probabilities.

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

The V2.1 collector evaluates all six risk regimes, machine triggers, guarded portfolio actions and alerts. A webhook can be configured with:

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
```

The V2.1 tests cover TIC parsing, CFTC positioning, FX squeeze detection, stablecoin peg-universe consistency, source-verification gates, freshness-before-scoring, fiscal-flow parsing, COFER period freshness, machine triggers, six-regime scoring, minimum trade/position constraints and six scenario stress tests.

## Important limitations

- True auction tails still require a dependable live when-issued yield source.
- FX option risk reversals, cross-currency basis and deep Treasury order-book data are still high-priority institutional-data additions.
- `check_source_url()` validates reachability and source class only; it does **not** prove a claim is true. High-impact facts must still be verified against the source before they are marked VERIFIED.
- TIC and COFER are lagged by design; V2.1 now discounts that lag rather than pretending the data are current.
- Stress-test returns are explicit scenario assumptions, not forecasts.
- The app is research/decision support, not a fiduciary or autonomous trading system.

See `TODO_V2.md` for the ranked roadmap.
