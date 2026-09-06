# Dollar Crisis Early Warning Dashboard — Version 2

A local Python/Streamlit research application that monitors U.S. dollar regime risk and translates changing evidence into bounded, auditable portfolio actions.

## What changed in V2

V1 mainly combined market/FRED/Treasury-auction data with analyst overrides. V2 adds the leading information that was most likely to be missing before price confirmation:

- **CFTC Traders in Financial Futures positioning** for major FX contracts.
- **Treasury TIC country-level Treasury holdings** and foreign-official trends.
- **Stablecoin supply / USD1 monitoring** as a structural digital-dollar-demand signal.
- **10-year term premium**, curve, financial-conditions and Fed foreign swap signals.
- **Data freshness/confidence scoring** with automatic reduction of portfolio aggressiveness when data is missing/stale.
- **Early Warning vs Market Confirmation** as separate indexes.
- **Anti-chasing and max-turnover guardrails** on portfolio recommendations.
- **Scenario stress tests** comparing current and recommended allocations.
- **Evidence journal**, alerts, alert history and optional generic webhook delivery.
- A much larger, prioritized product backlog in `TODO_V2.md`.

## Core regimes

1. **Managed dollar devaluation** — policy intentionally pushes the dollar moderately lower.
2. **Fiscal / inflation crisis** — debt, long yields, term premium and inflation credibility become the dominant problem.
3. **Dollar funding squeeze** — global stress creates urgent demand for dollars even if long-run dollar confidence is deteriorating.
4. **Reserve-confidence crisis** — investors/official institutions reduce dollar/Treasury exposure and market prices confirm a loss of confidence.

The four scores are **risk indicators, not statistically calibrated probabilities**. V2 separately reports a data-confidence score so a 70/100 regime score based on weak data is not treated like a 70/100 score supported by all feeds.

## Public data sources used by V2

- Yahoo Finance via `yfinance`: DXY proxy, gold, Bitcoin, equities, Treasury/TIPS/commodity/CHF proxies and major FX crosses.
- FRED CSV: Treasury yields, TIPS, breakevens, term premium, financial conditions, SOFR, Fed balance sheet, reserves, TGA, central-bank swap usage and foreign-custody series.
- U.S. Treasury FiscalData: auction bid-to-cover and bidder mix.
- U.S. Treasury TIC Table 5: major foreign holders and foreign-official Treasury holdings.
- CFTC public Socrata dataset: Traders in Financial Futures positioning.
- DefiLlama public stablecoin endpoints: stablecoin supply, history and current peg information.
- Google News RSS: headline discovery/triage only.

## Windows setup

Python 3.11 or 3.12 is a conservative choice.

```powershell
cd dollar_crisis_dashboard_v2
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Or double-click:

```text
run_windows.bat
```

Open `http://localhost:8501` if Streamlit does not open it automatically.

## Docker / Portainer

```bash
docker compose up -d --build
```

Open `http://<docker-host>:8501`.

The SQLite database persists in `./data`.

## Scheduled collection

Run:

```bash
python collector.py
```

The collector saves a full V2 snapshot and alerts. On Windows, use Task Scheduler; examples are in `scripts/`.

### Generic webhook alerts

Set an environment variable:

```text
DOLLAR_DASHBOARD_WEBHOOK=https://your-webhook-endpoint
```

When meaningful alerts exist, `collector.py` will POST:

```json
{"alerts": [...]}
```

This is suitable for an n8n webhook, a local automation server, or another alert router.

## Local LM Studio

Set the base URL in the dashboard sidebar or define:

```text
LMSTUDIO_BASE_URL=http://192.168.1.204:1234/v1
LMSTUDIO_MODEL=<optional model id>
```

Use the actual OpenAI-compatible port configured by LM Studio. V2 sends the current evidence snapshot to the local model and asks for:

- What changed
- Causal interpretation
- Red-team/counter-thesis
- Missing factors
- Portfolio actions
- Reversal triggers

## Portfolio engine

The default baseline remains close to the portfolio discussed during development, with a new zero-weight broad-commodity bucket that V2 may add when inflation/fiscal regimes justify it.

The portfolio engine now applies four guardrails:

1. Regime scores below 35 do not create a crisis overlay.
2. Low source confidence reduces the size of the overlay.
3. A one-run turnover limit prevents large mechanical changes.
4. Large recent gains in common hedges can cap additional buys so the app does not blindly chase gold/Bitcoin/foreign assets after a sharp move.

Every non-HOLD trade includes a reversal trigger.

## Tests

Offline tests do not require live internet feeds:

```bash
python test_engine.py
python test_v2.py
```

The V2 test suite covers TIC parsing, CFTC positioning summaries, stablecoin summaries, scoring, portfolio constraints and scenario stress tests.

## Important limitations

- **True auction tails** require a reliable when-issued yield feed and are not yet included.
- **FX option risk reversals and cross-currency basis** generally require institutional or paid market data; they remain high-priority roadmap items.
- TIC data are monthly and lagged by design.
- CFTC positions are weekly and reported with a publication lag.
- Stablecoin reserve composition differs by issuer; V2 does not assume all stablecoin supply is invested in Treasury bills.
- Google News RSS is for discovery. Policy scores should be backed by primary documents or high-quality reporting before analyst overrides are changed.
- Stress-test returns are transparent scenario assumptions, not forecasts.
- The tool is research/decision support, not individualized fiduciary investment advice.

See **`TODO_V2.md`** for the full ranked roadmap.
