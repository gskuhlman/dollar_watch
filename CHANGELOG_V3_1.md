# dollar_watch V3.1 — Canonical Policy / FX Evidence Hotfix

V3.1 keeps the six-regime architecture frozen and fixes the final policy-evidence routing problem exposed by the V3.0 red-team run.

## Deterministic official-source feeds
- Added `dollar_dashboard/official_policy.py`.
- Directly ingests the latest monthly Japan Ministry of Finance FX-intervention release from the MOF intervention index and parses the reported yen amount.
- Directly ingests the New York Fed quarterly U.S. Treasury/Federal Reserve FX-operations finding.
- Seeds exact canonical sources for:
  - Treasury Bessent–Ueda yen-policy readout,
  - Japan-U.S. finance-ministerial yen-market readout,
  - Treasury GENIUS Act / dollar-reserve-role statement,
  - NY Fed Q2 2026 U.S. FX-intervention report.

Structured official statistics are treated as DATA-DERIVED primary facts. Nuanced policy interpretation still requires relevance + LLM support + human approval before hard scoring.

## Canonical-source routing
- Exact topic-matched official pages are attempted before generic official-site crawling.
- Added a separate `Bilateral FX policy` verification family so yen-policy coordination is not conflated with direct intervention or broad U.S. dollar-devaluation intent.
- Existing route/relevance gates remain active as fallbacks.

## Scoring semantics
- Recent Japan MOF intervention is a bounded FX-positioning-squeeze catalyst.
- A current NY Fed finding of no direct U.S. FX intervention is modest counterevidence only to the direct-intervention channel; it is not proof against broader weak-dollar intent.
- Human-approved evidence can now target managed devaluation, FX positioning, reserve confidence, funding stress, fiscal stress, or structural dollar support separately.
- Managed-devaluation critical coverage receives limited credit for deterministic U.S. direct-intervention reporting while preserving uncertainty about broader policy intent.

## Policy action taxonomy
Approved evidence carries an action class:
- `BROAD_USD_DEVALUATION`
- `BROAD_USD_SUPPORT`
- `BILATERAL_FX_POLICY`
- `BILATERAL_FX_INTERVENTION`
- `USD_FUNDING_STRESS`
- `RESERVE_CONFIDENCE_STRESS`
- `FISCAL_DEBT_MANAGEMENT`
- `STRUCTURAL_DOLLAR_SUPPORT`

The red-team prompt explicitly prohibits collapsing all policy/intervention evidence into an “add T-bills” response.

## Verification queue / storage
- Canonical exact-source rows persist their candidate URL, relevance, action class, and structured-fact status.
- Canonical rows already `CHECKED` are not reset to `SOURCE_FOUND` on subsequent collector runs.
- Structured MOF intervention facts are visible without requiring the LLM to rediscover the published amount.

## UI
- Added deterministic official-policy metrics and source table to the Policy / Evidence tab.
- Added a visible policy-action taxonomy audit.

## Tests
- Added `test_v31.py` covering:
  - Japanese intervention amount parsing,
  - exact canonical topic routing,
  - Japan intervention as an FX catalyst rather than broad devaluation evidence,
  - bilateral policy evidence targeting the FX regime rather than managed devaluation,
  - exact-source queue/action-class persistence,
  - prevention of repeated SOURCE_FOUND resets.
