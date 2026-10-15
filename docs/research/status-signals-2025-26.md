# Public signals that a TRIO or GEAR UP Grant was non-continued, denied, terminated or reinstated in 2025–26

Researched 2026-10-14. Organization-level only: Recipients are named, people are not. Terms follow the project vocabulary: **Grant** (one FAIN), **Recipient** (the UEI-holding organization), **Program**, **Continuation**, **Succession**, **Host institution**. (No `GLOSSARY.md` exists on `main` or `docs/research-and-assumptions` yet, so the terms are used as given in the research brief.)

**Sources and access.**
- **USAspending API.** `api.usaspending.gov`, no key. Pulled every ED-awarded transaction under 84.042, 84.044, 84.047, 84.066, 84.103, 84.217 and 84.334 for FY2024, FY2025 and FY2026 to date: 4,403 + 3,994 + 3,628 raw rows, 11,922 after de-duplication on (FAIN, mod, date, type, amount). Also pulled every award touched since FY2022 (7,161 FAINs), and called `/api/v2/transactions/` for the court-named FAINs. The latest action in the pull is **2026-09-16**.
- **CourtListener (RECAP).** Docket search plus free PDFs for *Council for Opportunity in Education v. U.S. Department of Education*, D.D.C. 1:25-cv-03491 (the "SSS case", non-selections) and 1:25-cv-03514 (the "TRIO case", non-continuations), consolidated on 2025-12-15. The docket metadata API needs a login, so the docket was read through the public search API. Several filings are not in RECAP (listed under Open questions).
- **Other sources:** federalregister.gov API, govinfo (P.L. 119-75), a senate.gov PDF, coenet.org, dol.gov.
- **Blocked:** `www.ed.gov` returned **403** again on 2026-10-14. Not retried or worked around.
- **Local copies.** Downloaded data is in `/tmp/status-signals-data/` and scripts are in `/tmp/ss_scripts/`, both outside the repo.

## Short answer

- **No public source flags a 2025–26 non-continuation, denial, termination or reinstatement per Grant directly.**
  - USAspending has no status field.
  - The transaction descriptions are static project titles. In FY2026, 0 of 3,472 awards had more than one distinct description, and none contains "terminat", "non-contin", "rescind" or "reinstat".
  - ED does not publish non-continuations in the Federal Register.
  - The court records name only a handful of Grants publicly. The rest are sealed.
- **The strongest per-Grant signal is a funding-sequence test on USAspending transactions, keyed on FAIN:**
  - **Non-continued:** a Grant whose cohort normally runs past its next budget-period start has **no positive obligation** in the window where that Continuation is normally recorded.
  - **Reinstated:** a **late positive obligation** after such a gap.
  - **Terminated after reinstatement:** a later **unpaired negative obligation equal to the full Continuation amount**.
- **Validation against the court-named Grants.** All 7 non-continued Grants named in the public court record fit the pattern, and so do the 4 named SSS non-selections (table in §2).
- **Main caveats:**
  1. **It cannot tell why funding stopped.** Policy non-continuations look the same as routine non-continuations for performance, relinquishments, closures and Successions. The 2024 baseline already had 95 "no funding" cases, against 155 in 2025.
  2. **Lag.** ED's FABS reporting lag is up to about 60 days, and ED records Continuations anywhere from May to late September. A missing Continuation is safe to read only about 90 days after the budget period starts.
  3. **Encoding quirks.** Continuations are sometimes coded `EX` rather than `B1`. Many negatives are routine closeout (`FX`) or same-day reversal pairs.
  4. **Award-level dates.** The award "End Date" can freeze at the last funded budget period, so it is not a separate termination flag (§1d).
  5. **DOL.** If DOL becomes the awarding agency, the test must follow it. DOL has administered ED HEA programs since Nov. 18, 2025, but every FY2026 TRIO/GEAR UP row is still ED-awarded.
- **Court records** are authoritative but cover only COE's identified members. Most identities, UEIs and PR/Award numbers are sealed.
- **COE's member list is not public.**
- **ED and DOL notices** of non-continuation go to Recipients and, under P.L. 119-75 §524, to the Appropriations Committees. They are not published.

## 1. Signal-by-signal assessment

