# dollar_watch V3.4.4 — mixed-dtype financing-history chart fix

- Fixes `ValueError: Plotly Express cannot process wide-form data with columns of different type` in the Treasury Financing history chart.
- Historical holder-share columns are coerced to numeric only in a temporary chart copy; persisted history is not modified.
- All-null series are omitted from plotting.
- Financing history is melted to long form (`date`, `series`, `share_pct`) before Plotly rendering, making the chart robust across snapshots created by older app/schema versions and newly added holder categories.
- If no numeric financing observations are plottable, the dashboard shows an informational message instead of raising.
- Persisted schema remains 3.4.1.
