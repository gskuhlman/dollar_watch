# dollar_watch V3.2 — Official-Source Resilience / Intervention-History Freeze Release

V3.2 does not add a regime or change the portfolio architecture. It hardens deterministic policy evidence and contextual funding validation.

## Japan MOF intervention ingestion
- Unicode NFKC normalization handles full-width digits, commas and spacing.
- `兆` / `億` combinations and single-`億` amounts parse deterministically.
- Reiwa date ranges are normalized to Gregorian dates.
- The canonical 2026-08-28 MOF release remains available as a dated last-known-official fallback if the live page/index is temporarily unavailable.

## Resilient canonical official fetches
- Retries transient 403/429/5xx failures with alternate user agents.
- Treasury readouts can be re-resolved through the canonical Readouts index.
- Successful live official text is cached under `data/official_policy_cache.json`.
- A small set of dated, paraphrased canonical seeds protects fixed historical evidence from transient 503 failures.
- Cache fallback is explicit in the UI and official-policy confidence is capped when no live official source is reachable.
- Verification `fetch_source_text()` can use the same exact-source cache rather than converting a temporary network failure into missing evidence.

## U.S. intervention history taxonomy
- Replaces a context-free yes/no history with quarter-level rows containing actor, currency, direction/purpose and broad-USD implication.
- Q4 2025 records Federal Reserve = no intervention, Treasury/ESF = intervention in Argentine pesos for Argentina stabilization; broad-USD implication is LOW.
- Q1 and Q2 2026 record no direct Federal Reserve/Treasury intervention.
- The latest-quarter finding remains usable as modest direct-intervention counterevidence without erasing prior targeted operations.

## Lagged NY Fed offshore-funding validation
- Adds optional PDF extraction (`pypdf`) of the Q2 2026 NY Fed FX quarterly report.
- Captures the official characterization that offshore dollar funding was stable and euro-dollar / dollar-yen three-month basis spreads were historically tight.
- Records quarter-end central-bank dollar-swap usage when parseable.
- This is explicitly lagged validation only: it does not raise live offshore coverage and cannot trigger `repo_or_swap_stress`.

## UI / LLM
- Policy tab now shows the U.S. intervention timeline and source fetch mode.
- Data Health shows the lagged NY Fed basis validation next to the live proxy.
- Red-team instructions require actor/currency/purpose interpretation and disclosure when a canonical source is served from last-known cache.

## Tests
`test_v32.py` covers Japanese-unit parsing, Reiwa dates, cache fallback, intervention-history context, and lagged NY Fed basis parsing.
