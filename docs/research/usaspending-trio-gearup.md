# Pulling TRIO and GEAR UP awards from USAspending.gov

Researched 2026-10-14. All live calls were made that day against `https://api.usaspending.gov` with no API key. Organization-level data only.

## Summary

- **Listings.** Filter on these Assistance Listing numbers: 84.042 (SSS), 84.044 (Talent Search), 84.047 (Upward Bound, which also covers Upward Bound Math-Science and Veterans Upward Bound), 84.066 (EOC), 84.217 (McNair), and 84.334 (GEAR UP). 84.103 (TRIO Training) is a related listing. SAM.gov shows all seven as active, and none has been renumbered. Sub-programs show up only as a competition suffix (84.047A/M/V, 84.334A/S) and as the 5th character of the FAIN (`P047M…`). They do not get separate listings.
- **Best source for ~5 FYs × 6–7 programs: bulk files, not paged search.**
  - **Option 1.** Use the per-agency Award Data Archive: Department of Education (ED, toptier code 091), one assistance file per FY, pre-built and refreshed monthly. Filter it locally to the listings.
  - **Option 2.** Make one filtered `POST /api/v2/download/transactions/` (or `/download/awards/`) request.
  - **Why not search:** the whole FY2021–FY2025 universe is 20,913 transactions, far under the 500,000-row download cap. Paged search tops out at 100 rows per page, and its time filter selects *awards*, not *spending in a year*.
- **Grant structure.** Each ED grant is one award per FAIN for a whole 5-year project period, with one transaction per year: A1 New, then B1 Continuation, plus some EX/FX "Other" actions. A renewal is a new competition and gets a **new FAIN**.
  - "Amount by year" = sum of transaction `federal_action_obligation` grouped by `action_date_fiscal_year`.
  - Renewal timing = sequence of FAINs per (recipient UEI, listing).
- **Data-quality issues to plan for:**
  - DUNS stopped being issued in April 2022. The FY2025 file has `recipient_duns` empty on every TRIO/GEAR UP row.
  - Outlays have only been required since FY22.
  - FABS reporting lags: the 14-day rule is often missed (median 19 days in FY2025 for these programs).
  - Some non-ED awards carry a TRIO listing number among several, so filter by agency and transaction listing number.
  - Subawards are reported separately (FSRS) and only at ≥ $30k.
  - Recipient alternate-name lists are noisy.
  - Some files carry officer-name columns that must be dropped.

## Programs → listing numbers → sources

| Program | Assistance Listing | Competition suffix / FAIN prefix seen | Confirmed in |
|---|---|---|---|
| TRIO Student Support Services | **84.042** | 84.042A / `P042A` | SAM.gov listing `ed1ada9051254896a83f4ecbf9cb6620`[^sam042]; ED notice 2024-08328 ("Assistance Listing Number 84.042A")[^fr042]; USAspending autocomplete[^ac] |
| TRIO Talent Search | **84.044** | 84.044A / `P044A` | SAM.gov `2549a700e6f34fdea21a5925f191a6a3`[^sam044]; ED notice 2026-05655 ("Talent Search program (84.044A)")[^fr044] |
| TRIO Upward Bound (regular) | **84.047** | 84.047A / `P047A` | SAM.gov `8681de14d7f84ffe9af4a578d42559bb`[^sam047]; ED notice 2021-27235 ("84.047A")[^fr047a] |
| Upward Bound Math and Science | **84.047** (shared) | 84.047M / `P047M` | SAM.gov 84.047 objective: "This listing applies to Upward Bound, Veterans Upward Bound, and Upward Bound Math and Science."[^sam047]; ED notice 2022-08295 ("84.047M")[^fr047m] |
| Veterans Upward Bound | **84.047** (shared) | 84.047V / `P047V` | same SAM.gov statement[^sam047]; ED notice 2022-08827 ("84.047V")[^fr047v] |
| TRIO Educational Opportunity Centers | **84.066** | 84.066A / `P066A` | SAM.gov `4d8603995e5e4678931e36b9103cad22`[^sam066]; ED notice 2026-06456 ("(84.066A)")[^fr066] |
| Ronald E. McNair Postbaccalaureate Achievement | **84.217** | 84.217A / `P217A` | SAM.gov `60904b0b7cf149a0832cef6edee1b34b`[^sam217]; ED notice 2022-04987 ("84.217A")[^fr217] |
| GEAR UP (Partnership grants) | **84.334** | 84.334A / `P334A` | SAM.gov `0bb2c63123ad488a9802e6b0c4488b4e`[^sam334]; ED notice 2024-27054 ("84.334A")[^fr334a] |
| GEAR UP (State grants) | **84.334** (shared) | 84.334S / `P334S` | ED notice 2024-27055 ("84.334S")[^fr334s] |
| *Related:* Training Program for Federal TRIO Programs (SAM title "TRIO Staff Training Program") | **84.103** | 84.103A / `P103A` | SAM.gov `694d58ec4d9440fa8c1f91d4dfdbeda7` (objective names "program numbers 84.042, 84.044, 84.047, 84.066, and 84.217")[^sam103]; ED notice 2026-10630 ("84.103A")[^fr103] |

