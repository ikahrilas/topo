# Source terms, automated-access rules, and update cadence

Researched 2026-10-14. All robots.txt files were fetched directly that day with `curl` (and, for ed.gov, a real browser; see Source 2). Quotes are verbatim from the cited URL. "not stated" means the source says nothing on the topic. "UNVERIFIED" means I could not confirm it from a primary source.

## Summary

| Source | Access method | ToS / policy URL | Rate limit | Attribution | Cadence | Verdict |
|---|---|---|---|---|---|---|
| USAspending.gov | REST API `api.usaspending.gov/api/v2/`, monthly Award Data Archive zips at `files.usaspending.gov/award_data_archive/` | No ToS page found. Licensing: https://www.usaspending.gov/about (Licensing section). D&B limitation: https://www.usaspending.gov/db-info | Not stated (no key; no rate-limit headers seen). Website downloads capped at 500,000 rows (`MAX_DOWNLOAD_LIMIT`) | Suggested citation (see below). D&B Open Data fields need written attribution to D&B | Site data refreshes nightly. Archive files are monthly (latest `20261006`). API `last_updated` = 10/14/2026 | **API/bulk OK** (don't scrape the website UI) |
| ED TRIO / GEAR UP grantee lists (ed.gov) | Static PDF (FY2024–25 TRIO), XLSX (FY2021–23 TRIO; FY2022 GEAR UP), HTML tables (GEAR UP FY2017–25) under `www.ed.gov/media/document/` | https://www.ed.gov/about/ed-overview/required-notices/website-policies/copyright-status-notice | Not stated. Azure WAF returns 403 or a CAPTCHA to non-browser clients | Not stated (content is public domain) | Once a year per competition/continuation cycle. FY2025 TRIO PDFs last-modified 2026-01-09 | **Avoid automated access** (download by hand, then cache) |
| Urban Institute Education Data Portal | JSON API `educationdata.urban.org/api/v1/...`, bulk CSV `educationdata.urban.org/csv/...` | https://educationdata.urban.org/documentation/#terms (data: ODC-By 1.0); https://www.urban.org/terms-service | 10,000 records per page. No numeric rate limit stated. robots `Crawl-delay: 1` | Required under ODC-By. Cite both the portal and the dataset (see below) | Versioned releases several times a year. Latest v0.27.0 on 9/30/2026 | **API/bulk OK** (prefer `/csv/`, since robots.txt disallows `/api/`) |
| Census SAIPE school districts + Census Data API | API `api.census.gov/data/timeseries/poverty/saipe/schdist`; flat files at `www2.census.gov/programs-surveys/saipe/datasets/` | https://www.census.gov/data/developers/about/terms-of-service.html | Key required on every query (confirmed live). 50 variables per query. No numeric call limit published | Required notice: "This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau." | Annual. 2024 estimates released Jan 2026 (files dated 2026-02-19). No 2025 data yet | **API/bulk OK** (API with key; `www2` robots.txt is ambiguous, see below) |

---

## 1. USAspending.gov (API and bulk downloads)

**Terms of use**
- I found no ToS or "terms of use" page. The site's static sitemap (https://www.usaspending.gov/static.xml) lists only `/about`, `/about/accessibility`, `/about/privacy`, `/about/foia`, `/db-info`, `/download_center`, and `/data-dictionary`. The API landing page (https://api.usaspending.gov/) and docs index (https://api.usaspending.gov/docs/) say nothing about terms, keys, or rate limits.
- Licensing section of https://www.usaspending.gov/about. The site is a JS app, so I read the text from its source, `src/js/components/about/Licensing.jsx` in https://github.com/fedspendingtransparency/usaspending-website (master, commit d550b3e, 2026-10-14). It says: "The data on this site is available to copy, adapt, redistribute, or otherwise use for non-commercial or for commercial purposes, subject to the Limitation on Permissible Use of Dun & Bradstreet, Inc. Data".
- D&B limitation at https://www.usaspending.gov/db-info (source: `src/js/components/about/DBInfo.jsx`, same commit):
  - "By using this website you agree that you shall not use D&B Open Data without giving written attribution to the source of such data (i.e., D&B) and shall not access, use or disseminate D&B Open Data in bulk"
  - "Systematic access (electronic harvesting) or extraction of content from the website, including the use of "bots" or "spiders", is prohibited."
  - "D&B Open Data" is defined there as recipient Business Name, Street Address, City, State/Province name/code/abbreviation, Country, County Code, and ZIP. That is, recipient name and address fields.