| # | Signal | What it can show | Coverage | Lag | False-positive risk | Grant (FAIN) or Recipient? |
|---|---|---|---|---|---|---|
| 1 | **Missing expected Continuation** (USAspending transactions) | Non-continued, or otherwise unfunded, for a budget year | All ED-reported TRIO/GEAR UP Grants. 2,469 Grants were mid-project at the 2025 anniversary | ≈ 60–90 days after the budget-period start (FABS lag up to 60 days; ED posts Continuations May–Sept) | **High as a "why" signal:** 2024 baseline 95 of 3,570 vs 2025: 155 of 2,469. Also late reporting (§1b) | **Grant** (FAIN) |
| 2 | **Gap, then late positive obligation** (`B1`, `EX` or `A1`) | Reinstatement after the court order (non-continuation or non-selection reversed) | Same | Reinstatements posted 2026-03-13, 2026-05-26 and 2026-06-18/24, i.e. 2–5 months after the Jan. 16 and Apr. 13, 2026 orders | Moderate: late but routine Continuations look the same. 2024 had 11 such gaps, 2025 had 29 | **Grant** |
| 3 | **Unpaired negative obligation equal to a full prior Continuation** | Termination or reversal of an award already obligated | Same | Augsburg McNair: May 19 termination → `EX −272,360` on 2026-09-14 (≈ 4 months) | **High.** 916 negative transactions since 2025-07-01; 836 are partial `FX` closeouts; 53 full-amount `FX` reversals are mostly SSS 2020-cohort closeout, including 32 of exactly −$1 on 2026-08-11; 8 are same-day ± pairs (accounting); 4 match a same-day `A1` on another FAIN (Succession) | **Grant** |
| 4 | **Award End Date earlier than the cohort's usual end date** | Usually just "no funding since the last budget period" | Same | — | Not independent. Example: P334S230008's end date of 2025-09-30 was last modified on **2024-07-31**, before any 2025 action | **Grant** |
| 5 | **Transaction / modification descriptions** | Nothing | — | — | — | — |
| 6 | **Court records**, COE v. ED | Non-selection, non-continuation, vacatur, re-termination, reconsideration outcome | Only COE members COE chose to identify. **Names are public for the original 6 TRIO-case Recipients (7 Grants) and 3 SSS-case Recipients (4 applications); 46 later members are sealed**, including UEIs and PR/Award numbers | Days to weeks after events, but key exhibits (status reports, ED's Aug. 3 spreadsheet) are not in free RECAP | Low for what is named | **Grant**, where a PR/Award number is printed; otherwise Recipient or nothing |
| 7 | **COE member lists** | Membership only, not status | Not public. coenet.org's membership page has only a login and a staff directory. Additional members' identities are sealed by the court | — | — | Neither |
| 8 | **ED / DOL notices** | The actual decision | Sent to the Recipient. Also sent to the House and Senate Appropriations Committees under P.L. 119-75 Div. B §524. **Not published.** Federal Register search for "non-continuation" since 2025-01-01: 0 results | — | — | **Grant** in the letters; not public |
| 9 | **Congressional letters, press, Recipient statements** | Single cases | Ad hoc | Days | Low per case, but secondary to the decision itself | Sometimes Grant (the NH letter cites P334S230008) |

### 1a. Signal 1: missing expected Continuation

**Method** (`/tmp/ss_scripts/final.py`):
1. For each FAIN, group by the first 7 characters (program, suffix and cohort year, e.g. `P044A21`) and take the cohort's modal award end month as the normal project end.
2. A Grant "expects" a Continuation in year Y if all of these hold:
   - it started before Y;
   - its base obligation was before Y;
   - its cohort normally ends more than 60 days after the Grant's Y anniversary.
3. Check for any positive obligation over $1 in calendar Y. **Count `EX` and `FX` as well as `B1`.** Example: the TS FY2021 cohort's final-year Continuations were recorded as `EX`, positive, on 2025-09-18 (e.g. `P044A210026`).

**Results:**

| Year Y | Grants expecting a Continuation | Funded in Y | Gap, then later funding | No funding since |
|---|---|---|---|---|
| 2024 (baseline) | 3,570 | 3,464 | 11 | 95 (51 of them SSS FY2020 cohort, final year) |
| 2025 | 2,469 | 2,285 | **29** | **155** |

- **2025 "no funding since" by Program:** TS 50, UB 40, EOC 24, McNair 12, UBMS 8, VUB 6, GEAR UP Partnership 6, GEAR UP State 5, TRIO Training 4.
- **2025 "gap, then later funding":** McNair 10, TS 6, UB 5, EOC 3, SSS 2, VUB 2, UBMS 1.
- **Cross-check (consistency only, not proof).** ED's own filing says it "issued 2,251 continuation awards cumulatively across the Federal TRIO programs" in FY2025 [C3, p. 5].
- **Comparison with the 2024 baseline:**
  - The 2025 universe has no SSS, because SSS started a new cohort.
  - Non-SSS "no funding" cases rose from 44 in 2024 to 155 in 2025.
  - So roughly 110 Grants are excess over the baseline. **That excess is my arithmetic. It does not count policy non-continuations.**
- **TS/EOC FY2021 cohort.** 45 TS and 21 EOC Grants got no final-year (2025–26) funding.
  - COE says only 6 of the 22 programs still terminated in Aug. 2026 were TS/EOC in their final year [C8, p. 3].
  - So most of these 66 are not identified in any public record as policy actions. Their cause is UNVERIFIED.
- **Lag check for 2026–27.** As of the 2026-09-16 data, 214 of 2,620 Grants expecting a 2026–27 Continuation had none. 185 of those had Sept. 1 anniversaries, and they cluster by state and system (Louisiana, Alabama, Oklahoma, New Mexico, NY research foundations). That pattern points to batch reporting lag, not policy.
  - **Do not read 2026–27 gaps before about December 2026.**
  - The documented FABS rule is 2 weeks; ED's observed lag is median 19 and max 60 days (`docs/research/usaspending-trio-gearup.md` §5).

### 1b. Signal 2: reinstatement shows up as a late positive obligation

| Date | What posted | Interpretation | Basis |
|---|---|---|---|
| **2026-03-13** | `B1` on 6 of the 7 court-named non-continued Grants (P217A220172, P047V230016, P217A220356, P066A210058, P217A220339, P044A210139) | Reinstatement of the original identified members. COE says "the Department made continuation determinations in March" [C8, p. 2–3] | Verified by FAIN (§2) |
| **2026-05-26** | 17 SSS `A1` actions on `P042A25…` FAINs, plus 7 McNair `B1` actions on Grants with no 2025 funding (e.g. P217A220027, P217A220060) | Probably reconsidered non-selections and non-continuations for the 46 additional members added on Apr. 13, 2026 | **UNVERIFIED inference.** Those members' identities are sealed [C5, p. 10–11] |
| **2026-06-18 / 06-24** | SSS `A1` on P042A251037, P042A251043, P042A250499 and P042A251278 | Reversal of the court-named FY2025 SSS non-selections | Verified by FAIN (§2) |
| 2026-07 to 2026-08 | Late `B1` on further Grants with no 2025 funding (e.g. P047A220031, P047A220572, P044A210211) | Possibly the 6 reconsiderations ED approved on Aug. 3 [C8, p. 3], possibly routine late Continuations | UNVERIFIED |

### 1c. Signal 3: negative obligations

- **Mostly noise.** Since 2025-07-01 there were 916 negative transactions:
  - 836 unpaired partial `FX` (closeout or residual deobligation)
  - 53 unpaired full-amount `FX`, overwhelmingly SSS FY2020-cohort closeout, including 32 of exactly −$1.00 on 2026-08-11
  - 13 unpaired full-amount `EX`
  - 8 same-day ± pairs
  - 6 unpaired partial `EX`
- **Policy-relevant negatives are a small subset.** Unpaired `EX` equal to a full prior Continuation or `A1`, e.g.:
  - `P217A220172` (Augsburg McNair): reinstated `+272,360` on 2026-03-13, then `−272,360` on 2026-09-14. This is consistent with the May 19, 2026 terminations. That Augsburg was among the 28 is UNVERIFIED; the list is sealed.
  - `P044A220683` (Ivy Tech TS): `B1 +336,357` on 2025-09-17, then `EX −336,357` on 2025-09-29, in the same week as ED's Sept. 12–16 non-continuation notices [C3, p. 5]. Cause UNVERIFIED.
  - `P042A251037` (Big Bend SSS): reinstated by `A1` on 2026-06-18, then `EX −335,053` on 2026-08-14. Big Bend's other application, P042A251043, was funded again on 2026-09-01. Cause UNVERIFIED.
  - Four FY2025 SSS `A1`s fully reversed on 2025-07-28: P042A251153, P042A251819, P042A251672, P042A250188. ED says it corrected "administrative errors on the first SSS slate" [C2, p. 3–4], so these may be corrections rather than denials. UNVERIFIED.
- **Succession false positives.** These negatives match a same-day `A1` of the same amount on a new FAIN held by a different Recipient. Treat this as a Succession, not a termination:

| Old FAIN (Recipient) | Date | Amount | New FAIN (Recipient) |
|---|---|---|---|
| P047A221031 (Impact Educational and Housing Development) | 2025-12-22 | −513,114 | P047A250002 (Impact Prosperity Partners) |
| P217A220158 (Siena Heights University) | 2026-06-15 | −92,117.37 | P217A250002 (Adrian College) |
| P042A250822 (Siena Heights University) | 2026-07-06 | −202,423.49 | P042A251923 (Defiance College) |
| P042A250292 (Purdue University Global) | 2026-06-24 | −272,364 | P042A251922 (Purdue University) |

### 1d. Award End Date is not a separate signal

- **The NH GEAR UP Grant.** P334S230008 (Education Alliance for New Hampshire) was terminated by ED notice of Sept. 12, 2025, effective by Sept. 30 [N1]. USAspending shows:
  - project period 2023-10-01 → **2025-09-30**
  - last transaction `B1` on 2024-06-25
  - **Last Modified 2024-07-31**
- So the 2025-09-30 end date was on the record before the termination. On these awards, the award-level end date equals the end of the latest funded budget period.
- **The same pattern** (end date equal to the 2024–25 budget-period end, last modified mid-2024) appears on many 2025 "no funding" Grants, e.g. P044A210083, P066A210008 and P217A220017.
- **It is inconsistent across awards.** The reinstated court-named Grants show full project end dates; P217A220356 runs to 2026-09-30, last modified 2026-03-31.
- **Use it only to widen the candidate set.** Check the transaction sequence rather than trusting End Date.
- Whether ED overwrites the end date on non-continuation is UNVERIFIED. The transaction-level `period_of_performance_*` columns in the ED Award Data Archive could settle it; not checked here.

## 2. Validation: the Grants named in public court filings

These are the Grants named in ED's own filings. Source: ED's motion in the TRIO case [C3, pp. 4–6] and ED's opposition in the SSS case [C2, pp. 3–4]. The USAspending sequences were pulled on 2026-10-14 via `POST /api/v2/transactions/`.

| FAIN | Recipient / Program | Court-record status | USAspending sequence (2024 on) | Signal 1 | Signal 2 | Signal 3 |
|---|---|---|---|---|---|---|
| P217A220172 | Augsburg Univ. / McNair | Non-continued effective 2025-09-30 | B1 2024-07-12; **none in 2025**; B1 2026-03-13 +272,360; **EX 2026-09-14 −272,360** | yes | yes | yes |
| P047V230016 | Suffolk Univ. / VUB | same | B1 2024-07-05; none in 2025; B1 2026-03-13; B1 2026-08-30 | yes | yes | no |
| P047A220168 | SUNY Plattsburgh (Research Foundation) / UB | same | B1 2024-05-14; none in 2025; B1 2026-06-18; B1 2026-07-29 (two years caught up) | yes | yes | no |
| P217A220356 | Marquette Univ. / McNair | same | B1 2024-07-11; none in 2025; B1 2026-03-13 | yes | yes | no |
| P066A210058 | South Seattle College / EOC | same | B1 2024-07-30; none in 2025; B1 2026-03-13 | yes | yes | no |
| P217A220339 | Univ. System of New Hampshire / McNair | same | B1 2024-07-12; none in 2025; B1 2026-03-13 | yes | yes | no |
| P044A210139 | Univ. System of New Hampshire / TS | same | B1 2024-08-05; none in 2025; B1 2026-03-13 | yes | yes | no |
| P042A251037 | Big Bend CC / SSS application | Not selected, July 2025 | A1 2026-06-18 +335,053; EX 2026-08-14 −335,053 | n/a | yes | yes |
| P042A251043 | Big Bend CC / SSS application | Not selected | A1 2026-06-18; B1 2026-09-01 | n/a | yes | no |
| P042A250499 | Green River College / SSS application | Not selected | A1 2026-06-18; B1 2026-08-31 | n/a | yes | no |
| P042A251278 | Southern Illinois Univ. / SSS application | Not selected | A1 2026-06-24; B1 2026-08-31 | n/a | yes | no |

**Notes on the table:**
- **Non-selected SSS applications have FAINs before any money moves.** The PR/Award numbers in ED's filing became USAspending FAINs only when the reversal was funded. A **non-selection is invisible in USAspending until it is reversed**, so Signal 1 cannot detect denials of new applications.
- **The negative column is not a reliable non-continuation flag.** None of the 7 non-continued Grants shows any negative obligation at the 2025 non-continuation itself. ED simply did not obligate the next budget period. The one negative (Augsburg) belongs to the 2026 termination.

## 3. 2025–26 events visible in court records

All are from D.D.C. 1:25-cv-03491 / 1:25-cv-03514 (consolidated). The court records describe ED decisions; they are not ED publications.

1. **SSS FY2025 competition** [C2, pp. 3–4]:
   - 1,702 applications.
   - 962 new awards "on or about July 4, 2025", plus 151 more from second review and error corrections.
   - At the same time, 25 applicants were "not selected for funding based on the Department's review for potential conflicts with applicable nondiscrimination requirements."
2. **Summer 2025 non-continuations** [C3, p. 5; C6 ¶¶140–142]:
   - The named members' notices were transmitted Sept. 12–16, 2025, effective Sept. 30, 2025.
   - COE says other notices were effective May 30, Aug. 31 or Sept. 30, 2025, depending on the Grant type.
   - The total count of non-continued Grants is not stated in any public filing read here.
3. **Jan. 16, 2026 preliminary injunction** [C1]:
   - Vacated the non-continuation notices "sent to Plaintiff and the members it identified" (TRIO case) and the non-selection notices "sent to Plaintiff's identified members" (SSS case).
   - Ordered ED to reconsider and "issue new determinations".
   - Let COE add members by Feb. 1, 2026, identified "by their Unique Entity Identifier numbers" (fn. 2), i.e. at **Recipient** level.
   - The order covers **identified members only, not all COE members.**
4. **Apr. 13, 2026 modification** [C5, p. 5]:
   - Extended relief to **46 additional members** who filed declarations.
   - On May 27, 2026 the court denied relief for 33 further unnamed members.
   - The 46 members' names, UEIs and "PR/Award numbers" are **sealed** [C5, pp. 10–11].
5. **May 19, 2026 terminations** [C8, pp. 1–4]:
   - ED issued "notices of termination to 28 TRIO programs" under 2 C.F.R. §200.340(a)(4).
   - 25 of the 28 requested reconsideration.
   - On Aug. 3, 2026 ED denied 19 and approved 6.
   - COE says **22** programs remain terminated: 6 are TS/EOC in a final year ending Aug. 31, 2026, and 13 are in year 4 (COE's figures).
   - ED's Aug. 3 spreadsheet (ECF 65-1) is not in free RECAP.
6. **Settlement, Sept. 30, 2026** [C9]:
   - The parties signed a settlement agreement.
   - ED is to file a stipulation of dismissal within 65 days, "following Defendants' compliance with certain terms".
   - **The terms are not on the public docket.**
   - ED also filed a "Notice Regarding Fiscal Year 2026 Appropriations" on Sept. 28, 2026 (ECF 72). It is not in RECAP; contents UNVERIFIED.

**A second public channel, unpublished.** P.L. 119-75, Div. B, §524 requires ED, DOL and HHS to notify the House and Senate Appropriations Committees "not less than 3 full business days prior to announcing or providing notice of … (1) any new or non-competing continuation grant … and (2) the termination or non-continuation of any grant, including a short description of the reason" [L1]. ED cited this "recent reporting requirement" in the litigation [C5, p. 12]. It would be the most complete per-Grant record, but **it is not published**. Whether the committees release it is UNVERIFIED.

**GEAR UP.** No GEAR UP litigation was found on CourtListener. The one public per-Grant GEAR UP case found is the NH delegation letter: P334S230008, notified Sept. 12, 2025 of termination by Sept. 30 [N1]. USAspending agrees: no 2025 funding. The 2025 Signal-1 set has 11 GEAR UP Grants with no 2025 funding. Their causes are UNVERIFIED, and some are cohort-end artifacts; for example P334A210147, P334A210174 and P334S210008 had already-shortened end dates.

## 4. Recommended per-Grant reading rule

For each FAIN in a cohort that should still be running:
1. **Status = "continued"** if there is a positive obligation (`B1`, `EX` or `FX`) dated within about 4 months before to 1 month after the budget-period anniversary.
2. **Status = "unfunded (cause unknown)"** if there is none by about 90 days after the anniversary. Label it "non-continued" only with a corroborating source: a court record, a congressional letter, or a Recipient statement.
3. **Status = "funded late / possible reinstatement"** for a positive obligation after such a gap. Two obligations close together (e.g. P047A220168) mean the skipped year was back-funded.
4. **Status = "terminated / reversed"** for an unpaired `EX` (or `FX`) negative equal to a full prior obligation. First exclude two cases:
   - same-day ± pairs;
   - a same-day `A1` of the same amount on another FAIN (Succession: link the two FAINs, not a termination).
5. **Never use** award End Date, transaction descriptions, or partial `FX` negatives as status signals.
6. **Filter on listing number, not awarding agency.** Re-check DOL (toptier 1601) as an awarding agency; see `docs/research/apr-data-and-fy2026-awards.md` §2c.

**Signal limits to keep in mind:**
- **Non-selections of new applications** (SSS FY2025, and FY2026 TS/EOC if any) never appear in USAspending unless reversed. FY2026 TS/EOC new awards are not in USAspending at all yet.
- **Recipient vs. Grant.** Court remedies are framed per member (UEI), but one Recipient can hold several Grants (e.g. UNH: TS and McNair). Keep status at the FAIN level.

## Open questions / UNVERIFIED

- **The total number** of 2025 TRIO/GEAR UP non-continuations and the full list of affected FAINs. Not public: sealed exhibits, plus §524 notices to Congress.
- **Filings not in free RECAP:** ED's Jan. 30, Mar. 9 and May 21, 2026 status reports (ECF 31, 37, 42) and ECF 65-1 (the Aug. 3 reconsideration spreadsheet) may contain per-Grant outcomes. Getting them requires PACER purchase, not attempted.
- **Settlement terms** (ECF 74) and whether they reinstate any of the 22 programs. Not public as of 2026-10-14.
- **Whether the 2026-05-26 SSS `A1` and McNair `B1` batch** is the 46 additional members. This is inference only.
- **Causes of the 2025 TS/EOC final-year gaps** (66 Grants) and the other Signal-1 Grants. Possibilities include performance-based non-continuation, relinquishment, the policy non-continuations, and reporting gaps.
- **The Ivy Tech TS, Big Bend SSS and four July-2025 SSS reversals:** cause unknown.
- **Whether ED changes `period_of_performance_current_end_date`** when it non-continues. The transaction-level archive columns would show it; not checked.
- **ED and DOL web pages** (ed.gov returned 403). DOL's "Grants Awarded" page loaded but lists no TRIO/GEAR UP awards. Whether DOL will report FY2026 TS/EOC awards, and under which agency, is still open.
- **COE member directory:** none found publicly. Whether one exists behind COE's member login is unknown and out of scope.

## Sources

- [C1] Order granting preliminary injunction, ECF 29, 1:25-cv-03491 (Jan. 16, 2026): https://storage.courtlistener.com/recap/gov.uscourts.dcd.285441/gov.uscourts.dcd.285441.29.0.pdf. Memorandum opinion, ECF 28: https://storage.courtlistener.com/recap/gov.uscourts.dcd.285441/gov.uscourts.dcd.285441.28.0.pdf
- [C2] Defendants' response to the PI motion, SSS case, ECF 16 (Nov. 10, 2025), pp. 3–4: https://storage.courtlistener.com/recap/gov.uscourts.dcd.285441/gov.uscourts.dcd.285441.16.0.pdf
- [C3] Defendants' motion to dismiss / PI opposition, TRIO case, 1:25-cv-03514 ECF 14 (Nov. 10, 2025), internal pp. 4–6 (FAINs, 2,251 continuations, Sept. 12–16 notices): https://storage.courtlistener.com/recap/gov.uscourts.dcd.285494/gov.uscourts.dcd.285494.14.0.pdf
- [C4] Docket entries for both cases, read via the CourtListener search API (`type=rd`, `docket_id` 71495173 and 71506962), 2026-10-14. Includes the minute orders of Apr. 7, June 16, July 14, Aug. 21 and Sept. 22, 2026 and the ECF 33/41/46/47/53/65/72 descriptions.
- [C5] Memorandum opinion on the motion to dismiss, the seal motion and the motion to modify, ECF 43 (May 27, 2026), pp. 4–5, 10–12: https://storage.courtlistener.com/recap/gov.uscourts.dcd.285441/gov.uscourts.dcd.285441.43.0.pdf. Order, ECF 44: https://storage.courtlistener.com/recap/gov.uscourts.dcd.285441/gov.uscourts.dcd.285441.44.0.pdf
- [C6] Complaint, TRIO case, 1:25-cv-03514 ECF 1, ¶¶140–142: https://storage.courtlistener.com/recap/gov.uscourts.dcd.285494/gov.uscourts.dcd.285494.1.0.pdf. PI motion, ECF 2: https://storage.courtlistener.com/recap/gov.uscourts.dcd.285494/gov.uscourts.dcd.285494.2.0.pdf
- [C7] Joint status report, ECF 67 (Aug. 14, 2026) (May 19 terminations, Aug. 3 reconsiderations): https://storage.courtlistener.com/recap/gov.uscourts.dcd.285441/gov.uscourts.dcd.285441.67.0.pdf
- [C8] COE's renewed motion to enforce, ECF 68 (Aug. 17, 2026), pp. 1–4 (28 terminated, 25 sought reconsideration, 19 denied, 6 approved, 22 remaining): https://storage.courtlistener.com/recap/gov.uscourts.dcd.285441/gov.uscourts.dcd.285441.68.0.pdf
- [C9] Notice of settlement, ECF 74 (Sept. 30, 2026): https://storage.courtlistener.com/recap/gov.uscourts.dcd.285441/gov.uscourts.dcd.285441.74.0.pdf. Joint status report, ECF 71: https://storage.courtlistener.com/recap/gov.uscourts.dcd.285441/gov.uscourts.dcd.285441.71.0.pdf
- [L1] Consolidated Appropriations Act, 2026, P.L. 119-75, Div. B, §524 (140 Stat. 321): https://www.govinfo.gov/content/pkg/PLAW-119publ75/html/PLAW-119publ75.htm
- [N1] New Hampshire congressional delegation letter to the Secretary of Education, Sept. 19, 2025 (P334S230008): https://www.shaheen.senate.gov/download/nh-gear-up-letter?download=1
- [U1] USAspending API, 2026-10-14:
  - `POST /api/v2/search/spending_by_transaction/` and `POST /api/v2/search/spending_by_award/`. Filters: the 7 listings above; awarding toptier = Department of Education; award types 02–05; FY windows 2023-10-01→2024-09-30, 2024-10-01→2025-09-30 and 2025-10-01→2026-10-14 (transactions), plus 2021-10-01→2024-09-30 and 2023-10-01→2026-10-14 (awards).
  - `POST /api/v2/transactions/` and `GET /api/v2/awards/ASST_NON_<FAIN>_091/` for the FAINs in §2 and P334S230008.
  - Scripts: `/tmp/ss_scripts/pull.py`, `final.py`, `analyze2.py`, `tx.py`.
- [F1] Federal Register API, `conditions[term]="non-continuation"`, published ≥ 2025-01-01: 0 results. `conditions[term]=TRIO`, ≥ 2025-06-01: 13 results, none a non-continuation or award notice. https://www.federalregister.gov/api/v1/documents.json
- [W1] coenet.org institutional membership page (no public member list): https://coenet.org/about-coe/institutional-membership/. DOL ETA "Grants Awarded" page (no TRIO/GEAR UP entries): https://www.dol.gov/agencies/eta/grants/awards. ed.gov returned 403.
- Related repo notes: `docs/research/usaspending-trio-gearup.md` (fields, lag, action codes), `docs/research/apr-data-and-fy2026-awards.md` (FY2026 TS/EOC absence, DOL footprint), `docs/research/trio-gearup-funding-and-cycles.md` (cycles, FY2025 project-count drops).
