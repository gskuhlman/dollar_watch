# dollar_watch V3.4.6 — intervention-asset inference hardening

- Tightens Japan MOF intervention semantics in the red-team prompt.
- Even if quarterly MOF detail later confirms yen-buying, the model may infer use/sale of foreign-currency reserves or cash to obtain yen, but may not infer U.S. Treasury sales, Treasury-collateral liquidation, or generic "USD asset disposal" unless the supplied verified evidence identifies the asset/instrument.
- No scoring, trigger, portfolio, Treasury-financing, CFTC-calendar, or funding-scope formulas changed.
- Application version advanced to 3.4.6; persisted schema remains unchanged.
