# dollar_watch V2.5 changelog

## Treasury buyback results
- Reworked completed TreasuryDirect buyback-result discovery so it does not depend on result links being present in dynamically rendered HTML.
- Derives official BBR result-XML filenames from operation dates/start times, including Eastern-to-UTC conversion, and uses a bounded recent-date fallback probe.
- Buyback schedule and completed-results health are independent. Missing completed results are unknown evidence, never zero activity.
- Tracks result URLs attempted, 404/not-found counts, completed operations, total par offered and total par accepted when available.

## Dollar-funding plumbing
- Median `SOFR-IORB` and upper-tail `SOFR99-IORB` are now distinct signals.
- Added repo-tail percentile, z-score and multi-observation persistence diagnostics plus a dedicated `repo_tail_stress` WATCH trigger.
- Global funding coverage now distinguishes fully observed domestic funding plumbing from missing/partial offshore FX-swap and cross-currency-basis visibility.

## Policy / evidence verification
- Added official-source-family adapters and same-domain claim-relevance ranking for queued policy claims.
- The app can fetch top primary-source candidates and ask the configured Ollama/OpenAI-compatible LLM to return SUPPORTED / CONTRADICTED / INCONCLUSIVE.
- Verification checks persist in SQLite with source URL/tier, verdict, explanation, model and provenance.
- LLM findings remain non-scoring until the user explicitly promotes evidence to VERIFIED.
- Added an unknown-is-not-absent language gate when critical evidence coverage is below 50%.

## Validation
- Retains all V2.2–V2.4 regression tests.
- Adds `test_v25.py` for buyback URL generation/discovery, repo-tail-vs-median separation, offshore funding coverage, verification persistence and primary-link relevance.
