# TRIO/GEAR UP APR data at the grantee level, and how FY2026 awards appear in USAspending

Researched 2026-10-14. Only organization-level data is in scope; nothing here concerns individual students or staff. All USAspending calls went to `https://api.usaspending.gov` with no API key, on 2026-10-14. USAspending's `GET /api/v2/awards/last_updated/` returned `{"last_updated":"10/14/2026"}`.

**Access notes.** These sites answered a plain `curl` with HTTP 403 (bot or WAF block). Per the rules for this task, nothing was done to get around the blocks; each one is recorded where it matters below.
- `www.ed.gov`, including `https://www.ed.gov/data.json` (ED's open data inventory)
- `www2.ed.gov`, including the grantee-level `.xls` files
- `www.dol.gov`, including the newsroom, ETA grant awards and the ETA grant PDFs

These sites worked: data.ed.gov (CKAN API), catalog.data.gov, federalregister.gov, reginfo.gov and api.usaspending.gov.

## Short answers

**Q1. Does ED publish TRIO or GEAR UP APR data at the grantee level?**
- **Historically, yes, for some TRIO programs.** ED's data catalog lists datasets explicitly described as "grantee-level performance data derived from the annual performance reports". They are Excel `.xls` files hosted on www2.ed.gov:
  - Talent Search: 2006-07 to 2013-14
  - EOC: 2006-07 to 2013-14
  - Upward Bound and UBMS: 2003-04 to 2013-14 (data years run through 2012-13 expected high school graduates)
  - SSS: 2003-04 efficiency results and 2009-10 performance/efficiency
  - McNair: cohort tables, 2003-04 to 2013-14 (whether these are at grantee level is UNVERIFIED)
- **Nothing newer than 2013-14 was found, and nothing at all for GEAR UP, VUB or TRIO Training.**
- The files themselves returned 403, so their columns are known only from the catalog titles:
  - postsecondary enrollment rates
  - financial aid application rates
  - rates of service to low-income/first-generation participants
  - persistence and graduation rates
  - efficiency (cost per successful outcome)
  - excluded projects
- ED's 2026 APR clearance notices say the APR data are "aggregated to provide national information on project participants and program outcomes". They do not mention any project-level public release.
- **No current source of grantee-level participant counts was found** on data.ed.gov or catalog.data.gov.
- The only current grantee-level participant figures found are free-text "WILL SERVE N PARTICIPANTS" phrases inside some USAspending award descriptions. These are funded-to-serve targets, not APR actuals.

**Q2. How do the FY2026 Talent Search and EOC awards appear in USAspending?**
- **They don't yet, as of 2026-10-14.** For 84.044 and 84.066 between 2025-10-01 and 2026-10-14, USAspending has:
  - 95 transactions, all **B1 continuations** (59 TS, 35 EOC) plus 1 EOC `EX`
  - **0 A1 new awards**
  - no `P044A26…` or `P066A26…` FAINs
  - most recent action dates of **2026-08-30 (TS)** and **2026-08-29 (EOC)**
- **Agencies.** Every FY2026 transaction under all seven TRIO/GEAR UP listings (3,628 rows) has awarding agency, awarding sub-agency, funding agency and funding sub-agency all equal to **Department of Education**. No DOL rows were found.
- **Other FY2026 activity:**
  - SSS (84.042) has 49 new awards with `P042A26` FAINs (A1 actions dated 2026-08-31 to 2026-09-09), plus 23 late A1 actions on `P042A25` awards.
  - UB (84.047) and McNair (84.217) each have one A1 on a `…25` FAIN.
  - There are no new GEAR UP awards; 84.334 shows only B1 and EX actions.
- **Would an ED-only awarding-agency filter miss FY2026 TRIO/GEAR UP awards?** Not today: no TRIO/GEAR UP awards are recorded under any other agency. It would miss them as soon as DOL starts reporting them, and there is direct precedent:
  - DOL/ETA is already recorded as the awarding *and funding* agency on ED listings 84.048 (CTE State Grants) and 84.002 (Adult Education State Grants). Those records use DOL-style FAINs (`25E55EP…`) and generated IDs ending `_1601`.
  - DOL's grant reporting to USAspending is stale. DOL's latest grant action is **2026-02-20**, and DOL grant obligations are **0 for every month from March 2026 on**. DOL contract actions are current (2026-10-09).
  - So if DOL issued the FY2026 TS/EOC awards as the awarding agency, their absence would be expected. **Do not filter on awarding agency. Filter on listing number, and re-check DOL (toptier `1601`).**
- **Official publication of results.**
  - No award announcement was found on federalregister.gov.
  - dol.gov and ed.gov were blocked, so their pages are UNVERIFIED.
  - The only report found is secondary: a COE press release of Aug. 28, 2026. It says ED released a first slate of **326 TS grants (~$143M)** and **102 EOC grants (~$45M)**, with second slates pending.
  - USAspending shows **0** of these as new awards. The gap is 326 vs. 0 for TS and 102 vs. 0 for EOC. The COE figures themselves are UNVERIFIED.

---

## Q1 details: grantee-level APR data

### 1a. What ED's catalog lists (data.ed.gov, mirrored on catalog.data.gov)

Every entry is published by ED's Office of Postsecondary Education, `access_level: public`, and was last modified in ED's catalog in Dec 2022 or Jan 2023. Every file URL is on `www2.ed.gov` and returned **HTTP 403** to a plain request on 2026-10-14. Contents are therefore known only from the catalog metadata.

| Program | Dataset (catalog description) | Years (from file names/titles) | Fields, per resource titles | Format |
|---|---|---|---|---|
| Talent Search | "Grantee-level Performance Data -- Talent Search Program": "grantee-level performance data derived from the annual performance reports submitted by grantees". https://data.ed.gov/dataset/grantee-level-performance-data-talent-search-program-24c69 | 2006-07 through 2013-14 (`ts-gl-data-0607.xls` … `ts-gl-data-1314.xls`) | "Postsecondary Enrollment Rates; Financial Aid Application Rates; and Efficiency Data". The 2006-07 file has no efficiency data | XLS |
| EOC | "Educational Opportunity Centers - Grantee-level Performance Results": "granteee-level program performance data and data analysis derived from performance reports". https://data.ed.gov/dataset/educational-opportunity-centers-grantee-level-performance-results-538cd | 2006-07 through 2013-14 (`eoc-gl-data-0607.xls` … `eoc-gl-data-1314.xls`) | "Postsecondary Enrollment Rates; Rates of Service to Both Low-Income and Potentially First-Generation College Students; and Efficiency Data" | XLS |
| Upward Bound + UBMS | "Grantee-Level Performance Results -- Upward Bound Program and Upward Bound Math-Science". https://data.ed.gov/dataset/grantee-level-performance-results-upward-bound-program-and-upward-bound-math-science-51524 | Files cover expected HS graduates of 2003-04 through 2012-13; file names run `ub-grantee-level.xls`, `ubgranteelevel-tables0506.xls` … `ubgranteelevel-data1314.xls` | "Postsecondary Enrollment Rates of [year] Expected High School Graduates; Efficiency; and Excluded Projects" | XLS |
| SSS | "Performance and Efficiency Measure Results: 2009-10 under the Student Support Services Program". https://data.ed.gov/dataset/performance-and-efficiency-measure-results-2009-10-under-the-student-support-services-prog-1d7ac | 2009-10 (`measures-2009-10.xls`) | "Grantee Performance and Efficiency Tables: Persistence; Graduation Rates at Two- and Four-Year Institutions; and Efficiency Measures" | XLS |
| SSS | "Student Support Services Program - Efficiency Measure Performance Results 2003-04 - Introduction". https://data.ed.gov/dataset/student-support-services-program-efficiency-measure-performance-results-2003-04-introducti-141a8 | 2003-04 | "Grantee Efficiency Analysis" (`efficiencygranteeanalysis.xls`). The resource note says "project-level efficiency measures were calculated for the remaining 876 grants" | XLS |
| McNair | "Performance -- Ronald E. McNair Postbaccalaureate Achievement Program". https://data.ed.gov/dataset/performance-ronald-e-mcnair-postbaccalaureate-achievement-program-bf13d | Cohort years 2003-04 through 2013-14 (`mcn-cy…`, `mcn-cytables-2013-14.xls`) | Titles say only "Cohort year …". Whether these are at grantee level is UNVERIFIED. A separate entry, "Explanation of Grantee-Level Performance Results: 2004-05 and 2005-06 for the TRIO McNair Program", links only to an OMB ExpectMore page: https://data.ed.gov/dataset/explanation-of-grantee-level-performance-results-2004-05-and-2005-06-for-the-trio-mcnair-p-9aba7 | XLS |
| GEAR UP | none | n/a | data.ed.gov `package_search?q=GEAR UP` returned **count 0** | n/a |
| VUB, TRIO Training | none at grantee level | n/a | Only "Awards" grantee lists exist (e.g., https://catalog.data.gov/dataset/awards-veterans-upward-bound-program) | n/a |

**Queries used:**
- data.ed.gov: `https://data.ed.gov/api/3/action/package_search?q=<term>`, then `package_show?id=<name>`, for the terms TRIO, GEAR UP, Annual Performance Report, Upward Bound, Student Support Services, McNair, Talent Search, Educational Opportunity Centers, grantee-level, Veterans Upward Bound, Gaining Early Awareness, GEARUP and prior experience.
- catalog.data.gov: `https://catalog.data.gov/search?q=<term>`, which returns JSON. The old CKAN `/api/3/...` path returned 404. It returned the same TRIO datasets and nothing newer.

**Other "Awards" lists are grantee lists, not APR outcomes.** The catalog also has "Awards -- <program>" datasets: grantee name, amount and so on per year, e.g. "Projects funded for 2019-20". Examples:
- https://data.ed.gov/dataset/awards-talent-search-program-c35be
- https://data.ed.gov/dataset/awards-student-support-services-program-989b0

Whether these lists include "number of participants funded to serve" is UNVERIFIED, because their files are on data.ed.gov or www2 and were not opened.

**ED open data inventory.** `https://www.ed.gov/data.json` returned 403. catalog.data.gov harvests ED's inventory, and the catalog records above carry ED's DCAT metadata (`bureauCode` 018:xx, contact `odp@ed.gov`), so the inventory was effectively checked through the harvest.

### 1b. What ED says the APR data are used for (2026 PRA notices)

- **Talent Search APR**, OMB 1840-0826. The notice proposes reinstatement; the collection "expired on January 31, 2026". Estimated 517 annual responses and 9,306 burden hours. Quote: "The report provides the Department with information needed to evaluate a grantee's performance and compliance with program requirements and to award prior experience points … The data collection is also aggregated to provide national information on project participants and program outcomes." https://www.federalregister.gov/documents/2026/06/15/2026-12002/agency-information-collection-activities-comment-request-talent-search-ts-annual-performance-report. Submitted to OMB on Aug. 28, 2026: https://www.federalregister.gov/documents/2026/08/28/2026-17574/agency-information-collection-activities-submission-to-the-office-of-management-and-budget-for
- **EOC APR**, OMB 1840-0830. Estimated 160 annual responses. The APR data "are compared with the projects' approved objectives to determine the projects' accomplishments, to make decisions regarding whether funding should be continued, and to award 'prior experience' points". https://www.federalregister.gov/documents/2026/06/02/2026-10998/agency-information-collection-activities-comment-request-educational-opportunity-centers-program-eoc. Submitted to OMB: https://www.federalregister.gov/documents/2026/08/28/2026-17575/agency-information-collection-activities-submission-to-the-office-of-management-and-budget-for
- **ICR history for 1840-0830** at reginfo.gov: approvals in 2016, 2019, 2023 and 2025, and an extension received by OIRA on 08/28/2026 (ICR 202605-1840-005). https://www.reginfo.gov/public/do/PRAOMBHistory?ombControlNumber=1840-0830
- **Related 2026 notices** (not APR data releases):
  - "Description of Today's TRIO Programs and Proposing Options for Future Outcome Evaluations", a new ICR: https://www.federalregister.gov/documents/2026/03/19/2026-05419/agency-information-collection-activities-comment-request-description-of-todays-trio-programs-and
  - "GEAR UP Application Packages for Partnership and State Grants": https://www.federalregister.gov/documents/2026/06/25/2026-12775/agency-information-collection-activities-submission-to-the-office-of-management-and-budget-for

**Implication.** None of these notices commits to publishing project-level results. The latest catalogued grantee-level release is 2013-14.

### 1c. Grantee-level participant counts elsewhere

- **USAspending award descriptions** sometimes carry the number of participants a project is funded to serve. For example, `P044A220184` (Mineral Area College): "TALENT SEARCH WILL SERVE 500 PARTICIPANTS (6TH - 12TH GRADE) …". Source: `spending_by_transaction` (request in §2b below).
  - A rough regex over the FY2026 descriptions found count-like numbers in 181 of 1,934 SSS awards, 63 of 1,307 UB, 6 of 59 TS, 2 of 35 EOC, 0 of 14 McNair and 4 of 109 GEAR UP.
  - The regex also produces false positives, so treat these as upper bounds.
  - These numbers are free text written at award time. They are targets, not APR actuals.
- **ED's FY2025 project counts** per program are already in `trio-gearup-funding-and-cycles.md`. Those are program-level, not participant counts.
- **Reports to Congress / budget justifications:** not checked, because ed.gov was blocked. UNVERIFIED. They have historically held national GPRA figures; whether any include project-level tables is unknown.

---

## Q2 details: FY2026 awards in USAspending

The window is FY2026 plus FY2027 to date (`2025-10-01` → `2026-10-14`). The award types are grants (`02`–`05`).

### 2a. By agency (all seven listings)

```bash
F='{"award_type_codes":["02","03","04","05"],"program_numbers":["84.042","84.044","84.047","84.066","84.103","84.217","84.334"],"time_period":[{"start_date":"2025-10-01","end_date":"2026-10-14"}]}'
for c in awarding_agency awarding_subagency funding_agency funding_subagency cfda; do
  curl -s -X POST https://api.usaspending.gov/api/v2/search/spending_by_category/$c/ \
    -H 'Content-Type: application/json' -d "{\"filters\":$F,\"limit\":20,\"spending_level\":\"transactions\"}"; done
```

Trimmed responses:
- `awarding_agency`, `awarding_subagency`, `funding_agency` and `funding_subagency` each returned exactly one result: `{"code":"ED","name":"Department of Education","amount":1115548935.61}`.
- `cfda` returned:
  - 84.047: 431,432,380.52
  - 84.334: 331,880,931.0
  - 84.042: 325,092,827.57
  - 84.044: 13,290,505.0
  - 84.066: 11,202,025.0
  - 84.217: 2,650,266.52
  - 84.103 was absent (no FY2026 transactions).

### 2b. All transactions, paged (84.044 + 84.066, then all seven)

```bash
# Python loop over pages; same body each page, page += 1 until hasNext is false
curl -s -X POST https://api.usaspending.gov/api/v2/search/spending_by_transaction/ -H 'Content-Type: application/json' -d '{
 "filters":{"award_type_codes":["02","03","04","05"],"program_numbers":["84.044","84.066"],
            "time_period":[{"start_date":"2025-10-01","end_date":"2026-10-14"}]},
 "fields":["Award ID","Mod","Recipient Name","Recipient UEI","Action Date","Action Type","Transaction Amount",
           "Transaction Description","Assistance Listing","Awarding Agency","Awarding Sub Agency",
           "Funding Agency","Funding Sub Agency","Award Type"],
 "page":1,"limit":100,"sort":"Action Date","order":"desc"}'
```

Trimmed first result:

```json
{"Award ID":"P044A220184","Mod":"5","Recipient Name":"MINERAL AREA COLLEGE","Action Date":"2026-08-30","Action Type":"B1",
 "Transaction Amount":286000.0,"Assistance Listing":{"cfda_number":"84.044","cfda_title":"TRIO TALENT SEARCH"},
 "Awarding Agency":"Department of Education","Awarding Sub Agency":"Department of Education",
 "Funding Agency":"Department of Education","Funding Sub Agency":"Department of Education",
 "generated_internal_id":"ASST_NON_P044A220184_091"}
```

**Completeness check.** `POST /api/v2/search/spending_by_transaction_count/` and `POST /api/v2/download/count/` with the same filters returned `grants: 95` / `calculated_transaction_count: 95` for TS+EOC and `3628` for all seven listings. These match the rows paged.

**Duplicate rows.** `spending_by_transaction` returned **3,628 rows, but only 3,550 are unique** on (Award ID, Mod, Action Date, Action Type, Amount). Two examples:
- For `P042A251138` mod 2, the search returned 2 identical rows, but `POST /api/v2/transactions/` with `{"award_id":"ASST_NON_P042A251138_091"}` lists one transaction, `ASST_TX_9100_P042A251138_-NONE-_84.042_2`.
- For `P042A260270`, the search returned 2 A1 rows, but `/transactions/` lists one, `ASST_TX_9100_P042A260270_-NONE-_84.042_1`.

The count endpoints count the duplicates too. Dedupe on the transaction key. Prefer the bulk archive for totals.

**Results, deduplicated.** All rows are awarding = funding = Department of Education at both tiers.

| Listing | Transactions | Awards | Action types | Sum of obligations | Earliest / latest action |
|---|---|---|---|---|---|
| 84.042 SSS | 2,018 | 1,934 | A1 72, B1 1,080, FX 849, EX 17 | 305,860,813.00 | 2025-11-19 / 2026-09-10 |
| 84.044 TS | 59 | 59 | **B1 59** | 13,290,505.00 | 2026-03-13 / **2026-08-30** |
| 84.047 UB/UBMS/VUB | 1,313 | 1,307 | A1 1, B1 1,289, FX 21, EX 2 | 431,432,380.52 | 2025-12-01 / 2026-09-16 |
| 84.066 EOC | 36 | 35 | **B1 35, EX 1** | 11,202,025.00 | 2026-03-13 / **2026-08-29** |
| 84.217 McNair | 15 | 14 | A1 1, B1 10, FX 3, EX 1 | 2,650,266.52 | 2025-11-18 / 2026-09-14 |
| 84.334 GEAR UP | 109 | 109 | B1 104, EX 5 | 304,661,722.00 | 2026-08-31 / 2026-08-31 |
| 84.103 TRIO Training | 0 | 0 | none | 0 | none |

The latest action across all seven listings is **2026-09-16**. There are no actions dated 2026-10-01 or later.

The deduplicated sums differ from the `spending_by_category/cfda` totals in §2a: 84.042 is 305.9M vs. 325.1M, and 84.334 is 304.7M vs. 331.9M. Cause UNVERIFIED (possibly award-level vs. transaction-level listing attribution).

**FAIN cohort digits, characters 6–7, FY2026 rows only:**
- TS: `P044A21` 5, `P044A22` 51, `P044A23` 3.
- EOC: `P066A21` 2, `P066A22` 31, `P066A23` 2, `P066A24` 1.
- **No `P044A26` or `P066A26` FAIN exists.**

All 74 deduplicated A1 (new award) actions:

| FAIN prefix | A1 actions | Action dates | Notes |
|---|---|---|---|
| `P042A26` (SSS) | 49 | 2026-08-31 – 2026-09-09 | 49 awards, sum $20,254,157. Example: `P042A261503`, Utah State University, $361,922, period 2026-09-01 → 2027-08-31, funding opportunity "NOT APPLICABLE". Descriptions include "TRIO STUDENT SUPPORT SERVICES GRANT PROJECT FY25". Award detail: `GET /api/v2/awards/ASST_NON_P042A261503_091/` |
| `P042A25` (SSS) | 23 | 2026-05-26 – 2026-07-06 | Late FY2025-cohort new awards |
| `P047A25` (UB) | 1 | 2025-12-22 | `P047A250002`, Impact Prosperity Partners, $513,114 |
| `P217A25` (McNair) | 1 | 2026-06-15 | `P217A250002`, Adrian College, $92,117.37 |

New-award counts by award date: `spending_by_award_count` with `date_type: "new_awards_only"` returned **0** for [84.044, 84.066] and **74** for all seven listings.

### 2c. Is there a DOL footprint? Would an ED-only filter miss anything?

```bash
# DOL-awarded grants by listing, FY2026
curl -s -X POST https://api.usaspending.gov/api/v2/search/spending_by_category/cfda/ -H 'Content-Type: application/json' -d '{
 "filters":{"agencies":[{"type":"awarding","tier":"toptier","name":"Department of Labor"}],
            "award_type_codes":["02","03","04","05"],"time_period":[{"start_date":"2025-10-01","end_date":"2026-10-14"}]},
 "limit":60,"spending_level":"transactions"}'
```

Trimmed: `84.048 Career and Technical Education -- Basic Grants to States 768433378.0` and `84.002 Adult Education - Basic Grants to States 0.0`, alongside DOL's own 17.xxx listings. **No 84.042/044/047/066/103/217/334.** For FY2024 to date the DOL-awarded 84.* listings are only 84.048 (1,907,272,302.14) and 84.002 (1,031,831,978.82).

Precedent record:
- `GET /api/v2/awards/ASST_NON_25E55EE000017_1601/`
  - FAIN `25E55EE000017`, "ADULT EDUCATION AND FAMILY LITERACY ACT STATE GRANT", Texas Workforce Commission
  - awarding: Department of Labor / Employment and Training Administration; funding: Department of Labor
  - listing 84.002; A1 dated 2025-09-20, $16,199,794.83
- `spending_by_transaction` for 84.048 with a DOL filter returned rows such as `25E55EP000074` (California Dept. of Education), `EX`, 2025-10-02, $77,566,498, all with awarding and funding sub-agency "Employment and Training Administration".

So for ED programs that DOL administers, USAspending can show **DOL as both awarding and funding agency**, with a DOL FAIN format and an `_1601` generated ID. An ED-only awarding or funding filter would drop them.

**DOL reporting is stale for assistance.**

```bash
curl -s -X POST https://api.usaspending.gov/api/v2/search/spending_over_time/ -H 'Content-Type: application/json' -d '{
 "group":"month","filters":{"agencies":[{"type":"awarding","tier":"toptier","name":"Department of Labor"}],
 "award_type_codes":["02","03","04","05"],"time_period":[{"start_date":"2025-07-01","end_date":"2026-10-14"}]},
 "spending_level":"transactions"}'
```

Trimmed response (fiscal months; FY2026 month 1 = Oct 2025):
- FY2026 m1: 2,629,676,498.0
- m2: 243,442,665.06
- m3: 847,645,487.64
- m4: −37,292,951.75
- m5: −898,116.24
- **m6–m12 (Mar–Sep 2026): 0**
- FY2027 m1: 0

Related checks:
- DOL's latest grant transaction is `AP386432260A48`, **2026-02-20**. A query across all assistance types returned the same row.
- DOL's latest contract actions are dated **2026-10-09** (`1605JW22C0014`, `1605JE26C0002`).
- ED's latest grant action is **2026-09-18**.

The cause of the gap in DOL assistance reporting is UNVERIFIED.

**Keyword cross-check** (`spending_by_category/awarding_agency`, `keywords`, `date_type:"new_awards_only"`, FY2026 to date). None of these returned DOL:
- "Talent Search": HHS only
- "Educational Opportunity Center": none
- "TRIO": ED, HHS, NSF, NEH
- "GEAR UP": NSF
- "Upward Bound": ED, HUD, NSF

**Recipients named by COE.**
- `recipient_search_text` for "OKLAHOMA EMPLOYMENT SECURITY COMMISSION" and for "WEST VIRGINIA COUNCIL FOR COMMUNITY AND TECHNICAL COLLEGE" (grants, 2026-06-01 → 2026-10-14) returned 0 rows.
- Wisconsin DPI's existing TS awards `P044A210566` (ends 2026-08-31) and `P044A210567` (ends 2026-09-30) have no FY2026 action. No new Wisconsin DPI TS award appears.

### 2d. Published FY2026 TS/EOC results vs. USAspending

| Source | TS | EOC | Status |
|---|---|---|---|
| federalregister.gov API (`conditions[term]` "Talent Search", "Educational Opportunity Centers", "TRIO", "Gaining Early Awareness", published ≥ 2026-01-01) | No award notice. Only the Mar. 23, 2026 competition notice and the APR ICR notices | No award notice. Only the Apr. 3, 2026 competition notice and the APR ICR notices | Checked. https://www.federalregister.gov/api/v1/documents.json |
| dol.gov (newsroom, ETA grant awards) | n/a | n/a | **Blocked (403)**. UNVERIFIED |
| ed.gov (program pages, press releases) | n/a | n/a | **Blocked (403)**. UNVERIFIED |
| COE press release, Aug. 28, 2026 (**secondary**, "according to information provided to COE") | First slate of **326 grants, ~$143M** for FY2026; 28 more selected to start in FY2027/28; ~$32M left for a second slate. Statewide awards to the Executive Office of the State of Ohio and Wisconsin DPI | First slate of **102 grants, ~$45M**; 28 more to start in FY2027–29; ~$8M left. Statewide awards to the Oklahoma Employment Security Commission and the West Virginia Council for Community and Technical College Education | https://coenet.org/?p=7522. UNVERIFIED against a primary source |
| USAspending (this pull) | **0 new awards**; 59 B1 continuations | **0 new awards**; 35 B1 continuations | Live, 2026-10-14 |

The 59 TS and 35 EOC FY2026 continuations are at least consistent with COE's statement that projects with years remaining "will continue operating in FY 2026 through non-competing continuation awards". The counts are not directly comparable, though, and this is my inference.

---

## Open questions / UNVERIFIED

- **Contents and columns of the grantee-level `.xls` files** on www2.ed.gov (all returned 403). Field descriptions above come only from catalog titles. Whether files after 2013-14 exist on ed.gov but are uncatalogued is also UNVERIFIED.
- **McNair cohort tables:** whether they are at grantee level is UNVERIFIED.
- **Full APR field lists** (e.g., participants served by type): the ICR packages on reginfo.gov (OMB 1840-0826 and 1840-0830, plus the other programs' APRs) were not opened. Next step: the `PRAViewICR` documents for ICR 202605-1840-005, https://www.reginfo.gov/public/do/PRAOMBHistory?ombControlNumber=1840-0830
- **ED reports to Congress and budget justifications** with any project-level participant data: not checked (ed.gov blocked).
- **Official FY2026 TS/EOC award lists and counts:** none were found in a primary source. The COE figures (326 TS / ~$143M; 102 EOC / ~$45M) are secondary.
- **Which agency will show as awarding and funding for the FY2026 TS/EOC awards** when they appear: ED (FAIN `P044A26…`) or DOL/ETA (`_1601`, DOL FAIN format, as with 84.048/84.002). UNVERIFIED.
- **Why DOL assistance reporting to USAspending stops after 2026-02-20:** UNVERIFIED. Re-check `spending_over_time` for DOL monthly.
- **What the 49 `P042A26` SSS awards are.** They have one-year periods (2026-09-01 → 2027-08-31), funding opportunity "NOT APPLICABLE", and descriptions mentioning "FY25". They could be FY2025-competition awards made after the Jan. 16, 2026 court order, but that is a guess. UNVERIFIED.
- **Duplicate rows and sum mismatches.** `spending_by_transaction` returns duplicates (3,628 raw vs. 3,550 unique), and listing totals differ from `spending_by_category/cfda`. The cause of both is UNVERIFIED. Use the ED (and DOL) Award Data Archive for totals.
- **Funded-to-serve numbers in USAspending descriptions** are free text from grantees or ED. Coverage is sparse, and they are not APR actuals.
