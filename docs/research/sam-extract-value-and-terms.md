# SAM.gov public monthly extract: what it adds to Recipient matching, and what the D&B clause allows

Researched 2026-10-14. Read with `entity-and-geo-sources.md` (Part A covers SAM access and keys), `federal-audit-clearinghouse.md`, `usaspending-trio-gearup.md` and `source-terms-and-cadence.md`. Terms follow `GLOSSARY.md`: **Recipient** (the UEI-identified legal entity), **Grant** (one FAIN), **Host institution** (UNITID or LEAID).

Method:
- **No SAM account or key** was created or used. I did not download any SAM entity data.
- **SAM documentation** was read with single ordinary fetches of open.gsa.gov pages and workbooks and of the SAM.gov Terms of Use.
- **Data:**
  - USAspending FY2024 ED Award Data Archive (`FY2024_091_Assistance_Full_20261006.zip`).
  - USAspending recipient-profile API, one call per Recipient.
  - FAC bulk `general.csv` and `additional_ueis.csv`.
  - IPEDS `HD2024.zip`.
- **Source code read:** usaspending-api (`master` @ `0a6d86a1`, 2026-10-14) and data-act-broker-backend (`master` @ `bed939e6`, 2026-10-14).
- **Points of contact:** none were collected. POC columns are listed below only to say they must be dropped.

Not legal advice.

## Verdict

**v1 does not need SAM.** It becomes a *maybe* later, under the conditions listed after the bullets below.

What already covers v1:
- **USAspending already republishes SAM's entity core for every Recipient that has a SAM record.** The USAspending recipient profile's name, physical address, congressional district and parent come from SAM (§2). USAspending's own loader reads the SAM *FOUO* extract, so it even supplies the ultimate parent. That parent is FOUO and is not in the public extract.
- **The hard matching problem is Recipient → Host institution (UNITID/LEAID). SAM does not solve it.** SAM carries no UNITID, OPEID or LEAID (§1).
- **IPEDS is the better source for colleges.** IPEDS HD2024 publishes `UEIS` (UEIs per UNITID). It matched **1,000 of 1,345 (74%)** FY2024 TRIO/GEAR UP Recipient UEIs directly (§4).
- **FAC covers most of the rest.** FAC (2022–2025, primary or additional UEI) covers another 267. Only **78 Recipients (2.9% of FY2024 obligations)** are in neither IPEDS nor FAC.

What SAM would add that no current source gives:
- `DBA NAME`.
- `ENTITY URL`, which could be matched against IPEDS `WEBADDR`.
- The raw `BUS TYPE STRING`, which includes `H6` School District, `M8`, `1R`, `OH`, `HB`, `HS`, `GW`, and others.
- `ENTITY STRUCTURE`.
- Mailing address.
- `CAGE CODE`.
- Registration dates and status.

Of these, only DBA, URL and `H6` plausibly help matching. They matter for the **345 Recipients with no IPEDS UEI hit** (school districts, nonprofits, state agencies, some colleges): 28% of FY2024 obligations.

