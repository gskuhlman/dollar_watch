# dollar_watch V3.4.8 — deterministic arithmetic and inference hardening

- Added deterministic long-end Treasury buyback `offer/accept` and `offer/parsed-capacity` ratios. The red-team model must use these supplied ratios and may no longer invent aggregate multiples from operation counts or mismatched scopes.
- Fixed the failure exposed by the Sep. 8 red-team run: $111.8B offered against $12B accepted/capacity is about 9.3x, not 6.1x.
- Added an FX-index attribution gate: a single cross move cannot be described as driving/concentrating a broad-dollar index without supplied contribution weights/decomposition.
- Added a percentile/valuation gate: historical percentiles describe levels, not automatic entry/valuation signals. High real yields can improve starting real income but do not by themselves make TIPS an attractive entry; duration/real-yield risk remains.
- No regime-score, trigger, Treasury-financing, or portfolio-allocation math changed.
