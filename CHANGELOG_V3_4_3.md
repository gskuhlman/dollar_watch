# dollar_watch V3.4.3 — release-aware financing calibration

- Replaces calendar-distance-only Z.1 staleness labels with release-aware timeliness. On 2026-09-07, 2026:Q1 is the latest expected official Z.1 release; Q2 is scheduled for 2026-09-11.
- Keeps the financing reading historical: latest official does not mean current-quarter.
- Adds `release_lag_quarters`, `expected_latest_quarter`, `next_expected_quarter`, and `next_release_date`.
- Adds `eslr_relevant_bank_proxy_absorption_pct` using U.S.-chartered depository Treasury absorption; broad monetary-capable absorption remains a separate monetary-transmission metric.
- Explicitly forbids attributing foreign banking office or credit-union Treasury absorption to eSLR.
- Separates CFTC Tuesday position-as-of dates from expected Friday public release dates.
- Escapes generated `$` currency markers before Streamlit Markdown rendering to prevent LaTeX corruption of red-team output.
- Neutralizes dealer language: dealer acquisition is intermediary inventory, not equivalent to end-buyer demand, but also not proof of weak demand or failed placement.
- Adds hedge-fund Treasury holdings, repo assets, and domestic-repo-liability structural proxies; the derived domestic-repo/Treasury ratio is explicitly not leverage or direct basis-trade exposure.
- Prepares for the new 2026:Q2 F3.2.t hedge-fund Treasury transaction row and attempts it only on/after the scheduled release; missing optional data never becomes a zero or lowers core holder coverage.
- Strengthens the critical-coverage language gate against categorical crisis-denial wording when key blind spots remain.
- App version 3.4.3; persisted schema remains 3.4.1 because these are backward-compatible metadata/interpretation changes and the six-regime taxonomy is unchanged.
