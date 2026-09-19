# V3.4.13

## Verification accounting hardening
- Canonicalizes wrapped legacy verdict labels such as `VERDICT:_INCONCLUSIVE`, `RESULT: CONTRADICTED`, and similar wrappers before evidentiary counting.
- Keeps raw labels only as audit metadata; wrapped/typo variants can no longer appear as separate evidence categories.
- Adds deterministic count reconciliation fields for verdict, workflow-status, and relevance-gate populations.
- Complete-population summaries now expose whether each independent breakdown sums to the declared population total.
- LLM must list every nonzero category (or an explicit remainder) when presenting a complete-population breakdown.

## Funding-language hardening
- Swap-line and FIMA draws remain positive evidence of dollar-funding stress when present.
- Small/zero draws are not treated as necessary-condition failures for a funding squeeze.
- LLM must retain the possibility of private-market/offshore/eligibility/stigma/timing stress and pair facility observations with repo/SOFR/tail signals and the offshore basis gap.

## Compatibility
- Score model remains `3.4.1`.
- Database schema remains `3.4.1`.
- No regime, trigger, Treasury-financing, or portfolio formulas changed.
