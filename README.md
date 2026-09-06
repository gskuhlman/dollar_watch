# Dollar Crisis Early Warning Dashboard

A local Python/Streamlit application for monitoring four distinct U.S.-dollar risk regimes and translating them into an auditable portfolio recommendation.

## What it does

- Pulls market prices (DXY proxy, gold, Bitcoin, Treasuries, equities, EUR/USD, USD/JPY, USD/CHF, USD/CNY).
- Pulls public FRED data for Treasury yields, TIPS real yields, inflation breakevens, SOFR, Fed balance sheet, reverse repo, VIX, high-yield spreads, foreign-official Treasury holdings and weekly foreign custody changes.
- Pulls official Treasury FiscalData auction results and measures bid-to-cover / bidder-mix absorption stress for major coupon tenors.
- Discovers current policy/de-dollarization/funding/stablecoin headlines through Google News RSS.
- Tracks key policymakers and external actors.
- Lets the analyst explicitly score non-price facts such as FX intervention, Treasury auction stress, foreign official selling, BRICS payment progress, Fed-independence pressure, gold reserve rotation and structural stablecoin support.
- Produces four independent 0–100 risk scores:
  1. Managed dollar devaluation
  2. Fiscal / inflation crisis
  3. Dollar funding squeeze
  4. Reserve-confidence crisis
- Produces BUY / HOLD / REDUCE allocation changes in dollars.
- Saves snapshots to SQLite and charts score history.
- Optionally sends the current dashboard snapshot to a local OpenAI-compatible model (LM Studio, vLLM, etc.) for red-team analysis.

## Windows setup

Streamlit 1.63 supports Python 3.10–3.14. Python 3.11 or 3.12 is a conservative choice.

```powershell
cd dollar_crisis_dashboard
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Then open `http://localhost:8501` if it does not open automatically.

## Docker / Portainer

```bash
docker compose up -d --build
```

Open `http://<docker-host>:8501`.

The SQLite database is persisted in `./data`.

### Local LM Studio from Docker

Set `LMSTUDIO_BASE_URL` in `docker-compose.yml` or type the URL in the Streamlit sidebar. If LM Studio is on another LAN computer, use that computer's LAN IP and OpenAI-compatible API port, ending in `/v1`.

Example:

```text
http://192.168.1.204:1234/v1
```

(Use the actual port configured by LM Studio.)

## Workflow I recommend

1. Open the dashboard and refresh live data.
2. Review the headline monitor and primary reporting.
3. Update the analyst-input sliders only when evidence supports a change.
4. Review the four regime scores and active market drivers.
5. Review the Portfolio tab. Trades below the configured minimum threshold remain HOLD.
6. Run the local LLM red-team analysis if desired.
7. Save the snapshot so the next review measures *change*, not just level.

## Important limitations

- Headline keyword scoring is intentionally low-confidence. It is not sentiment analysis and not a substitute for reading source material.
- Yahoo Finance is convenient but not institutional market data.
- V1 automatically pulls Treasury auction absorption metrics and aggregate foreign-official/custody Treasury series, but it does not yet calculate when-issued auction tails, detailed country-level TIC flows, CFTC positions, FX option skew or cross-currency basis.
- Risk scores are transparent evidence-weighted indicators, not statistically calibrated probabilities.
- The portfolio model is a macro risk-allocation framework, not individualized fiduciary advice.
