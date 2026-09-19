# V3.4.20 — Mixed-instrument auction calendar lint + verified-fact coherence

## Fixed

- The post-generation Treasury calendar validator now checks **every tenor** when one calendar date is shared by several instruments in compact prose. This closes the hole that allowed text such as `2Y reopening + 5Y Sep 23` to validate only the 5Y leg even though Sep 23 is a **2-Year FRN reopening**, not a nominal 2-Year note auction.
- TIPS/FRNs are now treated at the **individual tenor** level during LLM linting. A line containing one explicit FRN/TIPS no longer bypasses validation for nominal tenors elsewhere in the same sentence.
- Added a mixed-instrument rule requiring `FRN`/`TIPS` to be stated explicitly. Bare phrases such as `2Y reopening` are treated as nominal coupon claims and must match `snapshot.upcoming_auctions`.
- Added a verified-fact coherence rule: month-specific quantities, streak lengths, rankings, and similar numerical attributes may not be stitched together from separate source-check records into a synthetic fact. This prevents a current August PBoC quantity from being paired with an older streak count.

## Lineage

- App version: **3.4.20**
- Schema version: **3.4.1**
- Score model: **3.4.3** (unchanged from V3.4.19; this release does not change risk math)
