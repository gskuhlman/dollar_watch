# v3.4.24 — Conservative historical-score replay and visible horizon changes

- Score historical saved-input snapshots under current score model 3.4.3 when an older final score cannot be compared, instead of rejecting every prior model version.
- Freeze time-sensitive evidence-age and CFTC lifecycle calculations at each reference snapshot timestamp during replay; live scoring is unchanged.
- Require preserved market/FRED/auction/CFTC/TIC/COFER/fiscal/stablecoin/financing/policy inputs plus source confidence, original overrides, original human-approved evidence and historical news scores; do not substitute today's values or silently zero missing historical fields.
- Retain original historical score unmodified, expose original-versus-replayed model provenance, and flag every replayed delta as a retrospective/data-quality-affected estimate.
- Use another valid reference inside the SAME fixed-horizon tolerance if the nearest stored run cannot be replayed. Never expand 1D/7D/1M/3M/6M/1Y windows or synthesize missing dates.
- Show 1D/7D/1M point changes beside the six top regime cards (≈ denotes replay); retain exact age and method in the reference-details table.
- No score-model or schema upgrade; no database migration; persistent /data is never shipped in the update archive.
