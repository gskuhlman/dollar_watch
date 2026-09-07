# dollar_watch V3.4.1 — Treasury Financing Calibration

This patch tightens the V3.4 Treasury-financing layer after its first red-team run.

## Fixes
- Replaces obsolete nonfinancial-business FRED identifiers with live F3.2.t transaction series (`NCBTSAQ027S`, `NNBGSAQ027S`).
- Financing classification now uses M2/deposit growth aligned to the same Z.1 quarter rather than combining stale quarterly holder flows with newer monthly money data.
- Current M2/deposit growth remains visible as context, but cannot upgrade a stale quarter's classification.
- Financing states are marked provisional when holder data lag the current quarter by two or more quarters.
- Adds an explicit eSLR transmission-test status. Q1 2026 cannot isolate the April 1 full-effective-date effect, although early adoption was permitted January 1.
- Adds H.8 Treasury+agency change since April 1 as a high-frequency proxy only; agencies remain included and causality is not inferred.
- Replaces dealer "warehousing" wording with dealer net absorption/inventory unless stronger evidence exists.
- Prohibits "MMF out of bills" conclusions from the all-Treasury Z.1 holder-flow series.

The six crisis regimes are unchanged.
