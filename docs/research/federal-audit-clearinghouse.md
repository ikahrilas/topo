# Federal Audit Clearinghouse (FAC) as a spending check and a UEI–EIN bridge

Researched 2026-10-14 (some response headers show 2026-10-15 UTC). Live API calls went to `https://api.fac.gov` using api.data.gov's public `DEMO_KEY`. Bulk CSVs were downloaded from the FAC's public download links without a key. Organization-level data only. Read with `usaspending-trio-gearup.md`.

## Verdict

**(a) Independent check on grantee-level spending: yes, partly.** FAC gives each auditee's audited **amount expended** for each Assistance Listing, from the Schedule of Expenditures of Federal Awards (SEFA).
- **What it is good for:** a year-level plausibility check on USAspending **obligations**. It is not a dollar-for-dollar reconciliation (see §7).
- **Coverage gap 1, threshold:** only entities whose *total* federal spending is ≥ $1M (fiscal years starting on or after 2024-10-01; $750K before that) must file.
- **Coverage gap 2, consolidated filers:** many public universities, and some private systems, are audited inside a state, system, or parent audit. Their own UEI then appears only in `additional_ueis`, or not at all.
- **Live cross-match:** I matched 1,345 ED recipients of TRIO/GEAR UP obligations in FY2024 (USAspending) against FAC audit years 2023–2025:
  - 748 (56%) are the primary auditee of some audit.
  - 434 (32%) appear only as an *additional* UEI on someone else's audit.
  - ~163 (12%) are absent.
  - Recipients found in FAC account for 90% of FY2024 obligation dollars.
- **FAIN is usually missing:** a usable FAIN (e.g. `P047A221315`) appears in `additional_award_identification` on only ~12% of TRIO/GEAR UP SEFA rows. Award-level matching is therefore mostly impossible. Matching works at the level of (UEI, listing, fiscal year).

**(b) Bridge between UEI and EIN: yes, for primary auditees from audit year 2022 on, with cleanup.**
- **Where the pair lives:** each `general` row carries one `auditee_uei` and one `auditee_ein`. Further EINs are in `additional_eins`, and further UEIs are in `additional_ueis`.
- **How stable it is:** for the 759 TRIO/GEAR UP recipient UEIs that are primary auditees in 2022+, 728 (96%) map to exactly one EIN across years. The other 31 have two, often from typos (e.g. `205143175` vs `215143175`).
- **Limit 1, older years:** before 2022, migrated Census records carry `auditee_uei = "GSA_MIGRATION"`, so they cannot be bridged.
- **Limit 2, consolidated audits:** additional UEIs and additional EINs are separate lists with no pairing between them. A campus UEI listed under a state or system audit therefore cannot be tied to its own EIN.

## 1. API: base URL, auth, limits, endpoints, paging, bulk

**Base URL.** `https://api.fac.gov` is the production endpoint, "typically updated once per week on Wednesdays." `api-staging`, `api-dev` and `api-preview` contain test data. Source: https://www.fac.gov/api/getting-started/

