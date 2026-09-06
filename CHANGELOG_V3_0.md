# dollar_watch V3.0 — Correctness / Feature-Freeze Release

V3.0 keeps the six-regime architecture intact and closes the remaining decision-engine correctness gaps identified in the V2.9 red-team review.

## Route-aware primary-source verification

- Official-source retrieval now applies bucket-specific path rules before semantic ranking.
- Treasury policy claims prefer press releases, statements/remarks, and financing-policy surfaces.
- White House claims prefer remarks, presidential actions, and briefing/statement surfaces.
- Privacy, generic assistance, help/contact, and other non-policy routes are rejected before LLM verification.
- Candidate rows expose `route_reason` so source-routing decisions are auditable.
- Standing probes were rewritten as narrow, falsifiable propositions rather than broad “X rather than Y” claims.

## Bidirectional policy evidence

- Verification-queue rows now carry `effect_target`, `effect_direction`, and `effect_weight`.
- Only rows that are source-relevant, LLM `SUPPORTED`, and explicitly human `APPROVED` are eligible for bounded hard-score effects.
- Approved pro-devaluation evidence can raise managed-devaluation policy intent.
- Approved strong/stable-dollar evidence can lower it.
- CONTRADICTED and INCONCLUSIVE checks remain audit evidence and are not automatically inverted into scoring signals.
- Approved primary-source policy evidence also raises managed-devaluation critical evidence coverage instead of leaving it at zero forever.

## Stateful funding-stress hysteresis

- `repo_or_swap_stress` remains the entry trigger: median SOFR-IORB >10bp, central-bank USD swaps >=$1B, or FIMA repo >=$1B.
- New `repo_stress_normalized` KILL can fire only after a prior funding-stress episode was active.
- Recovery requires SOFR-IORB <=3bp on at least three recent observations plus swaps and FIMA below $250M.
- Normal markets no longer produce a permanently-true “reduce liquidity” condition merely because SOFR-IORB is below the stress-entry threshold.

## Funding-squeeze portfolio direction

- A swap-line/FIMA draw is explicitly treated as dollar-liquidity stress, never as a reason to add non-USD exposure.
- A triggered funding-stress pre-commitment shifts toward T-bills and trims BTC plus unhedged ex-US equities, subject to normal trade-size and turnover guardrails.
- Scenario hedge alignment now separates direct hedges, conditional/unreliable hedges, USD-denominated rate-sensitive assets, and vulnerable assets.
- TIPS and U.S. equities are no longer credited as direct funding-squeeze hedges simply because they are denominated in dollars.

## Buyback capacity reconciliation

- `long_end_completed_capacity` remains the authoritative completed-operation capacity metric.
- Legacy `long_end_max_amount` now resolves to completed capacity when available, otherwise upcoming announced capacity.
- `long_end_max_amount_scope` states which population the value represents.
- `long_end_upcoming_max_amount` remains available separately.

## Regression coverage

`test_v30.py` adds checks for:

- route blocking/preference,
- narrow bidirectional standing policy probes,
- positive and negative approved policy-score effects,
- managed-devaluation critical coverage from approved evidence,
- stateful funding-stress recovery,
- buyback capacity reconciliation,
- funding-squeeze hedge classification,
- funding-stress trade direction, and
- the human approval gate for score-eligible verification evidence.
