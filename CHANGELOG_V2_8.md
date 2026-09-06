# dollar_watch V2.8 changelog

V2.8 is a cleanup/freeze release. The six-regime scoring architecture is unchanged.

## Fixed
- TreasuryDirect buyback aggregate maximum amounts can now be recovered from nested XML values as well as flat tags.
- Buyback capacity/intensity remains `UNKNOWN` instead of becoming a false zero when maximum amounts cannot be established.
- Legacy persisted LLM verification checks are quarantined when the matching queue candidate fails the current semantic relevance gate.
- Stablecoin and other high-specificity policy buckets now require discriminating topic anchors; generic dollar-language cannot make an unrelated official page relevant.

## Added
- Indicative EUR/JPY/CHF front-futures-versus-spot dislocation proxy using free market data.
- Proxy output includes current de-trended dislocation, 1Y z-score and absolute percentile.
- Offshore funding coverage can rise modestly when the proxy is available, but true cross-currency basis remains explicitly unavailable.
- Quarantined legacy checks are exposed separately for audit and excluded from normal LLM verification context.
- `test_v28.py` regression coverage.

## Deliberate limitations
- The front-futures/spot proxy is not cross-currency basis and is not used as a covered-interest-parity measurement.
- No verification result automatically becomes hard-scoring VERIFIED analyst evidence.
- Core regime definitions and portfolio guardrails remain frozen pending live-history calibration.
