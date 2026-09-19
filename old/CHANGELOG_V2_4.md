# dollar_watch V2.4 changelog

## Correctness / evidence integrity
- TreasuryDirect buyback schedule and completed-result ingestion are separated; offers and accepted amounts are tracked when result XMLs are available.
- H.4.1 Treasury holdings are decomposed into bills, nominal notes/bonds and TIPS, with a data-derived purchase-composition classification.
- Auction trigger evidence now ages and expires; imminent replacement auctions downgrade old signals.
- Regime evidence coverage now reports generic, critical and effective coverage.
- Legacy snapshots are explicitly labeled rather than treated as current-schema predecessors.
- Verification queue rejects incomplete rows.
- LLM payload compaction preserves whole JSON records rather than string-slicing serialized evidence.

## Portfolio / interpretation
- Added scenario hedge-alignment table to replace single “percent defensive” framing.
- Red-team instructions explicitly distinguish Fed bill accumulation/MBS runoff from QE and distinguish aging event evidence from fresh triggers.

## Tests
- Added `test_v24.py` covering all V2.4 regression targets.
