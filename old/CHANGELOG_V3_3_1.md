# dollar_watch V3.3.1

- Added explicit `observed_position_unwind` state. Spot FX price action no longer permits factual wording that crowded shorts "are unwinding" unless newer CFTC report-over-report data confirms position shrinkage.
- `CONFIRMED` requires shrinkage in at least two crowded EUR/JPY/CHF leveraged shorts; one signal or DXY-long liquidation is `PARTIAL`; stale reports cannot confirm.
- Added deterministic anchor validation to exact canonical official statements. Reachability alone is insufficient.
- Added two-tier policy evidence: `DETERMINISTIC_VERIFIED` facts vs `HUMAN_APPROVED_INTERPRETATION`.
- Deterministic official facts can increase evidence coverage automatically and receive a 25%-scaled, tightly bounded mechanical score effect; human-approved interpretations retain the full bounded effect.
- Direct U.S.-intervention status, bilateral FX-policy facts, and structural-dollar-support facts now improve managed-devaluation evidence coverage without establishing broad-dollar motive. Deterministic context alone remains below the 50% broad-intent language gate.
- Deterministically validated canonical queue rows are `STRUCTURED_VERIFIED` and do not require redundant LLM claim verification.
- Policy/Evidence UI now separates deterministic verified facts from human-approved interpretive claims; Positioning UI shows observed CFTC unwind state.
- Updated LLM rules to require "consistent with short-covering" language unless `observed_position_unwind.status == CONFIRMED`.
- Version 3.3.1 / schema 3.3.1.
