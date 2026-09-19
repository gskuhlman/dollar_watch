# V3.4.21 — Fixed-horizon UI clarity

- Fixed-horizon tables render unavailable/incomparable values as `N/A`, never Python `None`.
- Added deterministic `status_reason` for every horizon: missing snapshot window, schema mismatch, score-model mismatch, or successful comparable reference.
- Reference-date table now includes a Reason column and explicit N/A values for unavailable metadata.
- When no horizon is currently comparable, the Executive tab explains why 1D/7D are unavailable and reiterates that the engine will not substitute an unrelated older run.
- No horizon tolerances, scoring math, schema, triggers, or portfolio logic changed. Score model remains 3.4.3.
