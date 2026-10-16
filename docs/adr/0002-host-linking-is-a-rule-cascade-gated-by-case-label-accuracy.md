# Host linking is a rule cascade, gated by per-case accuracy on a frozen answer key

The #10 prototype linked 4,315 FY2024 Grants to Host institutions with named rules and no scores: 85.5% matched, 7.2% "no single Host", 6.1% review, 1.3% unmatched. About 99% of automatic decisions were right on a fresh 79-row hand check. The 54 unmatched Grants come mostly from Recipient-type errors and missing directories (CCD schools, regional agencies), not from name variation. A probabilistic model would not fix them, and a numeric score over hand-written rules would claim a precision we can't back. We therefore keep a **deterministic rule cascade** for v1, with no Splink and no numeric confidence. Signals rank as: Recipient UEI → IPEDS (same state), then the ED grantee-list name (joined by exact FAIN), then campus words and award-description phrases, with address only as a tiebreak. Campus text from the ED list or description overrides the UEI's unit only when it names a sibling campus of the Recipient and nothing contradicts it. ED text outranks the description. Any other conflict goes to review.

A case label is **auto-accepted** only if it scores at least 95% on the frozen answer key with at least 10 checks. A label below that is demoted to review. A label with fewer than 10 checks is reported as "unverified". The answer key is about 200 Grants, frozen once and never tuned against, stratified by case label, and oversampling weak cases (`nonprofit_no_site_named`, `system_campus_by_address`, `uei_only`) and including review and "no single Host" rows. About 40 are labelled a second time by another reviewer to estimate disagreement. A separate growing set is used for tuning. Human review decisions live in a versioned overrides file (FAIN → Host, reviewer, date, note) applied after the rules, so they survive reruns.

Policies:

- GEAR UP partnerships: the Host is a district, never the college partner. No district named gives "no single Host".
- IPEDS merges: use the unit as of the Grant's start year where IPEDS history allows. Fall back to the surviving unit, same state only, when the old unit has no current record.
- IPEDS sector 0 (system offices) never wins over a real campus. If it is the only candidate, the Grant goes to review.
- Nonprofits naming no site are "no single Host", reported as a lower-confidence class.
- Same state only, for every signal.
- No DUNS-derived value enters any table. Grants without a UEI are matched on name, ED list text and description only, labelled as such, and counted in the report.

## Consequences

- **No single Host**, **review** and **unmatched** are separate outcomes and all stay visible. The match-quality report shows them by count and by dollars, with accuracy per case label and its sample size, the review and unmatched lists by FAIN, the Recipients with no UEI link, and the UEI error exposure. It states the pull date and input hashes.
- Unreviewed queue items stay in the table as `review`. They are never silently accepted or dropped.
- Splink is revisited only if the review queue shows many name-variant failures.
- **ASSUMPTION:** the repo owner labels the answer key, and the founder or another reviewer labels the 40-row second pass. The prototype's accuracy came from one reviewer.

Decided in [Matching approach, answer key, and acceptance threshold](https://github.com/ikahrilas/topo/issues/11).