Conditions under which SAM moves to "yes":
1. Hand review of the 345 non-IPEDS Recipients shows that name, address and geo matching to LEAID or UNITID leaves a real residue.
2. Telling K-12 districts apart from community-college districts matters, and the existing sources cannot do it (§4: ED's FABS code `G` is used for both).

**How to check the gain.** It needs one free SAM.gov individual account, its "Public API Key", and **one** extract download (§5). The no-role limit is 10 requests/day.

**Licensing.** The SAM D&B restrictions apply only to records whose EVS source is D&B. Those are "entity registration records with a last updated date earlier than 4/4/2022" (SAM ToU).
- **Current monthly file (inference, UNVERIFIED):** the monthly public file holds only active registrations and those expired in the last 6 months, and a registration expires 365 days after submission. So a current file should contain essentially no D&B-sourced records. Check the `ENTITY EVS SOURCE` column on first download.
- **D&B-sourced rows:** for any such rows, the clause's non-Open-Data commercial ban names exactly our use: "identifying, quantifying, segmenting and/or analyzing customers and prospective customers". Sharing with one business does not take the use outside "commercial … or marketing purposes".
- **Bigger exposure is on the USAspending side, not SAM:** USAspending's identical D&B notice has **no 2022 date scoping** and defines D&B data to include "each entity's DUNS Number". Using legacy DUNS to bridge pre-2022 Grants for a prospect analysis is the most clearly restricted act in the current plan (§6).

---

## 1. Field-by-field: SAM public extract vs. what we already have

Sources:
- **SAM public extract layout:** `SAM Master Extract Mapping v6.0 Public File V2 Layout.xlsx` (https://open.gsa.gov/api/sam-entity-extracts-api/v1/SAM%20Master%20Extract%20Mapping%20v6.0%20Public%20File%20V2%20Layout.xlsx, server Last-Modified 2022-10-25). It has 142 columns, all with sensitivity "Public". Column numbers below are 1-based "Column Order".
- **USAspending:** archive columns as observed in the FY2024 file; recipient-profile fields from `usaspending_api/recipient/v2/views/recipients.py`.
- **FAC:** `general.csv` / `additional_ueis.csv` headers (downloaded 2026-10-14).
- **IPEDS:** `HD2024_dict.xlsx`.

| Matching-relevant field | SAM public extract | USAspending (FY2024 archive / recipient profile) | FAC `general` / `additional_ueis` | Net gain from SAM |
|---|---|---|---|---|
| UEI | col 1 `UNIQUE ENTITY ID` | `recipient_uei` (archive); `uei` (profile) | `auditee_uei`; `additional_uei` | None (join key) |
| Legal name | col 12 `LEGAL BUSINESS NAME` | Profile `name` comes from SAM when a SAM record exists (`010_sam_primary.sql` loads SAM rows first; transaction names fill in only on conflict-free gaps). Archive `recipient_name` | `auditee_name` (pre-filled from SAM since May 2026 per `federal-audit-clearinghouse.md`) | None |
| **DBA name** | col 13 `DBA NAME` (Optional) | **Not exposed for assistance.** USAspending stores it (`duns.dba_name`, `restock_duns.sql`), but no assistance download column or recipient endpoint returns it. The only `dba_name` download columns are FPDS contracts and subawards (`download_column_historical_lookups.py`, `subaward_search` d1/d2). Profile `alternate_names` are **transaction-reported** names, not DBA (`100_finalize.sql`: `array_agg(DISTINCT awardee_or_recipient_legal)` from transactions) | None | **Yes, new**. Fill rate for our Recipients is UNVERIFIED (needs the extract) |
| Division name | col 14 `ENTITY DIVISION NAME` | No | No | New. Value for matching UNVERIFIED |
| **Physical address** | cols 16–23 (line 1/2, city, state, ZIP, ZIP+4, country, CD) | **Already republished**: profile `location` is from SAM `coreData.physicalAddress` (broker `SAM_ENTITY_MAPPINGS` → `sam_recipient` → USAspending `duns` → `recipient_lookup`). Archive `recipient_address_*` is the ED-submitted FABS address | `auditee_address_line_1`, city, state, ZIP | None, except freshness (monthly vs. USAspending's refresh) |
| Mailing address | cols 40–46 | No | No | New, low matching value |
| **Business types** | col 32 `BUS TYPE STRING` (`~`-delimited; codes incl. `H6` School District, `M8` Educational Institution, `1R` Private University or College, `OH` State Controlled IHL, `HB` HBCU, `HS` Tribal College, `GW` Hispanic Servicing Institution, `G6/G7/G8` land grant, `1A` Minority Institution, `A8` Non-Profit, `12` U.S. Local Government, `2F` U.S. State Government, `C6/C7/C8` municipality/county/city): workbook "STRING Clarification" tab | **Collapsed.** Profile `business_types` maps SAM codes via `get_business_categories(..., "fpds")`: `H6` becomes only `local_government` (no school-district category); `1R` → `private_institution_of_higher_education`; `OH`/land-grant → `public_institution_of_higher_education`; `HB`/`HS`/`GW`/`1A` → `minority_serving_institution_of_higher_education`; `M8` → `educational_institution`. The profile also unions in the latest transaction's categories, so the result mixes sources (`recipients.py` `extract_business_categories`). Archive `business_types_code` is the **ED-submitted FABS** single letter (A–X), not SAM | `entity_type`: `higher-ed`, `local`, `non-profit`, `state`, `tribal`, `unknown` | **Partial.** Raw `H6` (K-12 district) and the specific MSI flags are new. Public/private IHE and nonprofit are already available |
| Entity structure | col 28 (`2J`, `2K`, `2L`, `8H` Corporate Entity (Tax Exempt), `2A` U.S. Government Entity, `CY`, `X6`, `ZZ`) | Not exposed as a field. It does leak into profile `business_types`: `extract_business_categories` appends it to the code list, so `2A` → `national_government` and `8H` → `corporate_entity_tax_exempt` (§4) | No | New as a raw code; low value (public vs. tax-exempt is already implied by FABS/FAC type and the profile categories) |
| **CAGE** | col 4 `CAGE CODE` | **No** for assistance (only in FPDS contract downloads) | No | New, but **no join partner** in our stack (IPEDS, CCD, FAC and ED lists carry no CAGE). No matching value |
| Entity URL | col 27 `ENTITY URL` (Optional) | No | No | **New.** Could join to IPEDS `WEBADDR` ("Institution's internet website address", HD2024 dict). Whether CCD LEA files carry a website is UNVERIFIED |
| Parent / hierarchy | **Not in public file** (hierarchy is FOUO, `entity-and-geo-sources.md` A1) | **Yes**: archive `recipient_parent_uei/name` and profile `parent_uei`. Broker derives them from SAM *FOUO* (`load_sam_recipient.py`: `DATA_TYPES = {"recipient": "FOUO", ...}`; V2 cols 199–201 `ultimate_parent_*`) | Consolidated audits list campus UEIs in `additional_ueis` | **Negative**: USAspending gives more than the public extract |
| EIN/TIN | No (Sensitive tier) | No | `auditee_ein`, `additional_eins` | FAC is the only source |
| Registration dates / status | cols 6–11 (`SAM EXTRACT CODE` A/E, initial reg, expiration, last update, activation), col 7 purpose of registration | No | No | New, not needed for matching |
| D&B provenance | col 24 `D&B OPEN DATA FLAG`, col 122 `ENTITY EVS SOURCE` | No | No | Needed only to apply the D&B clause to SAM rows |
| Opted-out entities | Excluded: `NO PUBLIC DISPLAY FLAG` col 119 (`NPDY`), and the public extract holds only "publicly available entities" (open.gsa.gov extracts page) | Profile still shows them if SAM-loaded (broker reads FOUO, which includes opt-outs) | n/a | **Negative**: USAspending can cover Recipients the public file omits |
| Points of contact | cols 47–112 (names, titles, street addresses) | (exec-comp officers in archive; also individuals) | certifier/contact columns | **Do not ingest** (individuals) |
| NAICS / PSC / SBA types | cols 33–37, 117–118 | No | No | Not relevant |

Unique identifiers that tie a Recipient to a Host institution:
- **IPEDS `UEIS`.** Dictionary: "Multiple UEI numbers are separated by the vertical bar."
- **IPEDS `EIN`.**

SAM has neither UNITID nor LEAID.

## 2. What USAspending already republishes from SAM (code trace)

1. **Broker load.** `data-act-broker-backend/dataactcore/utils/sam_recipient.py` maps SAM fields into `sam_recipient`:
   - `entityRegistration.dbaName` → `dba_name`
   - `coreData.generalInformation.entityStructureCode` → `entity_structure`
   - `coreData.physicalAddress.*` → `address_line_1`…`zip4`, `country_code`
   - `coreData.businessTypes.businessTypeList` → `business_types_codes`
   - `coreData.entityHierarchyInformation.ultimateParentEntity.*` → `ultimate_parent_*`

   For files, the V2 column mapping reads `dba_name` at index 12, `entity_structure` at 29, `business_types_raw` at 33, and `ultimate_parent_uei` at 200. Those indexes match the FOUO layout, and the script requests FOUO (`load_sam_recipient.py`).
2. **USAspending copy.** USAspending copies these into its `duns` table, keeping `dba_name`, `entity_structure` and `business_types_codes` (`usaspending_api/broker/management/sql/restock_duns.sql`).
3. **Recipient lookup.** `recipient_lookup` takes from SAM only:
   - name
   - physical address
   - congressional district
   - `business_types_codes`
   - parent

   It has **no DBA, entity-structure or CAGE column** (`recipient/models.py` `RecipientLookup`; `recipient_lookup/010_sam_primary.sql`).
4. **API output.** The recipient profile API (`GET /api/v2/recipient/<hash>-<level>/`) returns:
   - `name`
   - `alternate_names` (transaction names)
   - `location` (from `recipient_lookup`)
   - `business_types` (collapsed categories)
   - parent fields

   (`recipient/v2/views/recipients.py`.)
5. **FABS fields per transaction.** FABS transactions get only parent UEI/name and executive compensation from SAM (`fabs_derivations_helper.py` `derive_parent_uei`, `derive_executive_compensation`). The transaction address and `business_types` are what ED submitted.

So:
- **SAM's physical address and parent already reach us** through USAspending, without a SAM key.
- **DBA, raw business-type codes and entity structure** reach USAspending's database, but not its public outputs for assistance.

## 3. FY2024 TRIO/GEAR UP Recipient sample

Universe:
- FY2024 ED archive rows with `cfda_number` in 84.042/044/047/066/217/334/103 and awarding agency `091`.
- **4,403 transactions, 1,345 distinct Recipient UEIs, $1,489.8M** in summed `federal_action_obligation`.
- Every Recipient has a FABS street address; 1,310 have ZIP+4.
- 449 have a parent UEI on some row (243 of those are their own parent).

**ED-submitted FABS business type**, using each Recipient's most common code; only 1 UEI has more than one code:

| FABS code | Meaning (broker `BUSINESS_TYPE`) | Recipients |
|---|---|---|
| H | Public/State Controlled IHE | 657 |
| O | Private IHE | 213 |
| G | Independent School District | 201 |
| M | Nonprofit with 501C3 | 103 |
| B | County Government | 57 |
| C | City or Township Government | 39 |
| A | State Government | 33 |
| Q | For-Profit (Other than Small Business) | 16 |
| X | Other | 12 |
| R / I / D | Small Business / Tribal Gov. / Special District | 6 / 6 / 2 |

**ED's `G` is not "K-12 district".** 137 of the 201 `G` Recipients have a UEI in IPEDS HD2024. Examples are "SAUK VALLEY COMMUNITY COLLEGE", "DALLAS COLLEGE" and "HARTNELL COMMUNITY COLLEGE DISTRICT".

Conversely, K-12 bodies appear under other codes:
- `B`: "WELD COUNTY SCHOOL DISTRICT 6", "DOUGHERTY COUNTY SCHOOL SYSTEM".
- `C`: "BOARD OF EDUCATION CITY OF CHICAGO", "METROPOLITAN NASHVILLE PUBLIC SCHOOLS".

This is where SAM's `H6` could add a cleaner K-12 flag. Whether these Recipients actually carry `H6` in SAM is **UNVERIFIED** (needs the extract).

## 4. Coverage without SAM: IPEDS `UEIS` + FAC

Data: IPEDS HD2024 has 6,072 institutions, 5,537 with a non-empty `UEIS`, and 5,088 distinct UEIs. FAC uses audit years 2022–2025, with the UEI as either `auditee_uei` or `additional_uei`.

| FABS code | Recipients | IPEDS + FAC | IPEDS only | FAC only | Neither |
|---|---|---|---|---|---|
| H | 657 | 515 | 44 | 78 | 20 |
| O | 213 | 180 | 9 | 23 | 1 |
| G | 201 | 129 | 8 | 58 | 6 |
| M | 103 | 20 | 0 | 51 | 32 |
| B | 57 | 41 | 1 | 14 | 1 |
| C | 39 | 29 | 1 | 5 | 4 |
| A | 33 | 8 | 1 | 23 | 1 |
| other (Q, X, I, R, D) | 42 | 13 | 1 | 15 | 13 |
| **All** | **1,345** | **935** | **65** | **267** | **78** |
| share of FY2024 obligations | | 66.0% | 5.9% | 25.2% | 2.9% |

What the table shows:
- **IPEDS reaches 1,000 Recipients (74%) directly.** It gives UEI → UNITID with no name matching. 962 of those UEIs map to exactly one UNITID. Some are systems: one UEI maps to 22 UNITIDs, which is the Recipient ≠ Host institution case.
- **345 Recipients ($418.8M, 28%) have no IPEDS UEI hit.** These are where a SAM DBA, URL or `H6` could help matching. 267 of them are in FAC, which gives a second name and address, an `entity_type` and an EIN.
- **The 78 in neither source** are mostly nonprofits (`M` 32) plus odd cases. Examples are "IDAHO STATE BOARD OF EDUCATION", "GADSDEN STATE COMMUNITY COLLEGE", "UTAH STATE UNIVERSITY" and "RESEARCH FOUNDATION OF THE CITY UNIVERSITY OF NEW YORK". USAspending still gives each of them a name, address and FABS type.

**SAM-derived fields USAspending already republishes.** I called `GET /api/v2/recipient/<md5("uei-"+UEI)>-<R|C|P>/?year=2024` once per Recipient (1,345 calls, unauthenticated; all 1,345 returned: 1,133 at level `R`, 212 at level `C`).

- **Address:**
  - Profile `location` (SAM physical address where a SAM record exists) has the same street and ZIP5 as the ED-submitted FY2024 transaction address for **1,226** Recipients.
  - It differs for **119**, and of those the ZIP5 differs for 71.
  - So, versus the FABS address, SAM's physical address adds a second address for about 9% of Recipients, and USAspending already provides it.
- **Names:**
  - Profile `name` differs from the transaction `recipient_name` for only 2 Recipients.
  - 1,131 have at least one `alternate_names` value (median 2). These are transaction-reported variants, not SAM DBA.
- **Parent:** 212 profiles carry `parent_uei`.
- **Business types:**
  - 1,213 of 1,345 profiles carry at least one category that the FABS mapping never produces (`educational_institution`, `national_government`, `school_of_forestry`, `veterinary_college`, `council_of_governments`, `interstate_entity`). These come from the SAM-code (FPDS-style) mapping.
  - This means USAspending holds a SAM business-type record for roughly that many Recipients. It is not an exact count: an FPDS contract transaction could also produce these categories.
  - `national_government` appears on 812 profiles. The likeliest source is SAM entity structure `2A` "U.S. Government Entity": `extract_business_categories` appends `entity_structure` to the code list, and `2A` maps to `us_government_entity` and then to `national_government`. Likewise `corporate_entity_tax_exempt` (412) comes from `8H`.
  - **Entity structure therefore leaks through in coarse form.**
  - **No profile category distinguishes a school district.** `H6` maps only into `local_government` (379 profiles).

**Among the 345 non-IPEDS Recipients**, the FABS codes are H 98, M 83, G 64, A 24, O 24, B 15, X 11, C 9, Q 9, R 6, D 2. The profile categories for this group already include `nonprofit` (180), `public_institution_of_higher_education` (138), `local_government` (100) and `regional_and_state_government` (98). The residual that SAM's raw codes would sharpen is mainly **K-12 district vs. other local government**, the 64 `G` + 15 `B` + 9 `C` = 88 Recipients, plus DBA and URL for name matching.

## 5. What a SAM account would be needed to check

- **Account and key** (https://open.gsa.gov/api/sam-entity-extracts-api/):
  - A free non-federal individual SAM.gov account.
  - The "Public API Key" from `https://sam.gov/workspace/profile/account-details`. Sent as the `x-api-key` header.
  - Default limit for a "Non-federal user with no Role in SAM.gov": 10 requests/day.
- **Download:** one call to `https://api.sam.gov/data-services/v1/extracts?fileName=SAM_PUBLIC_MONTHLY_V2_<YYYYMMDD>.ZIP`. Monthly files are produced on the first Sunday of the month and "contain all active entities and entities expired in the last 6 months" (same page). Then join on UEI to the 1,345 Recipients and count:
  1. Present in the file at all. Absent means opted out (`NPDY`), expired more than 6 months, or never registered.
  2. `DBA NAME` non-empty, and whether it differs from the legal name and from USAspending `alternate_names`.
  3. `ENTITY URL` non-empty, and the domain match rate to IPEDS `WEBADDR` for the 1,000 IPEDS-linked Recipients. This shows how well URL would work for the 345 that are not linked.
  4. `H6` among the 345 non-IPEDS Recipients and among FABS `G`/`B`/`C`. `M8`/`1R`/`OH` among FABS `G`.
  5. `ENTITY EVS SOURCE = 'D&B'` or `D&B OPEN DATA FLAG = 'Y'` counts (licensing, §6).
  6. Physical address vs. the USAspending profile `location`, to confirm they are the same SAM value.
- **Handling:** drop POC columns 47–112 on read. Keep the key personal and rotate it every 90 days (ToU).
- **Not a substitute:** the synchronous Entity API (`ueiSAM` up to 100 values per call) would need 14 calls for 1,345 UEIs, which is over the 10/day limit. The extract is the right path.

## 6. Licensing: the D&B clause and an internal analysis shared with one business

**SAM.gov Terms of Use** (https://sam.gov/about/terms-of-use, fetched 2026-10-14):

- **Scope (plain-language section).**
  - "D&B Open Data may be in entity registration records last updated before April 4, 2022 … Entity registration records with D&B data show that data source in APIs and extracts."
  - The legal text says the same: "Applicable records containing D&B data include all entity registration records with a last updated date earlier than 4/4/2022 … These records show D&B as the Entity Validation Service (EVS) Source".
- **Limits on those records.**
  - Open Data: "You must state in writing that D&B is the data source", and "You may not share D&B Open Data in bulk (that is, enough records that someone could use them as an original data source or a substitute for getting data from D&B)".
  - Everything else from D&B: "Except for data elements identified above as D&B Open Data, under no circumstances are you authorized to use any other D&B data for commercial, resale or marketing purposes (e.g., identifying, quantifying, segmenting and/or analyzing customers and prospective customers)."
  - D&B Open Data = legal business name, street address, city, state/province, country, county code, ZIP.
- **Other SAM terms that bear on us:**
  - "If you want to share data publicly, only share data from public versions of APIs."
  - "Do not share your individual account API key with anyone."
  - "Update your API key … every 90 days."
  - "Automated data gathering, web scraping tools are prohibited", with the sanctioned channels being open.gsa.gov APIs and sam.gov/data-services.
  - The NDA's "shall not use such data for commercial purposes" binds Data Receivers of CUI (FOUO/Sensitive), not public-extract users.
  - I found no commercial-use limit on public, non-D&B SAM data.

**Reading for our use** (internal analysis of prospective customers, shared with one small business):
1. **Non-D&B SAM rows (expected: essentially all rows in a current monthly file).** No D&B restriction applies. The remaining duties are general ToU duties: use the API, keep the key personal, and share only public-tier data.
   - Inference (UNVERIFIED): column 9's definition says expiration is "365 days after the user submitted the registration", and the monthly public file holds only active registrations plus those expired in the past 6 months. So every record should have been submitted (and therefore last updated) within roughly the last 18 months, which puts it after 2022-04-04. Verify with `ENTITY EVS SOURCE`.
2. **Any D&B-sourced row.** The non-Open-Data D&B fields fall under a ban whose example ("identifying, quantifying, segmenting and/or analyzing … prospective customers") describes this project. Under SAM's definitions those fields are anything other than name and address. The clause has **no exception for internal or small-audience use**. "Commercial" turns on purpose, not audience size.
   - For Open Data fields (name, address), internal use is allowed with written D&B attribution. Sharing a full Recipient list with the business could be "bulk" if it is "enough records that someone could use them as an original data source". The clause does not define a number. **Ambiguous**; the safe course is to drop or flag D&B-source rows.
3. **USAspending's copy of the same clause is broader.** https://www.usaspending.gov/db-info (source `src/js/components/about/DBInfo.jsx`) uses the same commercial ban and the same bulk/attribution terms, but:
   - It has **no April 2022 date limit**.
   - It says D&B data "includes each entity's DUNS Number and its associated business information".

   So:
   - **(a) Legacy DUNS numbers** from USAspending (`recipient_duns`, profile `duns`) are D&B data *outside* Open Data. Using them to link pre-2022 Grants in a prospect analysis reads as a "commercial … marketing" use. `usaspending-trio-gearup.md` §5.2 suggests "Bridge older years via the recipient profile's duns + uei". Prefer bridging through FAC or IPEDS UEIs, or through FAIN successions, and do not carry DUNS into the deliverable.
   - **(b)** Whether USAspending's notice reaches post-2022, SAM-validated name and address fields is not stated; the notice does not distinguish them. **Ambiguous**. Giving D&B attribution on any recipient name/address list from USAspending costs little.
4. **SAM adds no new licensing risk** beyond what USAspending already carries, provided D&B-source rows are flagged.

## Open questions / UNVERIFIED

1. Fill rates of `DBA NAME`, `ENTITY URL` and `H6` for our 1,345 Recipients, and how many are missing from the public file (opt-outs, lapsed registrations). This needs the extract (§5).
2. Whether any current-file rows still show `ENTITY EVS SOURCE = D&B`. Inferred to be near zero; not verified.
3. Whether the CCD LEA directory carries a website field that SAM `ENTITY URL` could join to. Not checked.
4. **Workbook currency.** The public layout workbook linked from open.gsa.gov is v6.0 (server Last-Modified 2022-10-25). The page changelog (v3.4, 09/11/2023) says the "SAM Master Extract Mapping document" was removed, but the v6.0 Public layout is still linked. I did not check whether the current file's columns match the workbook.
5. **Is FAC `auditee_name` really SAM's?** It is said to be SAM-prefilled only since May 2026 (`federal-audit-clearinghouse.md`). Not re-checked here.
6. **Recipient vs. Host institution for systems.** IPEDS `UEIS` maps some system UEIs to many UNITIDs (one UEI → 22). SAM does not resolve this; Host institution must come from ED grantee lists or place of performance.
7. **Legal read.** Two questions:
   - Does USAspending's D&B notice cover legacy DUNS used only as an internal join key, never shown?
   - What number of name/address rows counts as "bulk"?

   Both are ambiguous in the text. Ask datause_govt@dnb.com (the contact named in both notices) or counsel.

Scripts and downloads were throwaway (`/tmp/samx_scripts/`, `/tmp/samx_data/`) and are not committed.
