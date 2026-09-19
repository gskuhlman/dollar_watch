# V3.4.22 — CFTC date semantics and lifecycle-language hardening

- Adds deterministic lint for CFTC date semantics: Tuesday position-as-of dates cannot be described as report/publication dates unless explicitly labeled as-of/position dates. The supplied expected Friday publication date must be used for release language.
- Adds deterministic lifecycle lint so `AGING`, `PENDING_REPLACEMENT`, or `EXPIRED` auction/event evidence cannot simultaneously be called `fresh`.
- Adds a tenor-specific auction prompt guard: 2Y/5Y/7Y weakness may affect broad auction stress but cannot confirm the `weak_10y_30y_pair` trigger or substitute for 10Y/30Y evidence.
- No scoring, schema, trigger thresholds, portfolio logic, or fixed-horizon tolerances changed. Score model remains 3.4.3.