**Authentication.**
- An api.data.gov key is required. The getting-started page says: "To use the API, you will need an API key from Data.gov" (https://www.fac.gov/api/).
- The key goes in the `X-Api-Key` header. api.data.gov also allows an `api_key` query parameter or HTTP basic auth (https://api.data.gov/docs/developer-manual/).
- With no key, `https://api.fac.gov/` returned `403 {"error":{"code":"API_KEY_MISSING",...}}` (live).

**DEMO_KEY works.** FAC documents it: "30 requests per IP address per hour, 50 requests per IP address per day … DEMO_KEY provides access only to publicly available FAC data. It does not provide access to suppressed Tribal audit information." (https://www.fac.gov/api/getting-started/). api.data.gov states the same limits (https://api.data.gov/docs/developer-manual/).
- **Observed:** the live responses carried `x-ratelimit-limit: 10`, falling to `x-ratelimit-remaining: 3` after 7 calls. This is lower than the documented 30/hour, so in practice DEMO_KEY allowed only 10 calls per hour (or per some window) on FAC.

**Rate limit with a personal key.** api.data.gov's default is 1,000 requests/hour per key, and "Rate limits may vary by service" (https://api.data.gov/docs/developer-manual/). *A FAC-specific limit for personal keys is UNVERIFIED.*

**Endpoints (tables).** These are PostgREST views (https://www.fac.gov/api/dictionary/):
- `general`
- `federal_awards`
- `notes_to_sefa`
- `findings`
- `findings_text`
- `corrective_action_plans`
- `passthrough`
- `secondary_auditors`
- `additional_ueis`
- `additional_eins`
- `resubmission`

**API versions** (GSA-TTS/FAC repo, `backend/dissemination/api/README.md` and `api_versions.py`, main @ `030cb3cc05c73aea249843e9f3a4764df1fda65d`; https://github.com/GSA-TTS/FAC/tree/main/backend/dissemination/api):
- Live schemas are `api_v1_1_0` (the default), `api_v1_2_0`, `api_v1_3_0` and `api_v1_3_1`.
- v1.3.x adds a `unified` view.
- You select a version with the PostgREST `Accept-Profile` header. Live: `Accept-Profile: api_v1_3_1` returned `content-profile: api_v1_3_1`. Default responses showed `content-profile: api_v1_1_0`.

**Filtering and paging** (PostgREST syntax):
- Filters look like `col=eq.X` or `col=in.(a,b)`, plus `select=`, `limit=`, `offset=`.
- Responses are capped at **20,000 rows per request**. Page with `limit`/`offset` and the PostgREST range headers. Source: https://www.fac.gov/api/results-management/
- `Prefer: count=exact` returns the total in `Content-Range` (live: `content-range: 0-2/874`).

**Bulk download (no key needed)** (https://www.fac.gov/data/download/current/):
- **Full CSVs per table:** `https://app.fac.gov/dissemination/public-data/gsa/full/<table>.csv`. These 302-redirect to a short-lived signed S3 URL.
- **Split files:** per audit year (`general-ay-2016.csv`) and per federal fiscal year of submission (`-ffy-`). *These links are rendered client-side, and I did not retrieve their exact URLs.*
- **Sizes downloaded 2026-10-14:**
  - `general.csv`: 272.8 MB, 418,551 rows
  - `federal_awards.csv`: 1.35 GB
  - `additional_eins.csv`: 4.8 MB
  - `additional_ueis.csv`: 1.9 MB
- **Historic Census data (1998–2015):** per-year ZIPs at `https://app.fac.gov/dissemination/public-data/census/csv/census-YYYY.zip`, with SHA1 files. These are "not included in our web-based search or API" (https://www.fac.gov/data/download/historic/).
- *How often the bulk files are refreshed is UNVERIFIED.*

**Recommendation for this project.** Use the bulk CSVs and scan them with polars, filtering `federal_awards` on `federal_agency_prefix == "84"` and the extensions. The TRIO/GEAR UP universe is about 3,200 rows a year. The API is fine for spot checks.

## 2. Fields

Field lists come from the API dictionary (https://www.fac.gov/api/dictionary/), the CSV dictionary (https://www.fac.gov/data/download/current-dictionary/), the view SQL (`backend/dissemination/api/api_v1_1_0/create_views.sql`), and live responses.

**`general` (one row per audit report)**

| Concept | Field | Notes |
|---|---|---|
| Report key | `report_id` | e.g. `2024-06-GSAFAC-0000361420`; Census-era: `2022-06-CENSUS-0000091651` (https://www.fac.gov/data/migration/) |
| UEI | `auditee_uei` | `"GSA_MIGRATION"` on ~all Census-migrated records for audit years 2016–2021 (bulk: 36,989 of 36,991 in 2016; 1 of 48,171 in 2022; 0 after) |
| EIN | `auditee_ein` | TEXT, 9 digits, no hyphen (all 418,551 rows are 9 characters) |
| Multiple EINs | `is_multiple_eins` (Yes/No) | Computed as "exists in `additional_eins`" (view SQL); the extra EINs are in `additional_eins.additional_ein` |
| Multiple UEIs | `is_additional_ueis` | Extra UEIs are in `additional_ueis.additional_uei` |
| Name / address | `auditee_name`, `auditee_address_line_1`, `auditee_city`, `auditee_state`, `auditee_zip` | Since May 2026, name and address are pre-filled from SAM.gov by UEI at submission (https://www.fac.gov/updates/2026-06-01/) |
| Entity type | `entity_type` | `non-profit`, `state`, `local`, `higher-ed`, `tribal`, `unknown` |
| Audit year | `audit_year` | Dictionary: "Year in which the audit was conducted". In the data it tracks the year of `fy_end_date` (e.g. audit_year 2024 has fy_end from 2024-01-17 to 2024-12-31) |
| Fiscal period | `fy_start_date`, `fy_end_date`, `number_months`, `audit_period_covered` (`annual`/`biennial`/`other`) | Migrated records' FY dates are off by one day (https://www.fac.gov/data/reliability/concerns/) |
| Total federal expended | `total_amount_expended` | Entity-wide, all programs |
| Type A/B threshold | `dollar_threshold` | "Dollar threshold to distinguish between type A and type B programs". This is **not** the single-audit threshold |
| Public flag | `is_public` | `false` = Tribal audit that opted out |
| Source | `data_source` | `CENSUS` or `GSAFAC` |
| Dates | `submitted_date`, `fac_accepted_date`, … | |
| Resubmission | `resubmission_version`, `resubmission_status` | API views show only `most_recent` (view SQL); the bulk `general.csv` held only `most_recent` |

**`federal_awards` (one row per SEFA line)**

| Concept | Field | Notes |
|---|---|---|
| Keys | `report_id`, `auditee_uei`, `audit_year`, `fac_accepted_date`, `award_reference` (`AWARD-####`) | `auditee_uei` comes from `general`, so awards carry no recipient UEI of their own |
| Assistance Listing | `federal_agency_prefix` (`"84"`) + `federal_award_extension` (`"047"`) | FAC "does not distribute the ALN"; you join the two with `.` (https://www.fac.gov/api/rollup/). Some filers add the suffix (`042A`, `047M`, `334S`: ~65 TRIO-named rows in 2024) or use `U##`/`RD` |
| Program name | `federal_program_name` | e.g. `TRIO UPWARD BOUND` |
| Free-form id | `additional_award_identification` | Workbook: "required if you don't know the agency's CFDA extension … can be left blank" (`backend/schemas/source/excel/libs/InstructionsFederalAwards.libsonnet`). For TRIO/GEAR UP rows: non-empty 49% (2024), a parseable FAIN `P0xxA######` ~12% |
| Amount | `amount_expended` | "Total amount of federal funds expended for an award. Rounded to the nearest whole dollar". Can be negative (seen: `-12`) |
| Program / cluster totals | `federal_program_total`, `cluster_total` | Auto-computed in the workbook |
| Cluster | `cluster_name`, `other_cluster_name`, `state_cluster_name` | 2024 TRIO/GEAR UP rows: `TRIO CLUSTER` 2,278, `N/A` 864 (mostly GEAR UP), `RESEARCH AND DEVELOPMENT` 52 |
| Direct vs. pass-through **in** | `is_direct` (Y/N) | Workbook: "Select "Y" if the award came directly from a Federal awarding agency". When N, the pass-through entity's name and id are in the `passthrough` table (`passthrough_name`, `passthrough_id`) |
| Passed **out** to subrecipients | `is_passthrough_award`, `passthrough_amount` | Workbook: "Select "Y" if the auditee entity passed on the Federal award to a subrecipient" and "Enter the amount passed through to the subrecipient". **The CSV dictionary's description of `is_passthrough_award` ("passed through another entity before reaching the auditee") contradicts the workbook. Follow the workbook.** |
| Major program / findings | `is_major`, `audit_report_type`, `findings_count` | |
| Loans | `is_loan`, `loan_balance` | |

**2024 direct vs. indirect for TRIO/GEAR UP** (bulk): 84.334 GEAR UP is mostly `is_direct = N` (598 N vs. 185 Y): state GEAR UP grants flow down to districts and colleges. The TRIO listings are ~97% direct.

## 3. Single-audit threshold

**Current rule.** 2 CFR 200.501(a): "A non-Federal entity that expends $1,000,000 or more during the non-Federal entity's fiscal year in Federal awards must have a single or program-specific audit". Paragraph (e) exempts entities under $1,000,000. Source: https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-F/subject-group-ECFR4424206eaecf751/section-200.501, fetched via `https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-2.xml?part=200&section=200.501`.

**Before.** The version in force on 2024-09-30 reads "$750,000 or more" (`…/full/2024-09-30/title-2.xml?part=200&section=200.501`).

**When it changed.** The eCFR version history shows one substantive amendment, dated **2024-10-01**, after 2020-11-12 (`https://www.ecfr.gov/api/versioner/v1/versions/title-2.json?part=200&section=200.501`).
- *The exact transition rule, "fiscal years beginning on or after October 1, 2024", is in the Federal Register preamble (89 FR 30046). That is outside the allowed sources, so the phrasing is **UNVERIFIED** here.*
- The data is consistent with it. Of 14,344 audits with `fy_start_date >= 2024-10-01`, only 11 report total expended under $1M. Of 71,227 audits with FY starts from 2023-07 to 2024-09, 6,884 (9.7%) were in the $750K–$1M band.
- FAC's own data page now says audits are required for entities that "spend $1,000,000) or more" (sic, https://www.fac.gov/data/).

**Type A threshold also moved.** 200.518(b)(1) now sets the minimum Type A threshold at $1,000,000. This is what `dollar_threshold` records (https://www.ecfr.gov/current/title-2/section-200.518).

**What this means for TRIO coverage:**
- **The threshold is entity-wide.** It tests the entity's *total* federal awards expended, not any single award (200.501(a)), and subrecipient spending counts (200.501(g)).
  - A university with Pell, research, and one $300K Talent Search grant is audited, and the TRIO line appears on its SEFA.
  - A standalone community nonprofit whose only federal money is one Upward Bound grant of about $300–700K is **exempt** (200.501(e)) and will not appear in FAC.
- **Expect FAC to miss mainly the small nonprofits and some small colleges.** In 2024, every primary auditee with a TRIO/GEAR UP line had total expended ≥ $787,886, and the 5th percentile was ≈ $1.83M. Only 15 of 1,194 TRIO/GEAR UP auditees in 2024 fell in the $750K–$1M band that the new threshold removes. The rise to $1M is therefore a small extra loss.
- **Program-specific audits:** an entity with only one federal program may elect one (200.501(c)). It is still filed in FAC (`audit_type` = `program-specific`).
- **Due date** (200.512(a)(1)): earlier of 30 days after the auditor's report or 9 months after FY end. The latest audit year is therefore incomplete for a long time: on 2026-10-14, audit year 2025 had 40,287 reports vs. 46,696 for 2024.

## 4. Data history

- **GSA took over in October 2023.** "GSA began collecting Single Audits in October of 2023; we completed migration of 98% of the data from Census in February of 2024, and the final 2% in July of 2024" (https://www.fac.gov/data/migration/).
- **Census records were resubmitted, not copied.** They went through GSA validation as "virtual" submissions. Gaps are annotated `GSA_MIGRATION`, and a CSV of the migration changes is published (https://www.fac.gov/data/migration/, https://www.fac.gov/data/download/).
- **Old Census keys.** The Census `DBKEY` + `AUDITYEAR` became `report_id` = `<AUDITYEAR>-<MM>-CENSUS-<DBKEY>` (https://www.fac.gov/data/migration/).
- **How far back:**
  - The API and current CSVs cover audit years **2016 to present** (https://www.fac.gov/data/download/current/). Bulk `general.csv` has 36,991 reports in 2016, 37–48K/year since, and 812 so far for 2026.
  - 1998–2015 is available only as historic Census ZIPs, with different column names (https://www.fac.gov/data/download/historic/).
- **TRIO/GEAR UP rows in the current set** (prefix 84, extensions 042/044/047/066/217/103/334): 31,206 in total, about 2,900–3,500 per audit year.
- **Known data issues** are listed at https://www.fac.gov/data/reliability/concerns/. Examples: migrated FY dates are off by one day, migrated accepted dates are wrong, some historical audit reports are missing, and duplicate valid submissions (Apr 2026).

## 5. Live tests

**Test 1: Upward Bound (84.047), audit year 2024, with an exact count.**

```bash
curl -s -D - -H "X-Api-Key: DEMO_KEY" -H "Prefer: count=exact" \
  "https://api.fac.gov/federal_awards?federal_agency_prefix=eq.84&federal_award_extension=eq.047&audit_year=eq.2024&limit=3"
```

Result: `HTTP/2 206`, `content-range: 0-2/874` gives **874 SEFA rows**. The bulk CSV agrees: 874. Headers also showed `content-profile: api_v1_1_0`, `x-ratelimit-limit: 10`, `x-ratelimit-remaining: 9`. First row:

```json
{"report_id":"2024-06-GSAFAC-0000361420","auditee_uei":"PMELJCUDNL17","audit_year":"2024",
 "fac_accepted_date":"2025-03-29","award_reference":"AWARD-00062","federal_agency_prefix":"84",
 "federal_award_extension":"047","additional_award_identification":"P047A221315",
 "federal_program_name":"TRIO UPWARD BOUND","amount_expended":687754,"cluster_name":"TRIO CLUSTER",
 "cluster_total":4127015,"federal_program_total":1948592,"is_major":"N","is_loan":"N",
 "is_direct":"Y","findings_count":0,"is_passthrough_award":"N","passthrough_amount":null}
```

**Test 2: SSS + Upward Bound (84.042, 84.047), audit year 2025, count only.**

```bash
curl -s -D - -o /dev/null -H "X-Api-Key: DEMO_KEY" -H "Prefer: count=exact" \
  "https://api.fac.gov/federal_awards?federal_agency_prefix=eq.84&federal_award_extension=in.(042,047)&audit_year=eq.2025&select=report_id&limit=1"
```

Result: `content-range: 0-0/1668`, so **1,668 rows**. Audit year 2025 is still filling in.

**Test 3: UEI and EIN for that auditee.** `federal_awards` carries UEI but **no EIN**; the EIN is on `general`.

```bash
curl -s -H "X-Api-Key: DEMO_KEY" "https://api.fac.gov/general?report_id=eq.2024-06-GSAFAC-0000361420&select=report_id,auditee_uei,auditee_ein,is_multiple_eins,is_additional_ueis,auditee_name,auditee_address_line_1,auditee_city,auditee_state,auditee_zip,entity_type,audit_year,fy_start_date,fy_end_date,total_amount_expended,dollar_threshold,is_public,data_source,fac_accepted_date"
```

```json
[{"report_id":"2024-06-GSAFAC-0000361420","auditee_uei":"PMELJCUDNL17","auditee_ein":"660177776",
  "is_multiple_eins":"No","is_additional_ueis":"Yes",
  "auditee_name":"UNIVERSIDAD INTERAMERICANA DE PUERTO RICO, INC",
  "auditee_address_line_1":"Jardines Metropolitanos 399 Calle Galileo","auditee_city":"San Juan",
  "auditee_state":"PR","auditee_zip":"00927","entity_type":"higher-ed","audit_year":"2024",
  "fy_start_date":"2023-07-01","fy_end_date":"2024-06-30","total_amount_expended":203730750,
  "dollar_threshold":3000000,"is_public":true,"data_source":"GSAFAC","fac_accepted_date":"2025-03-29"}]
```

**Cross-check against USAspending.** The award `P047A221315` in USAspending (`GET https://api.usaspending.gov/api/v2/awards/ASST_NON_P047A221315_091/`):
- Recipient is "INTER AMERICAN UNIVERSITY OF PUERTO RICO, INC." with UEI **`JU7XZBC56KJ4`**, which is a campus UEI, not the system UEI `PMELJCUDNL17`.
- That UEI is listed in FAC `additional_ueis` for this report (bulk; 11 additional UEIs; the API with `Accept-Profile: api_v1_3_1` returned the first 3).
- This illustrates both points above: matching must use `additional_ueis`, and the system EIN `660177776` is not necessarily the campus's EIN.
- Amounts: the USAspending obligation of 687,786 (B1 continuation, 2023-05-12) compares with FAC's 687,754 expended for FY Jul 2023–Jun 2024. The two are close but are different measures.

**Test 4: Tribal suppression.** I picked a non-public audit (`is_public = f`, entity_type `tribal`) from the bulk file.

```bash
for t in federal_awards notes_to_sefa findings_text; do
  curl -s -D - -H "X-Api-Key: DEMO_KEY" -H "Prefer: count=exact" "https://api.fac.gov/$t?report_id=eq.2024-12-GSAFAC-0000381736&limit=1"; done
```

- `federal_awards`: `content-range: 0-0/10` (visible).
- `notes_to_sefa`: `*/0`.
- `findings_text`: `*/0`.

This matches the view SQL. `findings_text`, `corrective_action_plans` and `notes_to_sefa` are filtered by `is_public_audit_or_authorized_user(gen.is_public)`, while `general` and `federal_awards` are not (`api_v1_1_0/create_views.sql`, `create_functions.sql`). It also matches FAC's terms: for Tribal opt-outs, "SEFA notes, Audit findings, Corrective action plans" are not public for fiscal periods ending 2019 or later (https://www.fac.gov/api/terms/). Tribal API access for authorized federal users dates from April 2024 (https://www.fac.gov/updates/2024-04-15/).
- Scale: 4,922 non-public reports in total; in 2024, 518, all tribal. Among 2024 TRIO/GEAR UP reports, 2 were non-public.

**Bulk-derived counts** (TRIO/GEAR UP = prefix 84, extension in 042/044/047/066/217/103/334; from `federal_awards.csv` + `general.csv`, downloaded 2026-10-14):

| audit_year | listing | SEFA rows | reports | distinct auditee UEIs | sum amount_expended |
|---|---|---|---|---|---|
| 2023 | 84.042 | 813 | 570 | 561 | 361,506,518 |
| 2023 | 84.047 | 1,060 | 480 | 468 | 435,989,436 |
| 2025 (partial) | 84.047 | 864 | 444 | 435 | 446,478,783 |
| 2025 (partial) | 84.334 | 768 | 491 | 480 | 465,533,962 |

- **2024 TRIO/GEAR UP reports by entity type:** 1,194 reports: higher-ed 555, local 420, non-profit 149, state 62, tribal 4, unknown 4. Every one has a non-empty EIN, and 77 have `is_multiple_eins = Yes`.
- **Coverage vs. USAspending** (script: USAspending `POST /api/v2/search/spending_by_category/recipient/`, ED, listings above, grants, FY2024; 1,345 recipient UEIs):

| Matched against FAC audit years | in FAC as primary or additional UEI | primary auditee with a TRIO/GEAR UP line | share of obligation $ in FAC |
|---|---|---|---|
| 2024 | 1,146 | 708 | 88.1% |
| 2023–2025 | 1,182 | 730 (737 allowing `042A`-style extensions) | 90.4% |

- **Who is missing:** the biggest absent recipients for 2024–2025 include University of Washington, Wichita State, Northern Arizona, Arizona State and the Massachusetts Department of Higher Education. These are likely covered by state-level audits that do not list their UEIs (*UNVERIFIED*). The median missing recipient got $469,690.
- **Bad UEI joins happen.** The UEI `V6AFQPN18437` ("University of Texas at Austin" in USAspending) is the primary auditee on a report with `entity_type = local` that has K-12 programs and no TRIO line. That points to the same UEI being reused by an affiliated entity. Joins on UEI alone need a sanity check.

## 6. Terms of use and attribution

- **Public domain.** "The data collected by the FAC is free to use and in the public domain." (https://www.fac.gov/data/)
- **API terms** (https://www.fac.gov/api/terms/): reporting packages are public under 2 CFR 200.512(b)(1) unless exempt. Tribes may restrict access under 200.512(b)(3). The page cites "(b)(2)", but the eCFR text puts the Tribal opt-out in (b)(3) (https://www.ecfr.gov/current/title-2/section-200.512).
- **Key handling.** Personal keys must not be shared or committed (https://www.fac.gov/api/signup/).
- **Attribution.** No attribution or citation requirement was found on fac.gov. *That none exists is UNVERIFIED.* Suggested credit: "Federal Audit Clearinghouse (GSA), fac.gov, accessed YYYY-MM-DD".
- **PII.** `general` includes named contacts, emails and phone numbers for auditee and auditor certifiers. Drop these columns to keep the project organization-level.

## 7. "Amount expended" (FAC) vs. "obligation" (USAspending)

| | FAC `amount_expended` | USAspending `federal_action_obligation` |
|---|---|---|
| What it measures | Federal award money the **recipient spent**, based on "when the activity related to the Federal award occurs", e.g. expenditure/expense transactions and disbursements to subrecipients (2 CFR 200.502(a), https://www.ecfr.gov/current/title-2/section-200.502) | The amount the **agency committed** in a transaction. Data dictionary: "Amount of Federal government's obligation, de-obligation, or liability … for an award transaction" (see `usaspending-trio-gearup.md` §3) |
| Time basis | The auditee's **fiscal year** (`fy_start_date`–`fy_end_date`), often Jul–Jun for colleges and districts | The **action date**, grouped by federal FY (Oct–Sep). ED TRIO continuations are dated around May–Sep for a budget year starting about Sep 1 |
| Granularity | One SEFA line per award (or per program) per auditee; rounded to whole dollars; FAIN usually absent | One row per FAIN per transaction |
| Who reports it | Auditee, audited by an independent auditor | Awarding agency (ED), via FABS |
| Sub-flows | `is_direct = N` lines are money received as a **subrecipient**, i.e. not in USAspending prime awards for that entity. `passthrough_amount` is money passed on to others | Prime awards only; subawards are reported separately (FSRS, ≥ $30K) |

**Reconciliation rules of thumb:**
1. **Compare spending with funding over the same span.** Over a 5-year project, the sum of `amount_expended` across the auditee's fiscal years should approach the sum of obligations, less unspent carryover or lapsed funds. A single year will not tie exactly: the budget period straddles two fiscal years, and recipients spend after the obligation date.
2. **Use the right outlay measure.** USAspending `total_outlays` (reported since FY22) is the closer federal-side analog to "expended", but it is still the agency's cash-disbursement view, not the recipient's accrual-basis expense. *How close the two get is UNVERIFIED.*
3. **Match direct to direct.** Restrict FAC to `is_direct = 'Y'` when comparing with prime awards. For GEAR UP state grants, the money the state passes down shows up both as the state's `passthrough_amount` and as `is_direct = 'N'` expenditure at districts and colleges. Do not double-count.
4. **Use the right key.** Match on (UEI, including `additional_ueis`) × listing × fiscal year, and use the FAIN in `additional_award_identification` when it parses as `P0(42|44|47|66|217|103|334)[A-Z]\d{6}` (about 12% of rows).

## Open questions / UNVERIFIED

- The exact effective-date wording ("fiscal years beginning on or after October 1, 2024") for the $1M threshold lives in the Federal Register preamble, which I did not read because it is outside the allowed sources. eCFR shows only the 2024-10-01 amendment date, and the data is consistent with it.
- The FAC API rate limit for personal api.data.gov keys is undocumented on fac.gov. The api.data.gov default is 1,000/hour. DEMO_KEY returned `x-ratelimit-limit: 10`, not the documented 30/hour.
- The refresh cadence of the bulk CSVs, and the exact URLs of the per-audit-year and per-FFY split files (rendered client-side), were not checked.
- Why ~12% of FY2024 TRIO/GEAR UP recipients (by count; ~10% of dollars) are absent from FAC 2023–2025 is not established. The likely reasons are state or system audits that do not list campus UEIs, entities under the threshold, and audits not yet filed. Not verified recipient by recipient.
- Whether `additional_ueis` and `additional_eins` correspond to each other: there is no pairing key, so a campus UEI → campus EIN link cannot be derived from FAC.
- Whether GEAR UP predecessor or other listings (e.g. 84.272) appear in the historic 1998–2015 Census files was not checked.
- The CSV data dictionary describes `is_passthrough_award` as inbound, which conflicts with the submission workbook (outbound to subrecipients). I followed the workbook. Worth asking the FAC helpdesk.
- No attribution requirement was found. The absence is not confirmed.
- Scripts used for the bulk analysis were throwaway (`/tmp/facr_scripts/`) and are not part of the repo.