FAIN-prefix counts come from a live FY2025 pull, paged through `spending_by_award` (all pages). For 84.047 the counts were `P047A` 1125, `P047M` 275, `P047V` 70. For 84.334 they were `P334A` 99, `P334S` 46. Every other listing had a single prefix.

## 1. Assistance Listing numbers

**SAM.gov.** The SAM.gov listing pages are a JavaScript app, so a plain fetch returns only the title. The same data came from SAM.gov's own JSON backend:
- Search: `https://sam.gov/api/prod/sgs/v1/search/?index=cfda&q="84.047"&is_active=true`
- Detail: `https://sam.gov/api/prod/fac/v1/programs/<id>`

All seven numbers above came back as active listings, titled as in the table. Each was last published in Jul 2026 (publishDate 2026-07-23 to 2026-07-30). USAspending's award detail endpoint links to the same SAM.gov page (`sam_website`), for example `https://sam.gov/fal/8681de14d7f84ffe9af4a578d42559bb/view` for 84.047.

**Notes copied from the SAM.gov listing records** (`financial.additionalInformation`):
- 84.042: "This program will only make continuations until 2030."
- 84.047: "This assistance listing will only make continuation awards in FY 2026."
- 84.217: "This assistance listing will only make continuation awards in FY 2026."

**Renumbering check.**
- SAM.gov archived-listing searches for "TRIO", "Upward Bound", "GEAR UP" and "Gaining Early Awareness" returned no archived TRIO or GEAR UP numbers.
- The listing records have no history field.
- ED's own notices from 2014–2026 use the same base numbers (84.042, 84.044, 84.047, 84.066, 84.217, 84.103, 84.334)[^fr042][^fr044][^fr047a][^fr066][^fr103][^fr334a].
- **Conclusion:** no renumbering. Two loose ends:
  - Archived **84.272** "National Early Intervention Scholarship and Partnership" exists in SAM.gov, and USAspending has 0 awards under it from FY2008 on. *Whether it was GEAR UP's predecessor is UNVERIFIED* (no primary source checked).
  - Archived **84.344** has title "Deleted", and USAspending has 0 awards.

**ed.gov.** ed.gov pages returned HTTP 403 (Azure WAF "Please enable JavaScript") to non-browser fetches. ED's numbers were therefore confirmed from ED's own Federal Register notices inviting applications, linked in the table. The ed.gov program URLs that SAM.gov lists are in its `website` field. For example: `https://www.ed.gov/grants-and-programs/grants-higher-education/trio/upward-bound-program`.

## 2. USAspending API: endpoints, filters, paging, limits, auth

Endpoint list: https://api.usaspending.gov/docs/endpoints. Contracts live in https://github.com/fedspendingtransparency/usaspending-api/tree/master/usaspending_api/api_contracts/contracts/v2. The repo was at master commit `0a6d86a1e7e4105f349ec5db193ed4c7fca00466` when checked.

