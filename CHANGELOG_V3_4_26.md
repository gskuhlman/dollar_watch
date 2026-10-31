# v3.4.26 — Arrow-safe fixed-horizon tables

- Format `Actual age (days)` and `Target error (hours)` as consistent display strings rather than a mixture of numeric values and `N/A`. This prevents Streamlit/PyArrow `ArrowInvalid: Could not convert 'N/A' ... tried to convert to double` warnings in the reference-date expander.
- Format all six optional regime-horizon delta columns consistently, including mixed available/unavailable rows. Numerical scores and saved history are unchanged; only table cells are formatted for display.
- Preserve existing persistent `data/` runtime state. No score-model, analytical-schema, or database migration change: score model 3.4.3, schema 3.4.1, DB migration 2.
