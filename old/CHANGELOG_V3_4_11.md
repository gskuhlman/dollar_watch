# dollar_watch V3.4.11 — evidence accounting + score-lineage hardening

V3.4.11 keeps the V3.4.10 scoring and navigation design while fixing issues exposed by the V3.4.10 red-team run.

## Changes

1. **Deterministic verification accounting**
   - Adds authoritative summaries for persisted source checks and verification-queue state.
   - The LLM is forbidden from recounting/truncating/merging these populations.
   - Prevents contradictory claims such as "all 18 inconclusive" alongside "16 total, one supported."

2. **Score-model lineage for fixed horizons**
   - Adds `SCORE_MODEL_VERSION`, currently `3.4.1`.
   - App versions can advance without breaking analytical comparability when score math is unchanged.
   - A future scoring-formula change can bump only this lineage; fixed-horizon comparisons across different score models return `INCOMPARABLE_SCORE_MODEL` instead of a misleading delta.
   - Historical V3.4.x snapshots with schema 3.4.1 are backward-compatible and treated as score model 3.4.1.

3. **Fed reserve-management neutrality**
   - `BILL_ACCUMULATION_WITH_MBS_RUNOFF` remains reserve-management/composition evidence.
   - It may not be relabeled as structural dollar support, QE, monetization, fiscal rescue, or devaluation without separate evidence.

4. **Inflation language guardrail**
   - Below-trigger readings may be described as not confirming debasement.
   - If percentiles are historically elevated, the LLM must preserve that context and avoid unqualified "contained/benign" wording.

No regime thresholds, portfolio allocation formulas, Treasury-financing math, or machine-trigger thresholds changed.
