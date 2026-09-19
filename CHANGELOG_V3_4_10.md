# dollar_watch V3.4.10 — top navigation + causal-language hardening

V3.4.10 keeps the V3.4.9 fixed-horizon measurement design and makes four targeted improvements found in the first V3.4.9 red-team run.

## UI

- Moves the primary tab menu directly under the dashboard title/caption.
- Moves the six headline regime cards, fixed-horizon change table, coverage table, and executive results inside the Executive tab so no analytical result appears above navigation.
- Relabels adjacent-run change output as an operational audit rather than analytical change.

## Red-team / causal semantics

- **Japan intervention direction:** JPY-buying/FX-selling supports JPY and can squeeze short-JPY positioning; JPY-selling/FX-buying weakens JPY and benefits short-JPY positioning. The latter must never be described as “squeezing JPY shorts the other way.”
- **Z.1 holder-flow causality:** holder absorption shares are ex-post financing mix. They do not identify the marginal auction buyer, prove that issuance “cleared only with” a holder, or establish buyer dependency/fragility.
- **Treasury buyback vocabulary:** offered/accepted multiples measure seller offers into Treasury’s buyback capacity. They are not issuance subscription ratios or investor-demand measures and must not be called “well-subscribed.”
- **Human intent gate:** adds an explicit `broad_intent_human_gate_status` (`SATISFIED` / `UNSATISFIED`) so prose cannot call a required-but-empty human motive gate “open.”

No six-regime scoring formula, fixed-horizon comparison threshold, Treasury-financing arithmetic, trigger threshold, or portfolio-allocation rule changed.
