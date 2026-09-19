# V3.4.15

## Deterministic evidence deduplication

- Fixed a duplicate evidence-record path for the NY Fed Q2 2026 no-U.S.-FX-intervention fact. The canonical exact-statement validator and the richer structured NY Fed field both represented the same fact; scoring was not doubled, but the analyst-facing evidence list counted it twice.
- `deterministic_verified_evidence` now keeps the richer structured U.S. intervention row and omits the duplicate canonical representation.
- Added stable `fact_key` identifiers plus `deterministic_evidence_summary` (`total_unique_facts`, `action_class_counts`, duplicate-key audit).
- Local-LLM instructions now require the summary for deterministic fact counts and prohibit adding `official_policy_meta.canonical_statements` on top of the analyst-facing list.
- Policy/Evidence UI explicitly labels canonical statement rows as validator/audit inputs that may overlap structured facts.

No scoring, trigger, Treasury-financing, portfolio, schema, or score-model changes. `SCHEMA_VERSION=3.4.1`; `SCORE_MODEL_VERSION=3.4.1`.