**robots.txt**
- https://www.usaspending.gov/robots.txt (HTTP 200):
  ```
  User-agent: *
  Disallow: /*.php*
  Disallow: /*?*
  ```
  Website URLs with query strings (for example `/search/?hash=...`) are disallowed. Python's `urllib.robotparser` agrees: `/download_center/award_data_archive` is allowed and `/search/?hash=abc` is disallowed.
- https://api.usaspending.gov/robots.txt returns HTTP 404, so the API host has no robots.txt.
- https://files.usaspending.gov/robots.txt returns HTTP 404, so the bulk file host has no robots.txt.

**Rate limits / keys**
- Rate limit: not stated. No key or authentication is required; `GET https://api.usaspending.gov/api/v2/references/toptier_agencies/` returned 200 with no rate-limit or Retry-After headers.
- Page size: for `/api/v2/search/spending_by_award/`, "If no limit is specified, the limit is set to 10." (https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_award.md).
- Custom downloads are capped at `MAX_DOWNLOAD_LIMIT = 500000` rows (`usaspending_api/settings.py` in https://github.com/fedspendingtransparency/usaspending-api).

**Attribution**
- Suggested general citation (Licensing section, https://www.usaspending.gov/about): "USAspending.gov, U.S. Department of Treasury, Bureau of the Fiscal Service, https://www.usaspending.gov. Accessed [Day] [Month]. [Year]."
- If we republish D&B Open Data fields (recipient name and address), we must give written attribution to D&B (https://www.usaspending.gov/db-info).

**Update cadence**
- "The data on USAspending.gov are updated every day after the nightly data pipeline runs." (source `src/js/components/interactiveDataSources/scrollerSections/Frequency.jsx`, rendered on the site's data-sources pages).
- Financial assistance (FABS, which covers ED grants): agencies must submit "within two weeks of the award transaction". In the same file's example, data submitted Sept 22 is published Sept 23.
- Award Data Archive: "Full files - data for the fiscal year up until the date the file was prepared" and "Delta files - only new, modified, and deleted data since the date the last month's files were generated" (`src/js/components/bulkDownload/archive/AwardDataArchiveContent.jsx`). This makes the archive monthly.
- Most recent update: `POST /api/v2/bulk_download/list_monthly_files/` returned `FY2026_All_Assistance_Full_20261006.zip` with `updated_date` 2026-10-06. `GET /api/v2/awards/last_updated/` returned `{"last_updated":"10/14/2026"}`.

**Verdict: API/bulk OK.** Use the API and the `files.usaspending.gov` archive zips. Neither host publishes robots.txt or a rate limit, so throttle politely. Do not crawl `www.usaspending.gov` UI pages: robots.txt blocks query URLs, and the D&B notice prohibits bots on "the website". It is unclear whether that bot language covers the API (see Open questions).

---

## 2. U.S. Department of Education: TRIO and GEAR UP grantee lists (ed.gov)

**Access constraint found:** every non-browser request to `www.ed.gov` and `www2.ed.gov` was blocked. That covered `curl` with three different User-Agents and the WebFetch tool. The responses were HTTP 403 "The request is blocked." or an Azure WAF page with `window.challengeType = "captcha"`. I did not try to solve or bypass the challenge. Everything below was read in a normal Chrome browser session, which passed the challenge without interaction.

**Current URLs and formats (verified 2026-10-14)**

TRIO hub: https://www.ed.gov/grants-and-programs/grants-higher-education/federal-trio-programs. Every program page shows "Page Last Reviewed: August 17, 2026", and each has an "Awards" accordion with per-year "Projects Funded" files:

| Program | Page | FY2025 (2025-26) | FY2024 | Older on page |
|---|---|---|---|---|
| Upward Bound 84.047A | https://www.ed.gov/grants-and-programs/grants-higher-education/federal-trio-programs/upward-bound-program-84047a | PDF `/media/document/ubfinal2025-113011.pdf` ("Total Projects: 1,000") | PDF `/media/document/fy-2024-ub-awards-109467.pdf` ("Total Projects: 1,026") | none found on page |
| UB Math-Science 84.047M | .../upward-bound-math-and-science-program-84047m | PDF `ubmsfinal2025-113012.pdf` | PDF `fy-2024-ubms-awards-109468.pdf` | XLSX `ubms-final2023xlsx-76271.xlsx`, `ubmsfinal2022xlsx-76282.xlsx`, `ubmsfinal2021xlsx-76281.xlsx` |
| Veterans UB 84.047V | .../veterans-upward-bound-program-84047v | PDF `vubfinal2025-113013.pdf` | PDF `fy-2024-vub-awards-109469.pdf` | XLSX 2023, 2022, 2021 |
| Talent Search 84.044 | .../talent-search-program-84044 | PDF `tsfinal2025-113009.pdf` | PDF `fy-2024-ts-awards-109466.pdf` | XLSX `ts-final2023xlsx-76712.xlsx` |
| Student Support Services 84.042A | .../student-support-services-program-84042a | PDF `sssfinal2025-113008.pdf` | PDF `fy-2024-sss-awards-109464.pdf` | XLSX `sss-final2023xlsx-76509.xlsx` |
| Educational Opportunity Centers 84.066A | .../educational-opportunity-centers-program-84066a | PDF `eocfinal2025-113006.pdf` | PDF `fy-2024-eoc-awards-109462.pdf` | XLSX `eoc-final2023xlsx-76158.xlsx` |
| McNair 84.217A | .../ronald-e-mcnair-postbaccalaureate-achievement-program-84217a | PDF `mcnfinal2025-113007.pdf` | PDF `fy-2024-mcnair-awards-109463.pdf` | XLSX `mcn-final2023xlsx-76337.xlsx` |

All files are under `https://www.ed.gov/media/document/`. Same-origin HEAD responses in the browser:
- `ubfinal2025-113011.pdf`: application/pdf, 116,672 bytes, Last-Modified Fri, 09 Jan 2026.
- `tsfinal2025-113009.pdf`: Last-Modified 09 Jan 2026.
- `fy-2024-ub-awards-109467.pdf`: Last-Modified 22 Jan 2025.
- `ubms-final2023xlsx-76271.xlsx`: XLSX, Last-Modified 16 Jan 2024.

The Upward Bound page also links grantee-level GPRA performance files: `ububms-2022-23-grantee-level-gpra-tables-113044.xlsx` plus a 2023-24 set.

GEAR UP:
- Partnership 84.334A awards: https://www.ed.gov/grants-and-programs/grants-special-populations/grants-economically-disadvantaged-students/gaining-early-awareness-and-readiness-undergraduate-programs-gear/grant-awards ("Page Last Reviewed: July 27, 2026").
  - Lists come as **HTML tables** (8 tables, FY2017–FY2025) with columns "New Grantees | State | Year 1 Proposed Students Served | Year 1 Budget". The tables cover new awards only.
  - Abstracts are PDFs, plus one XLSX: `fy-2022-gear-partnerships-combined-awards-63882.xlsx` (new and continuation, Last-Modified 12 Oct 2022).
  - The "FY 2024 GEAR UP: Partnership Abstracts" link points to the same file as FY2025 (`fy-2025-gear-partnership-abstracts-108210.pdf`, Last-Modified 22 Oct 2024). This looks like a page error.
- State 84.334S awards: https://www.ed.gov/grants-and-programs/grants-special-populations/grants-economically-disadvantaged-students/gaining-early-awareness-and-readiness-undergraduate-programsgear-state-84334s/grant ("Page Last Reviewed: July 27, 2026"). HTML tables FY2017–FY2025 with the same columns, plus PDF abstracts (for example `fy-2025-gear-states-abstracts-108212.pdf`).

**Restructuring and archive status (2024–2025 move to the new ed.gov)**

Each legacy URL below was opened in the browser:
- `https://www2.ed.gov/programs/trioupbound/index.html` redirects to the new Upward Bound 84.047A page.
- `https://www2.ed.gov/programs/gearup/awards.html` redirects to the GEAR UP Partnership program page, not to the grant-awards subpage.
- `https://www2.ed.gov/about/offices/list/ope/trio/grantees.html` (old TRIO grantee lists) redirects to `https://www.ed.gov/about/offices/list/ope/trio/grantees.html`, which is "Page not found".
- `https://www2.ed.gov/programs/trioupbound/awards.html` redirects to the same path on www.ed.gov, which is "Page not found".
- Search results still list old `www2.ed.gov/programs/gearup/gu-fy1999-...` pages. The same paths on www.ed.gov return 404, and I did not get a direct www2 result for them.

The new pages carry FY2021–FY2025 for most TRIO programs (only FY2024–2025 for Upward Bound) and FY2017–FY2025 for GEAR UP. I found no archive of earlier TRIO grantee lists on ed.gov (UNVERIFIED whether one exists).

**Terms of use**
- Copyright Status Notice (https://www.ed.gov/about/ed-overview/required-notices/website-policies/copyright-status-notice, "Page Last Reviewed: February 25, 2026"): "Unless specifically stated otherwise, all information on the U.S. Department of Education's (ED's) website at www.ed.gov is in the public domain, and may be reproduced, published or otherwise used without ED's permission."
- Site Security notice (https://www.ed.gov/about/ed-overview/required-notices/site-security-intrusion-detection): "If you use this system, you should understand that all activities may be monitored and recorded."
- Automated access or scraping: not stated in any policy I found (index: https://www.ed.gov/about/ed-overview/required-notices/website-policies). In practice it is blocked by the WAF bot challenge described above.

**robots.txt**
- `https://www.ed.gov/robots.txt` from curl: HTTP 403 (WAF block or CAPTCHA page).
- The same URL in a browser redirects to `https://www.ed.gov/sites/ed/files/robots.txt`, which returns **404 Not Found**. So no robots.txt is effectively published.
- `https://www2.ed.gov/robots.txt` from curl: 403 WAF CAPTCHA page.

**Rate limits:** not stated. **Attribution:** not stated (public domain).

**Update cadence:** not stated. In practice the lists are posted once per fiscal-year award cycle. The FY2025 TRIO PDFs were last modified 2026-01-09, and the GEAR UP award pages were last reviewed 2026-07-27. No FY2026 lists were posted as of 2026-10-14.

**Verdict: avoid automated access.** The host serves a CAPTCHA/bot challenge to scripted clients, and getting past it would mean bypassing bot detection. Download the roughly 20 files by hand once per award cycle, commit or cache them with checksums, and have the pipeline read the local copies. For ongoing award amounts, use USAspending for ED assistance listings 84.042/84.044/84.047/84.066/84.217/84.334 instead (this cross-walk is not verified here).

---

## 3. Urban Institute Education Data Portal (educationdata.urban.org)

**Terms of use** (https://educationdata.urban.org/documentation/, section "Data Policy and Terms of Use")
- "Visitors to this site agree to abide by the Urban Institute's terms of service" (https://www.urban.org/terms-service, "Last Updated: 11/01/2020").
- "All data made available via the Education Data Portal in any form is licensed to you under the Open Data Commons Attribution License (ODC-By) v1.0" (https://opendatacommons.org/licenses/by/1-0/).
- "The content is provided as is, without warranty of any kind, express or implied."
- The general Urban ToS restricts copying "Content" beyond personal use (§3.4), but the portal page explicitly licenses portal data under ODC-By. Section 3.3 also says "Unless otherwise marked or indicated", so the ODC-By marking controls for portal data. My reading; not legal advice.
- Scraping: the Urban ToS forbids only "the use of spiders, robots, and other technologies to collect email addresses from this site". General scraping is not stated.

**robots.txt** (https://educationdata.urban.org/robots.txt, HTTP 200)
```
User-agent: *
Crawl-delay: 1
Allow: /
Disallow: /api/
```
- `/api/v1/...` is **disallowed** for generic agents.
- `/csv/...` is allowed with a 1-second crawl delay (confirmed with `urllib.robotparser`).
- This conflicts with the documentation, which tells users to call the API from "Stata, R, Python, and JavaScript".

**Rate limits**
- No numeric rate limit is stated.
- FAQ (https://urbaninstitute.github.io/education-data-faqs/): "The API limits the number of records returned per page to 10,000. This ceiling prevents large data requests from slowing down the API for other users." The same FAQ says "For large data requests, it may be faster to download the full dataset as a CSV file".
- No key required.

**Attribution** (required by ODC-By; wording from https://educationdata.urban.org/documentation/#citing_data)
- "[dataset names], Education Data Portal (Version ), Urban Institute, accessed Month, DD, YYYY, https://educationdata.urban.org/documentation/, made available under the ODC Attribution License."
- Short form for constrained spaces: "[dataset names], via Education Data Portal v. , Urban Institute, under ODC Attribution License."

**Update cadence**
- Not stated as a schedule. The "Updates timeline" section renders empty in static HTML.
- The version history (https://educationdata.urban.org/documentation/data/api-changes.json, which feeds the `#versions` section) shows releases on 2025-09-01 (0.23.0), 2025-11-24 (0.24.0/0.24.1), 2026-03-30 (0.25.0, "Added 2024 SAIPE district endpoints"), 2026-06-30 (0.26.0), 2026-08-05 (0.26.1), and **2026-09-30 (0.27.0, latest)**.
- The bulk SAIPE CSV `https://educationdata.urban.org/csv/saipe/districts_saipe.csv` returned HTTP 200, 32.8 MB, Last-Modified Wed, 01 Apr 2026. Its download label still reads "1995–2022" (`data/api-downloads.json`), while the API returns 2024 rows. The label looks stale.

**Verdict: API/bulk OK.** The data is ODC-By, there is a documented public API, and there are bulk CSVs. Prefer `/csv/` files with at least 1 s between requests and conditional GETs on ETag/Last-Modified, because robots.txt disallows `/api/`. Record the portal version (for example 0.27.0) in the cache metadata for the citation.

---

## 4. Census SAIPE school district estimates + Census Data API

**Terms of use** (https://www.census.gov/data/developers/about/terms-of-service.html, "Page Last Revised - April 14, 2026")
- "You may use the Census Bureau API to develop a service or service to search, display, analyze, retrieve, view and otherwise "get" information from Census Bureau data."
- "Your use of the API may be subject to certain limitations on access, calls, or use ... If the Census Bureau reasonably believes that you have attempted to exceed or circumvent these limits, your ability to use the API may be temporarily or permanently blocked."
- Users may not use the data "to identify any individual person, household, business or other entity". This is low risk for district-level aggregates.
- Caching or storing responses: not stated.
- The API dataset metadata lists `"license": "https://creativecommons.org/publicdomain/zero/1.0/"` (https://api.census.gov/data/timeseries/poverty/saipe/schdist.json).

**robots.txt**
- https://www.census.gov/robots.txt (HTTP 200). The generic group that applies to us:
  ```
  User-agent: *
  Disallow: /search-results.html
  ```
  SAIPE landing and dataset pages under `/programs-surveys/saipe/` and `/data/datasets/` are allowed.
- https://www2.census.gov/robots.txt (HTTP 200, where the flat files live) begins:
  ```
  User-agent: *

  User-agent: RavenCrawler
  Disallow: /
  ```
  This is ambiguous. If the blank line ends the `*` group, generic bots have no rules. If the two `User-agent` lines form one group, as Python's `urllib.robotparser` reads it, then `*` is `Disallow: /`. `robotparser` returned `can_fetch = False` for `.../saipe/datasets/2024/2024-school-districts/ussd24.csv`. Named crawlers get `Crawl-delay: 30`.
- https://api.census.gov/robots.txt returned an F5-style "Request Rejected" page (HTTP 200 body, not a robots file) with two different User-Agents. UNVERIFIED; effectively none published.

**Rate limits / keys**
- Query Limits page (https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html, "Page Last Revised - May 14, 2026"): "You can include up to 50 variables in a single API query. An API key must be used with all data queries made to the Census Data API."
- Confirmed live: a keyless query to `/data/timeseries/poverty/saipe/schdist?get=...` returned `302` with header `X-DataWebAPI-KeyError: 1` and redirected to https://api.census.gov/data/missing_key.html. That page says "A valid key must be included with each data API request." Metadata endpoints (`schdist.json`, `variables.json`) still work without a key.
- Key signup: https://api.census.gov/data/key_signup.html (requires agreeing to the ToS). The user should request the key; I did not.
- Numeric daily or per-IP limit: not stated.

**Attribution**
- API ToS: "All services, which utilize or access the API, should display the following notice prominently within the application: "This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau.""
- Citation guidance (https://www.census.gov/about/policies/citation.html, revised February 24, 2026): "Use the suggested citation if one is provided". It also says users who create their own estimates "should cite the Census Bureau as the source of the original data only." Components for data: Author, Title, Table or File Name, Persistent Identifiers, Vintage, URL, Date Accessed.

**Update cadence**
- "provides annual estimates of income and poverty statistics for all school districts, counties, and states" (https://www.census.gov/programs-surveys/saipe/about.html).
- Most recent: 2024 estimates. The 2024 highlights report says they were released "in January 2026" (listed on https://www.census.gov/programs-surveys/saipe.html). Earlier vintages came out in December 2023 and December 2024.
- The 2024 school-district page is https://www.census.gov/data/datasets/2024/demo/saipe/2024-school-districts.html ("Page Last Revised - February 19, 2026"). Its files in https://www2.census.gov/programs-surveys/saipe/datasets/2024/2024-school-districts/ are `ussd24.txt`, `ussd24.xls`, `ussd24.csv`, and `sd24-XX.txt` per state, all timestamped 2026-02-19 16:30.
- `/saipe/datasets/2025/` returns 404, so no 2025 vintage has been released.
- The API metadata shows `"temporal": "1995/2024"` (with a stale `"modified": "2019-12-02"`).

**Verdict: API/bulk OK.** Use the Census Data API with a free key and show the required notice. For flat files, `www2.census.gov` robots.txt is ambiguous. Either fetch the roughly 4 national files by hand once a year, or treat it as allowed with a 30 s delay only after confirming with Census (see Open questions).

---

## Open questions / UNVERIFIED

1. **USAspending "no bots" scope.** The `/db-info` line ("Systematic access ... including the use of "bots" or "spiders", is prohibited") sits inside the D&B data-use limitation and says "from the website". Whether it covers `api.usaspending.gov` and `files.usaspending.gov` is not stated. The API is published for programmatic use and has no robots.txt. Worth confirming with USAspending.Help@fiscal.treasury.gov (address taken from the files.usaspending.gov error page).
2. **USAspending rate limits**: not stated anywhere I found. UNVERIFIED whether undocumented throttling exists.
3. **ed.gov WAF policy**: the bot challenge is observed behaviour, not written policy. No robots.txt (404) and no written scraping rule were found. UNVERIFIED whether ED offers a sanctioned machine-readable feed for TRIO/GEAR UP award lists.
4. **Pre-FY2021 TRIO grantee lists**: the old `www2.ed.gov/about/offices/list/ope/trio/grantees.html` now ends at a 404. UNVERIFIED whether older lists were archived anywhere on ed.gov. The Internet Archive or a FOIA request may be the only routes.
5. **GEAR UP FY2024 abstracts link** points to the FY2025 file (`fy-2025-gear-partnership-abstracts-108210.pdf`, Last-Modified 2024-10-22). The file may actually be FY2024 content. UNVERIFIED.
6. **Urban `/api/` robots disallow vs. documented API.** Unclear whether Urban intends robots.txt to cover programmatic API clients. Ask educationdata@urban.org, or default to `/csv/`.
7. **Urban SAIPE CSV label** says 1995–2022, but the file was modified 2026-04-01 and the API has 2024. UNVERIFIED which years the CSV contains (I did not download the 33 MB file).
8. **www2.census.gov robots.txt** grouping is ambiguous (see Source 4). UNVERIFIED which reading Census intends.
9. **api.census.gov robots.txt**: rejected by the server, so UNVERIFIED.
10. **Census API numeric limits**: not stated. The ToS only reserves the right to limit.
11. **SAIPE 2025 release date**: not posted as of 2026-10-14. Past releases were December (2022, 2023 vintages) and January 2026 (2024 vintage). The next date is UNVERIFIED.