| Need | Endpoint | Notes |
|---|---|---|
| Find awards by listing / FY | `POST /api/v2/search/spending_by_award/` | Award-level rows (contract `search/spending_by_award.md`) |
| Count before paging | `POST /api/v2/search/spending_by_award_count/` | Counts by type group (grants / direct_payments / …) |
| Find transactions by listing / FY | `POST /api/v2/search/spending_by_transaction/` | Row per transaction (contract `search/spending_by_transaction.md`) |
| All transactions of one award | `POST /api/v2/transactions/` | `award_id` = generated id, e.g. `ASST_NON_P047A220845_091`; `limit` Min 1 / Max 5000 (contract `transactions.md`) |
| One award's detail | `GET /api/v2/awards/<generated_award_id>/` | Project period, totals, parent, SAM listing link |
| Recipient profile | `GET /api/v2/recipient/<recipient_hash>-<level>/?year=all` | Level `R` neither, `P` parent, `C` child (contract `recipient/recipient_id.md`) |
| Filtered file (async) | `POST /api/v2/download/awards/`, `/download/transactions/`; poll `GET /api/v2/download/status?file_name=` | Accepts `program_numbers`; row cap 500,000 |
| Rows a download would contain | `POST /api/v2/download/count/` | Returns `calculated_transaction_count`, `maximum_transaction_limit` |
| Custom award download (bulk) | `POST /api/v2/bulk_download/awards/` | Filters by agency / date / award type / location. **No listing filter** in the contract (`bulk_download/awards.md`) |
| Pre-built Award Data Archive | `POST /api/v2/bulk_download/list_monthly_files/` (`agency` = ED's bulk id **80**, `type`=`assistance`) | Returns `files.usaspending.gov/award_data_archive/...` URLs |
| Listing autocomplete | `POST /api/v2/autocomplete/cfda/` | Used to confirm the titles above |

**Filters** (contract `search/spending_by_award.md`, AdvancedFilterObject):
- `program_numbers` (assistance listing)
- `award_type_codes`: grants are `02`, `03`, `04`, `05`; direct payments `06`, `10`; loans `07`, `08`. The contract says "Grant Type Codes (02, 03, 04 or 05)". All observed TRIO/GEAR UP awards are type `04` "PROJECT GRANT (B)".
- `time_period`
- `agencies`
- `recipient_search_text` (matches name, UEI, DUNS)
- `recipient_locations` and `place_of_performance_locations`
- `award_ids`: a quoted value gives an exact match

**`time_period` semantics.** These are documented in `api_contracts/search_filters.md`, "Award Search Time Period Object". By default `start_date` is compared to `action_date`, described as "typically … the date of the latest transaction associated with the award". `end_date` is compared to `date_signed`, described as "the date of the base transaction".
- So an FY filter on `spending_by_award` returns awards *touched in or after* the FY that began on or before its end. It does not return obligations *in* that FY.
- `date_type: "new_awards_only"` restricts to awards whose base transaction falls in the window.
- On `spending_by_transaction` the default is `action_date`, i.e. a true FY-of-action filter.
- The earliest searchable date is 2007-10-01. Older data needs download endpoints. The live API returns this as a `messages` warning.

**Paging and limits:**
- `limit` defaults to 10. The max is 100: a live call with `limit: 101` returned `{"detail":"Field 'limit' value '101' is above max '100'"}`.
- Use `page` and `page_metadata.hasNext`.
- Deep paging: `settings.py` sets `ES_AWARDS_MAX_RESULT_WINDOW = 50000`. `spending_by_award.py` then raises "Page #… is over the maximum result limit 50000. Please provide the 'last_record_sort_value' and 'last_record_unique_id' to paginate sequentially."
- Downloads: `MAX_DOWNLOAD_LIMIT = 500000` (`usaspending_api/settings.py`).

**Rate limits / auth:**
- **Authentication:** none was needed for any call made here. The API docs pages mention no key or registration (https://api.usaspending.gov/, https://api.usaspending.gov/docs/intro-tutorial).
- **Rate limits:** *No documented rate limit found (UNVERIFIED that none exists).*
  - The doc pages and a code search of the repo for "THROTTLE" / "rate limit" turned up nothing.
  - Response headers carried no rate-limit fields.
  - Be polite anyway: serial requests with backoff.
- **Download queue:** a `download/awards` job for one listing and one FY (84.066, FY2025) was still `"status":"ready"` (queued, not running) after more than 15 minutes. Async downloads can therefore queue for a long time.

### Live call 1: awards for one listing, one FY

```bash
curl -s -X POST https://api.usaspending.gov/api/v2/search/spending_by_award/ \
  -H 'Content-Type: application/json' -d '{
  "filters":{"award_type_codes":["02","03","04","05"],"program_numbers":["84.047"],
             "time_period":[{"start_date":"2024-10-01","end_date":"2025-09-30"}]},
  "fields":["Award ID","Recipient Name","Recipient UEI","Recipient DUNS Number","recipient_id",
            "Award Amount","Total Outlays","Start Date","End Date","Award Type","CFDA Number",
            "Recipient Location","Primary Place of Performance","generated_internal_id",
            "Description","Last Modified Date","Base Obligation Date"],
  "page":1,"limit":3,"sort":"Award Amount","order":"desc"}'
```

Trimmed response (2nd result):

```json
{"internal_id": 269526570, "Award ID": "P047A220845",
 "Recipient Name": "UNIVERSITY OF SOUTH FLORIDA", "Recipient UEI": "NKAZLXLL7Z91",
 "Recipient DUNS Number": null, "recipient_id": "ceec5ef7-d6a5-28f0-e23f-ec61155b7078-C",
 "Award Amount": 4253358.0, "Total Outlays": 3156863.49,
 "Start Date": "2022-06-01", "End Date": "2027-08-31",
 "Award Type": "PROJECT GRANT (B)", "CFDA Number": "84.047",
 "Recipient Location": {"state_code": "FL", "city_name": "TAMPA", "address_line1": "4202 E FOWLER AVE",
                        "congressional_code": "15", "zip5": "33620", "zip4": "9951", "...": "..."},
 "Primary Place of Performance": {"state_code": "FL", "congressional_code": "15", "zip5": "33620", "...": "..."},
 "generated_internal_id": "ASST_NON_P047A220845_091",
 "Base Obligation Date": "2022-05-23", "Last Modified Date": "2026-09-02 20:10:08"}
```

The response used the top-level `"Place of Performance Congressional District"` field name even though that name is **not** in the contract's field list. It came back `null`. Use `Primary Place of Performance.congressional_code` instead.

FY2025 counts from `spending_by_award_count` (same filter):

| Listing | 84.042 | 84.044 | 84.047 | 84.066 | 84.217 | 84.334 | 84.103 |
|---|---|---|---|---|---|---|---|
| Grants | 1992 | 517 | 1470 | 169 | 325 | 145 | 6 |

84.042 also showed `direct_payments: 1` (see §5).

### Live call 2: transactions for one award

```bash
curl -s -X POST https://api.usaspending.gov/api/v2/transactions/ -H 'Content-Type: application/json' \
  -d '{"award_id":"ASST_NON_P047A220845_091","page":1,"limit":50,"sort":"action_date","order":"asc"}'
```

Trimmed response (`description` omitted):

```json
[{"action_date":"2022-05-23","action_type":"A1","action_type_description":"New Award","modification_number":"1","federal_action_obligation":824294.0,"cfda_number":"84.047"},
 {"action_date":"2023-05-13","action_type":"B1","action_type_description":"Continuation","modification_number":"2","federal_action_obligation":857266.0},
 {"action_date":"2024-05-15","action_type":"B1","modification_number":"3","federal_action_obligation":857266.0},
 {"action_date":"2025-09-17","action_type":"B1","modification_number":"4","federal_action_obligation":857266.0},
 {"action_date":"2026-07-28","action_type":"B1","modification_number":"5","federal_action_obligation":857266.0}]
```

The five obligations sum to 4,253,358.00, which equals the award's `total_obligation`.

### Live call 3: transaction search (GEAR UP, FY2025)

```bash
curl -s -X POST https://api.usaspending.gov/api/v2/search/spending_by_transaction/ -H 'Content-Type: application/json' -d '{
 "filters":{"award_type_codes":["02","03","04","05"],"program_numbers":["84.334"],
            "time_period":[{"start_date":"2024-10-01","end_date":"2025-09-30"}]},
 "fields":["Award ID","Mod","Recipient Name","Recipient UEI","Action Date","Action Type",
           "Transaction Amount","Transaction Description","Assistance Listing","Award Type"],
 "page":1,"limit":2,"sort":"Transaction Amount","order":"desc"}'
```

Trimmed response:

```json
{"Award ID":"P334A230100","Mod":"3","Recipient Name":"UNIVERSITY OF OKLAHOMA","Recipient UEI":"EVTSTTLCEWS5",
 "Action Date":"2025-09-18","Action Type":"B1","Transaction Amount":6606400.0,
 "Assistance Listing":{"cfda_number":"84.334","cfda_title":"GAINING EARLY AWARENESS AND READINESS FOR UNDERGRADUATE PROGRAMS"},
 "generated_internal_id":"ASST_NON_P334A230100_091"}
```

### Live call 4: download size for the whole target universe

```bash
curl -s -X POST https://api.usaspending.gov/api/v2/download/count/ -H 'Content-Type: application/json' -d '{
 "filters":{"award_type_codes":["02","03","04","05"],
            "program_numbers":["84.042","84.044","84.047","84.066","84.217","84.334","84.103"],
            "time_period":[{"start_date":"2020-10-01","end_date":"2025-09-30"}]}}'
```

Response: `{"calculated_transaction_count":20913,"maximum_transaction_limit":500000,"transaction_rows_gt_limit":false,...}`

## 3. Recipient and award fields

**Field-name sources:**
- The live responses above.
- The FY2025 ED Award Data Archive file `FY2025_091_Assistance_Full_20261007_1.csv`, which has 116 columns.
- The data dictionary at `GET /api/v2/references/data_dictionary/`. Its rows map each element to download column names.

| Concept | API (search / award detail) | Download / archive column | Definition source |
|---|---|---|---|
| FAIN | `Award ID`; `fain` | `award_id_fain` | Data dictionary "FAIN": "unique ID within the Federal agency for each (non-aggregate) financial assistance award" |
| Stable award key | `generated_internal_id` / `generated_unique_award_id` (e.g. `ASST_NON_P047A220845_091`) | `assistance_award_unique_key` | Contract `transactions.md`: generated ids "are effectively permanent" |
| Transaction key | `id` in `/transactions/` | `assistance_transaction_unique_key` (e.g. `9100_P047A220845_-NONE-_84.047_4`) | Data dictionary "AssistanceTransactionUniqueKey" |
| Modification number | `modification_number` / `Mod` | `modification_number` | Data dictionary "AwardModificationAmendmentNumber" |
| Action date / FY | `action_date` / `Action Date` | `action_date`, `action_date_fiscal_year` | Data dictionary "ActionDate", "ActionDateFiscalYear" |
| Action type | `action_type` | `action_type_code`, `action_type_description` | Data dictionary "ActionType" (see caveat in §5) |
| UEI | `Recipient UEI`; `recipient.recipient_uei` | `recipient_uei` | Data dictionary "AwardeeOrRecipientUEI" |
| Legacy DUNS | `Recipient DUNS Number`; `recipient_unique_id`; recipient profile `duns` | `recipient_duns`, `recipient_parent_duns` | Profile contract: "`null` when no DUNS is provided". The website labels it "Legacy" (`GlobalConstants.js` `DUNS_LABEL: 'Legacy '`) |
| Recipient name | `Recipient Name` | `recipient_name`, `recipient_name_raw` | Data dictionary "AwardeeOrRecipientLegalEntityName" |
| Parent recipient | `parent_recipient_name`, `parent_recipient_uei` (award detail) | `recipient_parent_uei`, `recipient_parent_name` | Data dictionary "UltimateParentUEI", "UltimateParentLegalEntityName" |
| Recipient address + CD | `Recipient Location{address_line1, city_name, state_code, zip5, zip4, county_code, congressional_code}` | `recipient_address_line_1`, …, `prime_award_transaction_recipient_cd_original`, `…_cd_current` | Data dictionary "LegalEntityCongressionalDistrict" |
| Place of performance + CD | `Primary Place of Performance{…, congressional_code}` | `primary_place_of_performance_*`, `prime_award_transaction_place_of_performance_cd_original` / `_cd_current` | Data dictionary "PrimaryPlaceOfPerformanceCongressionalDistrict" |
| Period of performance | `Start Date`, `End Date`; `period_of_performance.start_date/end_date` | `period_of_performance_start_date`, `period_of_performance_current_end_date` | Data dictionary: for grants, "the total estimated time interval between the start of an initial Federal award and the planned end date, which may include one or more funded portions, or budget periods" |
| Obligation (per transaction) | `federal_action_obligation` / `Transaction Amount` | `federal_action_obligation` | Data dictionary: "Amount of Federal government's obligation, de-obligation, or liability … for an award transaction" |
| Obligation (award total) | `Award Amount`; `total_obligation` | `total_obligated_amount` | Data dictionary "TotalDollarsObligated" |
| Outlays (award total) | `Total Outlays`; `total_outlay` / `total_account_outlay` | `total_outlayed_amount_for_overall_award` | Data dictionary: "outlays have only been required to be reported since FY22" |
| Listing | `CFDA Number`, `Assistance Listings[]`; `cfda_info[]` | `cfda_number`, `cfda_title` | Data dictionary "AssistanceListingNumber" |
| Funding opportunity | `funding_opportunity.number` | `funding_opportunity_number` (e.g. `ED-GRANTS-121621-003`) | live response |
| Business type | `business_categories` | `business_types_code`, `business_types_description` | live response |

**Do not ingest:** `highly_compensated_officer_1..5_name/amount` (archive) and `executive_details.officers` (award detail). These are individual people and out of scope. They were null in every sample here.

**Two levels of "period of performance".** The award-level dates are the project period: award detail shows 2022-06-01 → 2027-08-31 for `P047A220845`. The transaction row carries the *budget period* of that action: mod 4 in the archive shows `period_of_performance_start_date` 2025-09-01 → `period_of_performance_current_end_date` 2026-08-31.

**Multi-year grants:**
- **Pattern:** one award (one FAIN, one `generated_internal_id`) per project period, with one transaction per budget year (live call 2).
- **Renewal = new competition = new FAIN.** For USF Upward Bound, a UEI search across FY2008–FY2026 returned `P047A080486`, `P047A121707`, `P047A171493` and `P047A220845`, plus a separate UBMS award `P047M220477`.
- **FAIN pattern (observed, not documented):** characters 6–7 match the competition year (`…22…` → base obligation 2022-05-23). *UNVERIFIED as an ED convention.*

**What this means for "award amount by year":**
- Use transaction rows. Sum `federal_action_obligation` by `action_date_fiscal_year` (or by budget-period start) per FAIN.
- Do **not** use `Award Amount` / `total_obligated_amount`. Those are cumulative over the whole project period.
- Continuation actions can land in a different FY than the budget period they fund. Example: action 2025-09-17 (FY2025) funds the budget period 2025-09-01 → 2026-08-31.
- Pick one basis (action FY vs. budget-period FY) and document it.

**What this means for renewal timing:**
- For each (UEI, listing/suffix), sort FAINs by base action date (`A1`, `Base Obligation Date`).
- A new FAIN following an expiring one = renewed. Award `End Date` (project period end) = when the next competition matters.
- Watch for UEI changes across cycles. A legacy DUNS may be the only link for pre-2022 awards.

## 4. Bulk download vs. API

**Recommendation:** use the bulk files for the backfill and keep the API for spot checks.

**Primary: Award Data Archive.**
1. `list_monthly_files` with `{"agency":80,"fiscal_year":FY,"type":"assistance"}`.
2. Download `FY{FY}_091_Assistance_Full_{date}.zip` for FY2021–FY2025. FY2025 was `FY2025_091_Assistance_Full_20261006.zip`: 86.6 MB zipped, 789 MB CSV, 609,118 rows of all ED assistance.
3. Filter `cfda_number` to the 7 listings. In FY2025 that left 3,994 rows (84.047 1,525; 84.042 1,264; 84.044 539; 84.217 327; 84.066 176; 84.334 157; 84.103 6).
4. Use `FY(All)_091_Assistance_Delta_{date}.zip` for monthly updates.

Why this fits a local polars + Parquet pipeline:
- Deterministic, versioned files.
- No paging.
- Transaction grain, which you need for by-year amounts.
- `cd_original` / `cd_current` and parent UEI included.

**Alternative:** one `POST /api/v2/download/transactions/` with `program_numbers` + `time_period`. The whole set is 20,913 rows, under the 500,000 cap. The files are smaller, but the job is async and was observed to stay queued for more than 15 minutes.

**Why not paged search:**
- 100 rows per page.
- The award `time_period` semantics shown in §2.
- No transaction-level amounts per FY without one `/transactions/` call per award.

Search is still fine for incremental checks and for the award-detail fields (project period, `sam_website`).

**Not suitable:** `bulk_download/awards` (Custom Award Download). Its contract has no listing filter, so you would pull all of ED.

## 5. Data-quality caveats

All of these are documented, observed, or both:

1. **Reporting lag.**
   - **Documented rule:** "Federal agencies must submit financial assistance data to FABS within two weeks of the award transaction", and data publish the day after submission. Source: USAspending *Data Sources* PDF, https://www.usaspending.gov/data/data-sources-download.pdf (PDF dated Jan 2023).
   - **Observed** for these programs in FY2025 (`initial_report_date − action_date`): min 8, median 19, p90 52, max 60 days, with 92.5% over 14 days.
   - **Implication:** treat the latest ~2 months as incomplete, and re-pull after FY close.
2. **DUNS → UEI.**
   - GSA: SAM.gov moved to the Unique Entity ID on April 4, 2022, and DUNS was no longer accepted. Source: https://www.gsa.gov/about-gsa/newsroom/news-releases/gsa-systems-switch-to-unique-entity-id-sam-on-april-4-2022-03162022.
   - USAspending's notice: "In April 2022, the federal government will transition from DUNS numbers to the new Unique Entity Identifier (UEI)…" (`usaspending-website/src/js/containers/shared/UEIModalContainer.jsx`).
   - **Observed:** `recipient_duns` empty on all 3,994 FY2025 TRIO/GEAR UP rows. The recipient profile still returns the legacy `duns` (USF: `069687242`).
   - **Implication:** key on UEI. Bridge older years via the recipient profile's `duns` + `uei`.
3. **D&B data-use limits on DUNS-era data.**
   - USAspending's D&B page: D&B "Open Data" (name, address fields) may not be used "in bulk", and other D&B data may not be used "for commercial, resale or marketing purposes". It also says "Systematic access (electronic harvesting) … is prohibited."
   - Source: https://github.com/fedspendingtransparency/usaspending-website/blob/master/src/js/components/about/DBInfo.jsx. The public page route for it was not confirmed.
   - **Relevance:** this applies to a company building a prospect list from legacy DUNS-linked data. Get a legal read (see Open questions).
4. **Outlays.**
   - Award-level outlays have only been required since FY22 (data dictionary "TotalOutlayedAmountForOverallAward").
   - USAspending says "it is more common to measure spending by obligations rather than outlays" (Data Sources PDF).
   - **Observed mismatch** for `P047A220845` on the same day: search `Total Outlays` = 3,156,863.49, but award detail `total_outlay` = archive `total_outlayed_amount_for_overall_award` = 3,232,782.88.
   - **Implication:** use obligations.
5. **Multi-listing awards from other agencies.**
   - `program_numbers: ["84.042"]` also matched a Department of the Interior (Bureau of Indian Affairs/Bureau of Indian Education) direct payment, `ASST_NON_A08AV00094_014`, which lists 10 listings including 84.042.
   - **Fix:** also require awarding toptier code `091` and transaction-level `cfda_number`.
6. **Subawards.**
   - Prime recipients report subawards ≥ $30,000 to FSRS (File F) by the end of the following month (Data Sources PDF).
   - Subaward data is separate from prime award data (`spending_level: "subawards"`).
   - All sampled TRIO awards had `subaward_count: 0`.
7. **Recipient name noise.** The USF recipient profile's `alternate_names` includes "EMORY UNIVERSITY", "SAM HOUSTON STATE UNIVERSITY" and "UNIVERSITY OF SOUTHERN CALIFORNIA". Do not use `alternate_names` for matching. Use UEI.
8. **Mergers / name drift.**
   - `P047A220689` description "MILLS COLLEGE UPWARD BOUND PROGRAM CONTINUATION" is recorded under recipient "NORTHEASTERN UNIVERSITY".
   - Parent UEI was filled on 1,386 of 3,994 FY2025 rows only.
9. **Action-type codes don't match the dictionary.**
   - The data dictionary lists assistance ActionType as single letters A–E.
   - ED rows actually carry `A1` New Award, `B1` Continuation, `EX` "Other Action, Non-Financial", `FX` "Other Action, Financial".
   - Some `EX` rows have nonzero `federal_action_obligation`. Example: `P217A220112` mod 5 = 272,363.00.
   - 332 FY2025 rows had negative obligations (deobligations).
   - **Implication:** sum all rows. Do not filter on action type to compute totals.
10. **Listing totals don't reconcile to SAM.gov.**
    - FY2025 sums of `federal_action_obligation` in the archive vs. the SAM.gov listing "actual":
      - 84.047: 469.4M vs 464.1M
      - 84.042: 400.0M vs 381.2M
      - 84.334: 367.3M vs 387.7M
    - Cause UNVERIFIED (timing of continuation actions across FYs is one candidate).
11. **Other documented limits.** USAspending excludes PII. ED records here are all `record_type_code` 2, "NON-AGGREGATE RECORD" (data dictionary "RecordType").

## Open questions / UNVERIFIED

- **Rate limits:** none documented on api.usaspending.gov or found in the repo, and no rate-limit headers were seen. Whether throttling exists is UNVERIFIED.
- **84.272 as GEAR UP predecessor:** UNVERIFIED. It is archived in SAM.gov with 0 USAspending awards since FY2008.
- **FAIN year digits:** that characters 6–7 encode the competition FY is an observed pattern, not found in ED documentation. UNVERIFIED.
- **ED action-type codes:** the meaning of `A1`/`B1`/`EX`/`FX` beyond their descriptions, and why `EX` "Non-Financial" rows carry obligations, is not in the USAspending data dictionary. The dictionary may predate a schema (GSDM) update. UNVERIFIED.
- **Outlays mismatch:** the cause of `Total Outlays` in search differing from award detail and the archive is UNVERIFIED.
- **SAM.gov vs. USAspending totals:** the cause of the listing-level gap is UNVERIFIED.
- **ed.gov pages:** returned 403 to automated fetch. Program numbers were confirmed via ED's Federal Register notices and SAM.gov instead. A manual browser check of ed.gov program pages was not done.
- **Data Sources PDF:** the lag rules come from a PDF created Jan 2023 (PDF metadata). It is still linked from usaspending.gov, but whether the rules changed since is UNVERIFIED.
- **Async download timing:** the `download/awards` job (84.066, FY2025) did not finish within the session. Its output columns were not checked directly. The archive columns listed above are verified.
- **D&B license:** whether the D&B terms restrict an education-services company's use of legacy-DUNS-era name/address data for business development needs a legal read. This is a policy question and was not researched here.

[^ac]: `POST https://api.usaspending.gov/api/v2/autocomplete/cfda/` with `{"search_text":"TRIO"}` returned 84.042, 84.044, 84.047, 84.066, 84.103 and 84.217. `{"search_text":"84.334"}` returned "Gaining Early Awareness and Readiness for Undergraduate Programs" `(GEAR-UP)`.
[^sam042]: https://sam.gov/fal/ed1ada9051254896a83f4ecbf9cb6620/view (data via `https://sam.gov/api/prod/fac/v1/programs/ed1ada9051254896a83f4ecbf9cb6620`)
[^sam044]: https://sam.gov/fal/2549a700e6f34fdea21a5925f191a6a3/view
[^sam047]: https://sam.gov/fal/8681de14d7f84ffe9af4a578d42559bb/view; the objective text was also returned by USAspending award detail `cfda_info[].cfda_objectives`.
[^sam066]: https://sam.gov/fal/4d8603995e5e4678931e36b9103cad22/view
[^sam217]: https://sam.gov/fal/60904b0b7cf149a0832cef6edee1b34b/view
[^sam334]: https://sam.gov/fal/0bb2c63123ad488a9802e6b0c4488b4e/view
[^sam103]: https://sam.gov/fal/694d58ec4d9440fa8c1f91d4dfdbeda7/view
[^fr042]: ED, "Applications for New Awards; Student Support Services Program", 2024-05-01: https://www.federalregister.gov/documents/2024/05/01/2024-08328/applications-for-new-awards-student-support-services-program
[^fr044]: ED, "Notice Announcing Talent Search Program", 2026-03-23: https://www.federalregister.gov/documents/2026/03/23/2026-05655/notice-announcing-talent-search-program
[^fr047a]: ED, "Applications for New Awards; Upward Bound Program", 2021-12-16: https://www.federalregister.gov/documents/2021/12/16/2021-27235/applications-for-new-awards-upward-bound-program
[^fr047m]: ED, "Applications for New Awards; Upward Bound Math and Science Program", 2022-04-19: https://www.federalregister.gov/documents/2022/04/19/2022-08295/applications-for-new-awards-upward-bound-math-and-science-program
[^fr047v]: ED, "Applications for New Awards; Veterans Upward Bound Program", 2022-04-26: https://www.federalregister.gov/documents/2022/04/26/2022-08827/applications-for-new-awards-veterans-upward-bound-program
[^fr066]: ED, "Notice Announcing Educational Opportunity Centers Program Competition", 2026-04-03: https://www.federalregister.gov/documents/2026/04/03/2026-06456/notice-announcing-educational-opportunity-centers-program-competition
[^fr217]: ED, "Applications for New Awards; Ronald E. McNair Postbaccalaureate Achievement Program", 2022-03-09: https://www.federalregister.gov/documents/2022/03/09/2022-04987/applications-for-new-awards-ronald-e-mcnair-postbaccalaureate-achievement-program
[^fr334a]: ED, GEAR UP (Partnership Grants), 2024-11-20: https://www.federalregister.gov/documents/2024/11/20/2024-27054/applications-for-new-awards-gaining-early-awareness-and-readiness-for-undergraduate-programs
[^fr334s]: ED, GEAR UP (State Grants), 2024-11-20: https://www.federalregister.gov/documents/2024/11/20/2024-27055/applications-for-new-awards-gaining-early-awareness-and-readiness-for-undergraduate-programs-state
[^fr103]: ED, "Notice Announcing TRIO Training Program Competition", 2026-05-28: https://www.federalregister.gov/documents/2026/05/28/2026-10630/notice-announcing-trio-training-program-competition
