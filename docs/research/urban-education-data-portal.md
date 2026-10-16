# Urban Institute Education Data Portal: is it current enough to be our main source?

Researched 2026-10-14. Every "latest year" below comes from a live call made that day (requests and trimmed responses are in the Appendix), or from the publisher's own download listing. Quotes are verbatim from the cited URL. **UNVERIFIED** means I could not confirm it from a primary source.

**Year convention.** On the portal, `year` = the fall in which the academic year begins: "Year that the academic year begins (e.g., the 2013–14 academic year is 2013)". Source: variable metadata at https://educationdata.urban.org/documentation/data/api-endpoint-varlist.json (the `year` variable on every endpoint checked, including CCD, IPEDS, CRDC and SAIPE). So Urban `2024` = school year 2024-25. SAIPE is the exception, covered in its section below.

## Recommendation

Use Urban as the default for **CCD (directory, enrollment, FRL)**, **IPEDS (directory, institutional characteristics, enrollment)**, and **SAIPE**. As of today these tables match the latest year the publisher has released, with one exception: NCES has published a 2025-26 *preliminary* CCD directory that Urban doesn't have yet.

Pull these **directly from the publisher**:

1. **CRDC SAT/ACT participation and AP enrollment.** Urban stops at 2021-22. OCR released the 2023-24 public-use file at https://civilrightsdata.ed.gov/assets/ocr/docs/2023-24-crdc-data.zip, which has `SCH/SAT and ACT.csv` and `SCH/Advanced Placement.csv`. Urban has added only the 2023 *offerings* table so far.
2. **College Scorecard (all of it).** Urban's Scorecard endpoints end in 2016-2020. Scorecard's own files run "1996-97 through 2025-26", last updated June 10, 2026 (https://collegescorecard.ed.gov/data/). Use the Scorecard bulk zip; the API needs a key and returns at most 100 rows per page. The bulk zip also has the OPEID↔UNITID crosswalk.
3. **Optional: CCD 2025-26 preliminary directory.** Pull this from NCES (https://nces.ed.gov/ccd/files.asp) only if we need the newest school and district roster before Urban loads it. It has directory fields only: no membership, no FRL.

Access pattern: use the per-endpoint bulk CSVs at `https://educationdata.urban.org/csv/...` and the JSON API for small filtered pulls. Robots.txt disallows `/api/` with `Crawl-delay: 1` (https://educationdata.urban.org/robots.txt), so prefer `/csv/` for bulk loads. The CSVs can lag the API, though. The SAIPE CSV is still labeled 1995–2022, while the API has data through 2024.

## Per-dataset summary

| Dataset | Urban latest year | Publisher latest year | Gap | Source URLs |
|---|---|---|---|---|
| CCD school directory (incl. FRL counts) | 2024 (= SY 2024-25) | SY 2024-25 (v.2a school file, Lunch Program Eligibility). SY 2025-26 *preliminary directory only* (v.0a) | 0 for FRL/enrollment. 1 year for directory-only fields | https://educationdata.urban.org/api/v1/schools/ccd/directory/2024/ · https://nces.ed.gov/ccd/files.asp · https://nces.ed.gov/ccd/data/zip/ccd_sch_029_2526_w_0a_050626.zip |
| CCD district directory | 2024 | SY 2024-25 (v.1a). SY 2025-26 preliminary directory | 1 year (preliminary directory only) | https://educationdata.urban.org/api/v1/school-districts/ccd/directory/2024/ · https://nces.ed.gov/ccd/data/zip/ccd_lea_029_2526_w_0a_050626.zip |
| CCD enrollment (school/district by grade, race, sex) | 2024 | SY 2024-25 (membership v.1a) | 0 | https://educationdata.urban.org/api/v1/schools/ccd/enrollment/2024/grade-9/ · https://nces.ed.gov/ccd/Data/zip/ccd_sch_052_2425_l_1a_073025.zip |
| IPEDS directory (HD) | 2025 (= 2025-26) | 2025-26 Fall collection, provisional, released July 28, 2026 | 0 | https://educationdata.urban.org/api/v1/college-university/ipeds/directory/2025/ · https://nces.ed.gov/ipeds/survey-components/data-release-schedule |
| IPEDS institutional characteristics (IC) | 2025 | 2025-26 Fall collection, provisional (July 28, 2026) | 0 | https://educationdata.urban.org/api/v1/college-university/ipeds/institutional-characteristics/2025/ · same schedule URL |
| IPEDS fall enrollment (EF) | 2024 (fall 2024) | 2024-25 Spring collection, provisional, released Jan 6, 2026 | 0 | https://educationdata.urban.org/api/v1/college-university/ipeds/fall-enrollment/2024/undergraduate/race/sex/ · same schedule URL |
| IPEDS 12-month headcount (E12) | 2024 | 2025-26 Fall collection includes E12 (provisional July 28, 2026) | 0 or 1: **UNVERIFIED** which collection Urban's `2024` maps to | https://educationdata.urban.org/api/v1/college-university/ipeds/enrollment-headcount/2024/undergraduate/ |
| CRDC SAT/ACT participation | 2021 (= 2021-22) | 2023-24 (zip last-modified 2026-08-31) | 1 collection (CRDC is biennial, so 2 school years) | https://educationdata.urban.org/api/v1/schools/crdc/sat-act-participation/2021/race/sex/ · https://civilrightsdata.ed.gov/assets/ocr/docs/2023-24-crdc-data.zip |
| CRDC AP/IB/GT enrollment | 2021 | 2023-24 | 1 collection | https://educationdata.urban.org/api/v1/schools/crdc/ap-ib-enrollment/2021/race/sex/ · same zip |
| CRDC AP exams (taking/passing) | 2017 | The 2023-24 `Advanced Placement.csv` has no exam columns (0 header columns contain `EXAM`) | Not collected recently, so not an Urban gap | https://educationdata.urban.org/api/v1/schools/crdc/ap-exams/{year}/race/sex/ |
| CRDC offerings (AP course counts, indicators) | 2023 | 2023-24 | 0 | https://educationdata.urban.org/api/v1/schools/crdc/offerings/2023/ |
| SAIPE school-district poverty | 2024 | 2024 estimates (page dated Feb 2026, files 2026-02-19). No 2025 directory yet | 0 | https://educationdata.urban.org/api/v1/school-districts/saipe/2024/ · https://www.census.gov/data/datasets/2024/demo/saipe/2024-school-districts.html · https://www2.census.gov/programs-surveys/saipe/datasets/2024/2024-school-districts/ |
| College Scorecard (institution) | inst-characteristics 2020, earnings 2018, default 2020, repayment 2016, student-characteristics 2016 | "1996-97 through 2025-26", last updated June 10, 2026 | ~5+ years | https://educationdata.urban.org/api/v1/api-endpoints/ · https://collegescorecard.ed.gov/data/ |

## Portal-wide facts

- **Current version:** 0.27.0, released 9/30/2026. This is the latest entry in the changelog feed at https://educationdata.urban.org/documentation/data/api-changes.json (the docs page renders its "Version history" from that feed).
- **Endpoint catalog with `years_available`:** https://educationdata.urban.org/api/v1/api-endpoints/ (130 endpoints). The FAQ recommends using it to find the latest year: "slicing the last four characters of the years_available field" (https://urbaninstitute.github.io/education-data-faqs/).
- **URL pattern:** `https://educationdata.urban.org/api/v1/{level}/{source}/{topic}/{year}/[{subtopic...}/]?{filter}={value}&...`, where level is `schools`, `school-districts` or `college-university`. Filters go in the query string as `?filter_variable=filter_value`, and you combine them with `&` (https://educationdata.urban.org/documentation/). Comma-separated values also work, e.g. `fips=17,55` (FAQ).
- **Pagination:** "The API limits the number of records returned per page to 10,000 ... you will need to iterate over the pages" (https://urbaninstitute.github.io/education-data-faqs/). Confirmed live: the full `school-districts/ccd/directory/2024/` call returned `count` 19636, 10000 rows, and `next` = `...?page=2`.
- **Rate limits:** No numeric limit is documented on the docs page or in the FAQ. The 10,000-row page ceiling exists "to prevent large data requests from slowing down the API for other users" (FAQ). Live responses carried no rate-limit headers (the headers seen included `cache-control: max-age=31536000` and `cf-cache-status: DYNAMIC`). robots.txt sets `Crawl-delay: 1` and `Disallow: /api/` (https://educationdata.urban.org/robots.txt).
- **Missing years return inconsistent responses:** some return HTTP 200 with `count: 0` (e.g. `schools/ccd/directory/2025/`), and others return HTTP 500 (e.g. `ipeds/fall-enrollment/2025/...`, `crdc/sat-act-participation/2022/...`). Code should treat both as "not available" and check `years_available` first.
- **Bulk CSV:** each endpoint lists files under `https://educationdata.urban.org/csv/{file_dir}/{file_name}`. The listing is at https://educationdata.urban.org/api/v1/api-downloads/ (990 entries) and in the FAQ: "For large data requests, it may be faster to download the full dataset as a CSV file". Examples: `csv/ccd/schools_ccd_directory.csv` (967.4 MB, 1986–2024), `csv/ccd/schools_ccd_enrollment_2024.csv` (887.7 MB), `csv/ipeds/colleges_ipeds_directory.csv` (1980–2025), `csv/crdc/schools_crdc_sat_and_act_participation_2021.csv`, `csv/saipe/districts_saipe.csv` (**labeled 1995–2022**, older than the API).
- **Summary endpoints:** `.../{topic}/summaries?var=...&stat=...&by=...` (https://educationdata.urban.org/documentation/#summary_endpoints; experimental docs at https://github.com/UrbanInstitute/education-data-summary-endpoints).
- **Codebooks:** each endpoint has an `.xls` codebook in the same downloads listing, e.g. `csv/ccd/codebook_schools_ccd_directory.xls`.

### Terms of use and citation

From https://educationdata.urban.org/documentation/ ("Data Policy and Terms of Use" and "Citing these data"):
- "Visitors to this site agree to abide by the Urban Institute's terms of service" (https://www.urban.org/terms-service).
- "All data made available via the Education Data Portal in any form is licensed to you under the Open Data Commons Attribution License (ODC-By) v1.0" (https://opendatacommons.org/licenses/by/1-0/).
- Citation: "please cite both the portal and the dataset. For example: [dataset names], Education Data Portal (Version ), Urban Institute, accessed Month, DD, YYYY, https://educationdata.urban.org/documentation/, made available under the ODC Attribution License." Short form: "[dataset names], via Education Data Portal v. , Urban Institute, under ODC Attribution License." Fill in the version, currently 0.27.0.

### Clients

- **No official Python client.** The docs say the Python examples "directly access endpoint URLs via the urllib library" (https://educationdata.urban.org/documentation/), and the FAQ gives `requests` page-loop examples (https://urbaninstitute.github.io/education-data-faqs/). PyPI has no `educationdata` package (`https://pypi.org/pypi/educationdata/json` → 404). No Python client turned up in the `UrbanInstitute` GitHub org.
- **R:** `educationdata`, https://github.com/UrbanInstitute/education-data-package-r. DESCRIPTION says Version 0.1.5, Date 2025-10-28. It is actively maintained: the latest commit is "Update for Release 27" on 2026-09-24, and it has a `csv = TRUE` option for bulk downloads.
- **Stata:** https://github.com/UrbanInstitute/education-data-package-stata (last push 2026-09-24).
- **MCP server (Python, not a client library):** https://github.com/UrbanInstitute/education-data-mcp, MIT license, created 2026-09-11. Its README says it "Queries the live EDP API. No API key required. Read-only." All its activity so far is from one day, so it's too new to call maintained.
- **Practical answer:** write a thin `httpx` page loop for the API (follow `next`), or read the `/csv/` files straight into polars.

---

## Details by dataset

### CCD: school and district directory, enrollment, free/reduced-price lunch

**Urban**
- Endpoints (from https://educationdata.urban.org/api/v1/api-endpoints/):
  - `schools/ccd/directory/{year}/` (1986–2024)
  - `school-districts/ccd/directory/{year}/` (1986–2024)
  - `schools/ccd/enrollment/{year}/{grade}/[race/|sex/|race/sex/]` (1986–2024)
  - `school-districts/ccd/enrollment/{year}/{grade}/...` (1986–2024)
- Identifiers: `ncessch` (string, 12 digits, e.g. `'110000500456'`), `ncessch_num` (numeric), `leaid` (string, 7 digits, e.g. `'1100005'`), `state_leaid`, `seasch` (live call and varlist).
- FRL lives in the **school directory** endpoint, not a separate table. Fields: `lunch_program`, `free_lunch`, `reduced_price_lunch`, `free_or_reduced_price_lunch` ("The total is only available if both of the details (or the total) were reported"), and `direct_certification` (varlist).
- Live check, Illinois, Urban 2024: of 4,438 schools, 3,468 have a non-negative `free_or_reduced_price_lunch`, and *all* have negative (missing/NA) codes for the separate `free_lunch` and `reduced_price_lunch`. 2023 looks the same. So state reporting differences come through as-is, and FRL completeness varies by state. Expect to use the combined total and the direct-certification counts.
- Lag pattern (changelog https://educationdata.urban.org/documentation/data/api-changes.json): CCD 2022 was added 3/14/2024, 2023 on 9/1/2025, and 2024 on 3/30/2026. That's roughly one CCD year per release cycle.

**NCES**
- File listing API behind https://nces.ed.gov/ccd/files.asp: `https://nces.ed.gov/ccd/datatables/api/File` and `.../api/File/0/0/{schoolYearId}/0/0/0`.
- Latest school and LEA universe files:
  - **2025-26:** preliminary Directory only (version "0a"). Files: `ccd_sch_029_2526_w_0a_050626.zip` and `ccd_lea_029_2526_w_0a_050626.zip`. Release notes: `https://nces.ed.gov/ccd/doc/SY_2025-26_Preliminary_Data_Release_CCD_Nonfiscal_Release_Notes.docx`.
  - **2024-25:** Directory, Membership (052), Staff (059), Lunch Program Eligibility (`ccd_sch_033_2425_l_2a_073025.zip`, v.2a), and School Characteristics (129).
- Access: zipped flat files only. There is also the ELSI table generator (https://nces.ed.gov/ccd/elsi/). I found no NCES CCD JSON API (see Open questions).
- Gap: none for enrollment and FRL. The directory is one preliminary year behind.

### IPEDS: directory, enrollment, institutional characteristics

**Urban**
- `college-university/ipeds/directory/{year}/`: 1980, 1984–2025. Has `unitid` (int) and `opeid` (8-char string, e.g. `'00143400'`). 96 fields in the 2025 sample. The endpoint description says it includes "control and level of institution, highest level and highest degree offered and Carnegie classifications". Changelog for 3/30/2026: "Added 7 new Carnegie Classification 2025 variables".
- `college-university/ipeds/institutional-characteristics/{year}/`: 1980, 1984–2025.
- `college-university/ipeds/fall-enrollment/{year}/{level_of_study}/race/sex/`: 1986–2024.
- `college-university/ipeds/enrollment-headcount/{year}/{level_of_study}/`: 1996–2024. The detailed variant (`enrollment-headcount-detailed`) was added in 0.27.0.
- `college-university/ipeds/enrollment-full-time-equivalent/{year}/{level_of_study}/`: 1997–2024.
- Other IPEDS endpoints lag further (years_available): admissions-requirements to 2022, SFA/net price to 2021, tuition to 2023, grad rates to 2023, outcome measures to 2023.
- Lag pattern: 2023 HD/IC was added 9/1/2025, 2024 HD/IC on 3/30/2026, 2025 HD/IC on 9/30/2026, and 2023–2024 fall enrollment on 6/30/2026. IPEDS endpoints have been updated in every 2026 release (0.25.0, 0.26.0, 0.26.1, 0.27.0).

**NCES**
- Release schedule (https://nces.ed.gov/ipeds/survey-components/data-release-schedule):
  - 2025-26 Fall (IC, C, E12): July 28, 2026 (PD)
  - 2024-25 Fall: September 8, 2026 (FD)
  - 2024-25 Spring (EF, F, HR): January 6, 2026 (PD)
  - 2024-25 Winter: December 9, 2025 (PD)
  - "PD = Provisional Data; FD = Final Data"
- Access databases (https://nces.ed.gov/ipeds/use-the-data/download-access-database): 2024-25 Provisional (March 2026) and 2023-24 Final (March 2026).
- Complete Data Files (CSV zips) at `https://nces.ed.gov/ipeds/datacenter/data/{TABLE}{YEAR}.zip`. Live HEAD checks: `HD2024.zip`, `IC2024.zip`, `EFFY2024.zip` → 200 (Last-Modified 2025-09-21), but `HD2025.zip` and `IC2025.zip` → 404, even though the 2025-26 Fall provisional data are released per the schedule. `https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx` redirected to `login.aspx?gotoReportId=1&fromIpeds=true`. See Open questions.
- Gap: none for the tables we need. Urban's IPEDS 2025 rows probably come from *provisional* data (see Open questions).

### CRDC: SAT/ACT and AP participation

**Urban**
- `schools/crdc/sat-act-participation/{year}/race/sex/` (also `/disability/sex/` and `/lep/sex/`): 2011, 2013, 2015, 2017, 2020, 2021. Field `students_SAT_ACT`: "Includes students who participated, regardless of whether they received valid scores on the tests."
- `schools/crdc/ap-ib-enrollment/{year}/race/sex/`: same years. Fields: `enrl_AP`, `enrl_AP_math`, `enrl_AP_science`, `enrl_AP_other`, `enrl_IB`, and `enrl_gifted_talented`.
- `schools/crdc/ap-exams/{year}/race/sex/`: 2011–2017 only.
- `schools/crdc/offerings/{year}/`: 2011, 2013, 2015, 2017, 2020, 2021, **2023**. Includes `ap_courses_indicator`, `num_courses_ap`, `students_select_ap_indicator`, and `sch_dual_indicator`. Changelog for 9/30/2026: "Updated 2011-2023 CRDC offerings endpoint with new years and new variables".
- Identifiers: `crdc_id`, `ncessch`, `leaid`. In live rows `crdc_id == ncessch`.
- Lag pattern: 2020-21 CRDC endpoints were added 7/30/2024, and 2021-22 on 11/24/2025. The 2023-24 data are only in offerings so far.

**OCR**
- Download list in the site bundle (https://civilrightsdata.ed.gov/data, module `recent-data-files`):
  - "2023-24 Downloadable Data Files" → `https://civilrightsdata.ed.gov/assets/ocr/docs/2023-24-crdc-data.zip` (HTTP 200, 99.6 MB, Last-Modified Mon, 31 Aug 2026)
  - then 2021-22, 2020-21 and 2017-18 zips at the same path pattern
- OCR's site FAQ text (same bundle): "OCR expects to release the 2023-24 CRDC public-use data file by September 2026" and "OCR released the 2021-22 CRDC public-use and restricted-use data files in January 2025."
- The 2023-24 zip has 37 CSVs, including:
  - `SCH/SAT and ACT.csv`: columns `COMBOKEY`, `LEAID`, `SCHID`, `SCH_SATACT_{race}_{M|F|X}`, `TOT_SATACT_{M|F|X}`, `SCH_SATACT_EL_*`, `SCH_SATACT_IDEA_*`
  - `SCH/Advanced Placement.csv`: `SCH_APENR_IND`, `SCH_APCOURSES`, `SCH_APSEL`, `TOT_APENR_*`, AP math/science/comp-sci/other enrollment
  - No AP exam columns
  - **No chronic absenteeism file**
- Join key: `COMBOKEY` (LEAID + SCHID) lines up with the 12-digit NCES school ID. **UNVERIFIED** for all rows: check the match rate after loading.
- Gap: one collection (2023-24) for SAT/ACT and AP enrollment, so pull those from OCR.

### Census SAIPE: school-district poverty

**Urban**
- `school-districts/saipe/{year}/`: 1995, 1997, 1999–2024.
- Fields: `leaid`, `district_id`, `district_name`, `est_population_total`, `est_population_5_17`, `est_population_5_17_poverty`, `est_population_5_17_poverty_pct`, `est_population_5_17_pct`.
- The description says it covers "the geographic district ... including those who go to charter or private schools".
- Lag pattern: 2022 was added 9/1/2025 and 2024 on 3/30/2026. The 2024 data reached Urban about 6 weeks after the Census files (dated 2026-02-19). The Census release date for the 2022 estimates is **UNVERIFIED**, so I can't measure the earlier lag.

**Census**
- 2024 estimates page (https://www.census.gov/data/datasets/2024/demo/saipe/2024-school-districts.html) is dated "February 2026" and says:
  - "The school districts for which we have estimates were identified in the 2025 school district mapping survey, which asked about all school districts as of January 1, 2025 and used school district boundaries for the 2024-2025 school year."
  - "The 2024 estimates are consistent with the population controls and income concepts used in the 2024 American Community Survey single-year estimates."
- Files are in https://www2.census.gov/programs-surveys/saipe/datasets/2024/2024-school-districts/ (`ussd24.csv`, `ussd24.txt`, `ussd24.xls`, per-state `sd24-xx.txt`, dated 2026-02-19). There is no `datasets/2025/` directory (404).
- Census API `https://api.census.gov/data/timeseries/poverty/saipe/schdist`: an unkeyed request redirected to a "Missing Key" page. Variables include `LEAID`, `SAEPOV5_17RV_PT`, `SAEPOP5_17V_PT`, `YEAR`, and `time`.

**Verified match:**
- Urban 2024 DC row: `est_population_total` 702250, `est_population_5_17` 90393, `est_population_5_17_poverty` 22266.
- Census `sd24-dc.txt`: `11 00030 District of Columbia Public Schools 702250 90393 22266`. The values are identical.
- Row counts are also identical: Urban 2024 `count` = 13,132 and `ussd24.csv` has 13,132 data rows.

**Year note:** Urban's `year` 2024 equals Census "2024 estimates" (income year 2024, 2024-25 boundaries). Urban's generic varlist calls this "Academic year (fall semester)". Join SAIPE year Y to CCD year Y (both use 2024-25 boundaries and rosters). Urban's `leaid` is built as state FIPS + Census `district_id`, e.g. `1100030` = `11` + `00030` (verified on the DC row).

### College Scorecard

**Urban** (years_available from https://educationdata.urban.org/api/v1/api-endpoints/):
- `college-university/scorecard/institutional-characteristics/{year}/`: 1996–2020. The description says "most of the information contained in this endpoint can be found in 2016". Has `unitid`, `opeid`, and `opeid6`.
- `scorecard/earnings/{year}/`: 2003–2014, 2018.
- `scorecard/default/{year}/`: 1996–2020.
- `scorecard/repayment/{year}/`: 2007–2016.
- `scorecard/student-characteristics/{year}/aid-applicants/` and `/home-neighborhood/`: 1997–2016.
- No Scorecard rows appear in any 2024–2026 changelog entry.

**Publisher** (https://collegescorecard.ed.gov/data/):
- "This data was last updated June 10, 2026."
- All Data Files zip (`https://ed-public-download.scorecard.network/downloads/College_Scorecard_Raw_Data_06102026.zip`, 470 MB) includes:
  - "Institution-level data files for 1996-97 through 2025-26"
  - field-of-study files
  - "Crosswalk files for 2000-01 through 2022-23 that link the Department's OPEID with an IPEDS UNITID"
- API (https://collegescorecard.ed.gov/data/api-documentation/):
  - Base URL `https://api.data.gov/ed/collegescorecard/v1/schools`
  - "you must have an API key" (`api_key` parameter)
  - "The default rate limit is 1,000 requests per IP address per hour"
  - `per_page` "default is 20, maximum is 100"
  - `latest.*` vs year-prefixed fields (e.g. `2018.earnings`)
- Gap: about 5+ years. Don't use Urban for Scorecard.

## What we'd want that the portal lacks

- CRDC 2023-24 SAT/ACT and AP enrollment (only offerings 2023 is loaded).
- CCD 2025-26 preliminary directory.
- Current College Scorecard, including the OPEID↔UNITID crosswalks through 2022-23 (Urban's IPEDS directory does carry `opeid`).
- AP exam taking and passing after 2017-18. OCR's 2023-24 file doesn't collect it either, so this needs another source.
- A fresh SAIPE bulk CSV: `csv/saipe/districts_saipe.csv` is labeled 1995–2022, so use the API for 2023–2024.
- Not in scope, but related: Urban also has MEPS school-level poverty estimates (`schools/meps/{year}/`, 2009–2022), which could add school-level child-poverty context.

## Open questions / UNVERIFIED

1. **Urban's CRDC year labels 2022 (chronic absenteeism) and 2023 (offerings).** By the documented convention, `2023` = 2023-24, which matches OCR's 2023-24 file. But `chronic-absenteeism` lists `2022`, there was no 2022-23 CRDC collection, and the 2023-24 OCR zip has no chronic-absenteeism file. What Urban's `2022` represents is **UNVERIFIED**. We don't depend on it.
2. **IPEDS provisional vs final.** Which release Urban loaded for IPEDS 2025 HD/IC and 2024 EF is **UNVERIFIED**. Only provisional data exist for 2025-26 Fall and 2024-25 Spring. Re-pull once NCES posts final data.
3. **IPEDS 12-month headcount year mapping.** Whether Urban `enrollment-headcount` `2024` comes from the 2024-25 or 2025-26 E12 collection is **UNVERIFIED**.
4. **IPEDS complete-file URLs for 2025.** `HD2025.zip` and `IC2025.zip` return 404 at `nces.ed.gov/ipeds/datacenter/data/`, and the Data Center files page redirected to a login URL. Whether NCES has moved or renamed the 2025-26 provisional complete files is **UNVERIFIED**.
5. **CCD version Urban loaded for 2024.** NCES lists the 2024-25 school file as v.2a. Whether Urban's 2024 school directory reflects v.1a or v.2a is **UNVERIFIED**.
6. **NCES CCD API.** I found no first-party JSON API for CCD on nces.ed.gov, only zip files and ELSI. The `datatables/api/File` endpoint is the file-listing backend for files.asp, not a data API.
7. **Numeric rate limit for the Urban API.** Not documented anywhere I checked. The only limits are the 10,000-row page ceiling and robots `Crawl-delay: 1`.
8. **CRDC `COMBOKEY` ↔ `ncessch` match rate** for 2023-24: not measured.
9. **NCES CCD 2024-25 release date.** The release-date table on files.asp is inside an HTML comment, so I didn't use it. Exact NCES release dates (and so Urban's exact lag in months for CCD) are **UNVERIFIED**.
10. **Summary endpoint semantics.** A live summary call worked: `schools/ccd/enrollment/summaries?var=enrollment&stat=sum&by=fips&fips=11&year=2024` → `{"year":2024,"fips":11,"enrollment":94038}`. Whether that sums only total rows or also subgroup rows is **UNVERIFIED**. Don't rely on it without checking.

---

## Appendix: live calls (2026-10-14)

Base: `https://educationdata.urban.org/api/v1/`. Responses are trimmed to `count`, `next` and the first few fields of the first row.

```
GET schools/ccd/directory/2024/?fips=11                       -> 200 count 247
  {'year': 2024, 'ncessch': '110000500456', 'school_id': '1100456', 'school_name': 'Cesar Chavez Public Charter Schools for Public Policy', 'leaid': '1100005', 'lea_name': 'Cesar Chavez PCS for Public Policy', 'state_leaid': 'DC-109', ...}
GET schools/ccd/directory/2025/?fips=11                       -> 200 count 0
GET school-districts/ccd/directory/2024/?fips=11              -> 200 count 72
  {'year': 2024, 'leaid': '1100004', 'lea_name': 'Carlos Rosario International PCS', 'fips': 11, ...}
GET school-districts/ccd/directory/2025/?fips=11              -> 200 count 0
GET school-districts/ccd/directory/2024/                      -> 200 count 19636, 10000 rows, next .../2024/?page=2
GET schools/ccd/enrollment/2024/grade-9/?fips=11              -> 200 count 48
  {'year': 2024, 'ncessch': '110000500456', 'grade': 9, 'race': 99, 'sex': 99, 'enrollment': 85, 'fips': 11, 'leaid': '1100005'}
GET schools/ccd/directory/2024/?fips=17                       -> 200 count 4438
  free_or_reduced_price_lunch >=0: 3468; free_lunch/reduced_price_lunch: all negative codes
GET school-districts/saipe/2024/?fips=11                      -> 200 count 1
  {'district_id': '30', 'district_name': 'District of Columbia Public Schools', 'est_population_total': 702250.0, 'est_population_5_17': 90393.0, 'est_population_5_17_poverty': 22266.0, 'year': 2024, 'leaid': '1100030', 'fips': '11', 'est_population_5_17_poverty_pct': 0.246324, ...}
GET school-districts/saipe/2025/?fips=11                      -> 200 count 0
GET school-districts/saipe/2024/                              -> 200 count 13132
GET college-university/ipeds/directory/2025/?fips=11          -> 200 count 23
  {'year': 2025, 'unitid': 131159, 'inst_name': 'American University', ..., 'opeid': '00143400', 'title_iv_indicator': 1}
GET college-university/ipeds/directory/2026/?fips=11          -> 200 count 0
GET college-university/ipeds/institutional-characteristics/2025/?fips=11 -> 200 count 22
GET college-university/ipeds/fall-enrollment/2024/undergraduate/race/sex/?fips=11 -> 200 count 9344
  {'unitid': 131159, 'year': 2024, 'ftpt': 1, 'level_of_study': 1, 'degree_seeking': 99, 'class_level': 99, 'sex': 1, 'race': 1, 'enrollment_fall': 1538}
GET college-university/ipeds/fall-enrollment/2025/undergraduate/race/sex/?fips=11 -> 500
GET college-university/ipeds/enrollment-headcount/2024/undergraduate/?fips=11    -> 200 count 496
GET schools/crdc/sat-act-participation/2021/race/sex/?fips=11 -> 200 count 5760
  {'crdc_id': '110000500456', 'ncessch': '110000500456', 'year': 2021, 'leaid': '1100005', 'race': 99, 'sex': 1, 'students_SAT_ACT': 19}
GET schools/crdc/sat-act-participation/2022/race/sex/?fips=11 -> 500
GET schools/crdc/ap-ib-enrollment/2021/race/sex/?fips=11      -> 200 count 5760
  {'crdc_id': '110000500456', 'year': 2021, 'ncessch': '110000500456', 'race': 1, 'sex': 1, 'enrl_IB': -2, 'enrl_AP': -2, ...}
GET schools/crdc/ap-exams/2021/race/sex/?fips=11              -> 500   (endpoint ends 2017)
GET schools/crdc/offerings/2023/?fips=11                      -> 200 count 233
  {'crdc_id': '110000500456', 'year': 2023, 'ncessch': '110000500456', 'num_classes_algebra1': '7.000', ...}
GET schools/crdc/directory/2023/?fips=11                      -> 200 count 0
GET college-university/scorecard/institutional-characteristics/2020/?fips=11 -> 200 count 26
  {'unitid': 131159, 'year': 2020, 'opeid': '00143400', 'opeid6': 1434, ...}
GET college-university/scorecard/institutional-characteristics/2021/?fips=11 -> 200 count 0
GET college-university/scorecard/earnings/2018/?fips=11       -> 200 count 52
GET schools/ccd/enrollment/summaries?var=enrollment&stat=sum&by=fips&fips=11&year=2024
  -> {"count":1,"next":null,"previous":null,"results":[{"year":2024,"fips":11,"enrollment":94038}]}
```

Publisher checks:

```
GET https://nces.ed.gov/ccd/datatables/api/File  -> School/LEA universe latest "2025 - 2026" (versionName None; files *_2526_w_0a_050626.zip), then "2024 - 2025"
HEAD https://civilrightsdata.ed.gov/assets/ocr/docs/2023-24-crdc-data.zip -> 200, content-length 99570187, last-modified Mon, 31 Aug 2026 19:12:52 GMT
GET https://www2.census.gov/programs-surveys/saipe/datasets/2024/2024-school-districts/sd24-dc.txt
  -> "11 00030 District of Columbia Public Schools  702250  90393  22266 sd24-dc.txt 17FEB2026"
GET https://www2.census.gov/programs-surveys/saipe/datasets/2025/ -> 404
HEAD https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip -> 200 (Last-Modified Sun, 21 Sep 2025); HD2025.zip -> 404
```
