# v3.4.26 — JPY intervention commentary follows the observed CFTC crowd

- Supply a deterministic `fx_intervention_positioning_context` companion to generic yen-buying/yen-selling mechanics. When the latest observed CFTC yen state is CROWDED_LONG, a hypothetical yen sale pressures crowded longs and yen buying supports them. A crowded-JPY-short squeeze is not the primary current positioning narrative unless newer CFTC data actually show crowded shorts.
- Apply the current-state rule to ALL LLM sections, including portfolio and reversal triggers; a state-aware deterministic lint requests a constrained repair for the previously observed wrong short-squeeze emphasis.
- Distinguish mechanical hypothetical effects from verified intervention direction and observed CFTC liquidation. Keep the original numeric regime scores, triggers, evidence confidence, historical replay and hard portfolio constraints unchanged.
- App version 3.4.26, analytical schema 3.4.1, score model 3.4.3, DB migration version 2. No runtime `data/` is packaged; existing `dashboard.sqlite` remains in place.
