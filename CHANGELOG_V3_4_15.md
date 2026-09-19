# V3.4.15

## Liquidity-buffer and source-scope narrative hardening

- Added a liquidity-buffer prediction guardrail: low reserve percentiles, a rebuilding TGA and depleted ON RRP may indicate a thinner cushion / greater event sensitivity, but do not by themselves predict a repo event or constitute a "classic setup" for one.
- Repo/funding-event language now requires actual confirmation from repo/SOFR/tail/facility/basis evidence; otherwise use watch-condition / reduced-buffer language.
- Added a verified-source scope rule: country-specific official-sector gold evidence (for example PBoC/China buying) cannot be generalized into broad central-bank reserve rotation without broader verified evidence.
- Article existence/metadata verification cannot be promoted into verification of every causal or market claim in the article.
- Added a regime-direction language rule: FX-squeeze and funding-squeeze directions are typical tendencies/scenario pressures, not guaranteed USD moves.

No scoring, trigger, Treasury-financing, portfolio, schema, or score-model changes. `SCHEMA_VERSION=3.4.1`; `SCORE_MODEL_VERSION=3.4.1`.
