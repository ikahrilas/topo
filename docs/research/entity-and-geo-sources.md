# Entity and geo sources for address and location matching

Researched 2026-10-14. Live calls were made that day against `geocoding.geo.census.gov`, `www2.census.gov`, `nces.ed.gov`, `open.gsa.gov`, the `sam.gov` file-listing backend, and the GitHub API. No accounts were created and no keys were used. **UNVERIFIED** marks anything I could not confirm from a primary source.

## Recommendation

1. **Entity attributes: SAM.gov public monthly extract.** Use `SAM_PUBLIC_MONTHLY_V2_YYYYMMDD.ZIP` (pipe-delimited, one file per month). Join it to USAspending on UEI to get the legal name, DBA, physical and mailing address, entity structure, and business-type codes. The codes include `H6` School District, `M8` Educational Institution, `1R` Private University or College, and `OH` State Controlled Institution of Higher Learning.
   - Downloading needs a free personal SAM.gov API key. **A person on the team has to create the account; this research did not.**
   - At 10 requests/day, a no-role key covers one extract download plus a few lookups.
   - Public data is unclassified/FOIA. EIN/TIN is in the Sensitive tier only, so it is not in the public data.
   - Use API/extract downloads only. SAM.gov's Terms of Use ban scraping.
2. **Reference points: NCES EDGE geocodes, not our own geocoding.** EDGE publishes lat/long keyed by `LEAID` (2024-25), `NCESSCH` (2024-25), and `UNITID` (2025-26).
3. **Recipient points: Census Geocoder batch.** Send one file (≤10,000 rows) with our ~5,000 recipient addresses. Then run a point-in-polygon join in **DuckDB spatial** against school-district polygons whose year matches the CCD year we use:
   - EDGE composite 2025 / TIGER 2025 = SY 2024-25.
   - TIGER 2026 = districts as of Jan 1, 2026.

   For district polygons, `GEOID` = `LEAID` except for pseudo-districts and temporary codes.
4. **Scoring and review: Splink 5.0.0 on DuckDB** (`link_type="link_only"`). Block on state, and compare name, address, and point distance. Choose the threshold from a hand-labelled sample using `accuracy_analysis_from_labels_table(output_type="threshold_selection")`. Our scale is tiny for Splink.
5. **D&B restrictions now cover only legacy records.** They apply to SAM records whose EVS source is D&B, meaning registrations last updated before 2022-04-04. Filter or flag on `ENTITY EVS SOURCE` / `evsSource`, and give D&B attribution for any such rows we republish.

---

## Part A: SAM.gov entity data

### A1. Public fields

**Entity Management API (`/entity-information/v1`–`v4`)**, per https://open.gsa.gov/api/entity-api/:

- Overview: "Public Data: This constitutes publicly available entities and their unclassified data such as name, UEI, registration details, physical and mailing addresses, business types, PSC, NAICS and points of contact name and address."
- FOUO adds "entities that have opted out of public display" plus "hierarchy, company and employee security levels and points of contact email address, phone, and fax numbers."
- Sensitive adds "banking information and SSN/TIN/EIN".

Response-schema sensitivity labels on that page:

| Section / field | Sensitivity |
|---|---|
| `entityRegistration`: `ueiSAM`, `cageCode`, `legalBusinessName`, `dbaName`, `purposeOfRegistrationCode/Desc`, `registrationStatus`, `registrationDate`, `lastUpdateDate`, `registrationExpirationDate`, `activationDate`, `ueiStatus`, `ueiCreationDate`, `publicDisplayFlag`, `exclusionStatusFlag`, `evsSource`, `dnbOpenData` | Public |
| `coreData.physicalAddress` (addressLine1/2, city, stateOrProvinceCode, zipCode, zipCodePlus4, countryCode), `coreData.mailingAddress`, `congressionalDistrict` | Public |
| `coreData.generalInformation`: `entityStructureCode/Desc`, `entityTypeCode/Desc`, `profitStructureCode/Desc`, `organizationStructureCode/Desc`, `stateOfIncorporationCode` | Public |
| `coreData.entityInformation`: `entityURL`, `entityDivisionName`, `entityStartDate`, `fiscalYearEndCloseDate` | Public |
| `coreData.businessTypes` | Public |
| `entityHierarchyInformation` (immediate/ultimate parent) | **FOUO** |
| `tinInformation`: `taxpayerName`, `taxpayerIdentificationType`, `taxpayerIdentificationNumber` | **Sensitive** |

So EIN/TIN is **excluded from the public tier** (confirmed). Note also that **parent hierarchy is FOUO**, so the public tier does not give us the parent-entity linkage.

**Public V2 extract layout** (`SAM Master Extract Mapping v6.0 Public File V2 Layout.xlsx`, https://open.gsa.gov/api/sam-entity-extracts-api/v1/SAM%20Master%20Extract%20Mapping%20v6.0%20Public%20File%20V2%20Layout.xlsx; the workbook was last modified 2021-11-04):

- 142 columns. Every one is labelled `Public`.
- Columns relevant to matching: `UNIQUE ENTITY ID` (col 1), `CAGE CODE` (4), `SAM EXTRACT CODE` (6), `PURPOSE OF REGISTRATION` (7), `INITIAL REGISTRATION DATE` / `REGISTRATION EXPIRATION DATE` / `LAST UPDATE DATE` / `ACTIVATION DATE` (8–11), `LEGAL BUSINESS NAME` (12), `DBA NAME` (13), `ENTITY DIVISION NAME` (14), `PHYSICAL ADDRESS LINE 1/2, CITY, PROVINCE OR STATE, ZIP, ZIP+4, COUNTRY, CONGRESSIONAL DISTRICT` (16–23), `D&B OPEN DATA FLAG` (24), `ENTITY URL` (27), `ENTITY STRUCTURE` (28), `STATE OF INCORPORATION` (29), `BUS TYPE STRING` (32, `~`-delimited), `PRIMARY NAICS` (33), `MAILING ADDRESS …` (40–46), POC names and street addresses (47–112), `NO PUBLIC DISPLAY FLAG` (119), `ENTITY EVS SOURCE` (122).
- There is **no TIN/EIN column and no separate "entity type" column**. Business types come only through `BUS TYPE STRING`.
- From the workbook's code tab: `12` U.S. Local Government, `H6` School District, `M8` Educational Institution, `1R` Private University or College, `OH` State Controlled Institution of Higher Learning, `HB` HBCU, `HS` Tribal College, `A8` Non-Profit Organization.
- `SAM EXTRACT CODE`: the monthly file has `A` (Active) and `E` (Expired). The daily file uses codes 1–4.
- `D&B OPEN DATA FLAG`: "This flag indicates whether the Business Name and Physical Address sourced from D&B."

### A2. Access, rate limits, formats, cadence, sensitivity

- **Key.** Public data needs a personal SAM.gov account key: "obtain the API Key from the https://sam.gov/workspace/profile/account-details page using the field, 'Public API Key'". A non-federal system account with "Read Public" also works. FOUO and Sensitive need a *Federal* System Account. Source: https://open.gsa.gov/api/entity-api/ and https://open.gsa.gov/api/sam-entity-extracts-api/.
  - Neither page mentions api.data.gov keys, so it is **UNVERIFIED** whether an api.data.gov key works.
  - Live test: `GET https://api.sam.gov/entity-information/v4/entities?ueiSAM=…` returned HTTP 404 with an empty body both with no key and with `api_key=DEMO_KEY`.
- **Daily rate limits** (same table on both pages):

  | Account | Key | Limit |
  |---|---|---|
  | Non-federal, no SAM.gov role | personal | 10/day |
  | Non-federal, with role | personal | 1,000/day |
  | Federal user | personal | 1,000/day |
  | Non-federal system account | system | 1,000/day |
  | Federal system account | system | 10,000/day |

- **API modes** (https://open.gsa.gov/api/entity-api/):
  - Synchronous JSON returns "ten records per page" and "only the first 10,000 records".
  - Adding `format=csv|json` makes it an asynchronous extract that "can return only the first 1,000,000 records".
  - `ueiSAM` "Allows a single 12-character value or up to 100 values."
  - Current version is v4 (changelog v4.6, 12/06/2024).
- **Bulk files** (https://open.gsa.gov/api/sam-entity-extracts-api/):
  - Names: `SAM_PUBLIC_MONTHLY_V2_YYYYMMDD.ZIP` and `SAM_PUBLIC_UTF-8_MONTHLY_V2_YYYYMMDD.ZIP`, downloaded via `https://api.sam.gov/data-services/v1/extracts?fileName=…`.
  - Cadence: monthly files are produced on the first Sunday of the month. The public monthly is "a refresh file for all active registration records and those which expired in the past six months".
  - There is **no public daily entity file**. Daily entity files exist only at the FOUO/Sensitive tiers (Tue–Sat).
  - The SAM.gov file listing (`https://sam.gov/api/prod/fileextractservices/v1/api/listfiles?domain=Entity%20Registration%2FPublic%20V2&privacy=Public`, one live call) shows the latest file as `SAM_PUBLIC_MONTHLY_V2_20261005.ZIP` (dated Oct 04, 2026). Its `fileFormat` is "ZIP, Pipe-Delimited", and its description is "entity registration data publicly available under the Freedom of Information Act (FOIA)".
  - Direct S3 access to that file returned HTTP 403, so the download really does need the API key.
- **Sensitivity.** The public extract and API are unclassified/FOIA data and are **not FOUO**. Entities that opted out of public display (`NPDY`) appear only at the FOUO tier and above, so the public file will be missing some entities (https://open.gsa.gov/api/entity-api/). How many ED grantees opted out is **UNVERIFIED**.

### A3. Terms of use and D&B restrictions

Source: SAM.gov Terms of Use (server-rendered), https://sam.gov/about/terms-of-use.

- **Scraping.** "Automated data gathering, web scraping tools are prohibited and, if detected, will result in the associated account(s) being denied access." The sanctioned channels are "https://open.gsa.gov/api/" and "https://sam.gov/data-services". Also: "Do not use your SAM.gov login for data mining, bots, or other data gathering and extraction tools."
- **Keys.** "Update your API key and system account password every 90 days. Do not share your individual account API key with anyone."
- **Publishing.** "If you want to share data publicly, only share data from public versions of APIs."
- **Commercial use.** The Non-Disclosure Agreement's ban on commercial use ("shall not use such data for commercial purposes") applies to **Data Receivers of CUI** (FOUO/Sensitive). I found **no commercial, marketing, or bulk restriction on public, non-D&B SAM data**. A legal read is still advisable (see Open questions).
- **D&B after the UEI transition.** The restrictions still exist but are now scoped to legacy records:
  - "D&B Open Data may be in entity registration records last updated before April 4, 2022, and exclusion records created before April 4, 2022. Entity registration records with D&B data show that data source in APIs and extracts."
  - Legal language: "all entity registration records with a last updated date earlier than 4/4/2022 … These records show D&B as the Entity Validation Service (EVS) Source."
  - Limits on those records:
    - Written attribution to D&B is required.
    - No bulk use of D&B Open Data ("in amounts sufficient for use as an original source or as a substitute").
    - D&B data *other than* Open Data may not be used "for commercial, resale or marketing purposes (e.g., identifying, quantifying, segmenting and/or analyzing customers and prospective customers)".
  - D&B Open Data = legal business name, street address, city, state, country, county code, and ZIP.
  - **Practical rule:** drop or flag rows where `ENTITY EVS SOURCE = 'D&B'` (`evsSource`) or `D&B OPEN DATA FLAG = 'Y'`.
  - Inference (**UNVERIFIED**): SAM registrations must be renewed, so most *active* registrations were probably updated after 2022-04-04 and are no longer D&B-sourced. Check the actual count once we have the file.
  - The USAspending-side D&B notice (https://www.usaspending.gov/db-info) is covered in `source-terms-and-cadence.md`. That page does not carry the 2022 date scoping.

---

## Part B: Geocoding and boundaries

### B1. Census Geocoder (geocoding.geo.census.gov)

- **Batch limit.** "There is currently an upper limit of 10,000 records per batch file." Larger jobs must be split (https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html, "Last updated 02/2026"; FAQ https://www2.census.gov/geo/pdfs/maps-data/data/Census_Geocoder_FAQ.pdf).
  - Batch input is CSV/TXT/DAT/XLS(X) with columns `Unique ID, Street address, City, State, ZIP`.
  - The FAQ warns that re-running the same batch can give different match counts under load. It recommends resubmitting only the unmatched rows.
- **School districts come back from single-record calls only.**
  - Single-record `geographies` calls with `layers=all`, or with the named layers (`Unified School Districts`, `Secondary School Districts`, `Elementary School Districts`), return the district `GEOID` directly.
  - **Batch `geographies` does not:** "Batch geoLookup only includes state, county, tract, and block code. Currently there is no way to request additional geographies" (API doc). A coordinates batch has the same limit.
  - So for 5,000 rows: batch-geocode to get lat/lon, then do our own point-in-polygon join (B4). Making 5,000 single calls is the alternative.
- **Live tests.**
  - Single call: `geographies/onelineaddress?address=4202 E Fowler Ave, Tampa, FL 33620&benchmark=Public_AR_Current&vintage=Current_Current&layers=all`.
    - It matched `4202 E FOWLER AVE, TAMPA, FL, 33612` at (-82.41420, 28.05451), `tigerLineId` 656645232, side L.
    - Unified School Districts: `GEOID 1200870`, "Hillsborough County School District", `LOGRADE PK`, `HIGRADE 12`, `SDUNI 00870`, `FUNCSTAT E`, `MTFCC G5420`. `1200870` is Hillsborough's NCES LEAID in EDGE.
  - Coordinates call in Tempe, AZ: returned both a Secondary district (`0408340` Tempe Union HSD, 09–12) and an Elementary district (`0408310` Tempe SD, PK–08). Both IDs are present as LEAIDs in EDGE.
  - Two-row batch: output columns were `id, input, Match, Exact|Non_Exact, matched address, "lon,lat", tigerLineId, side, state, county, tract, block`, with no district.
- **Benchmarks and vintages** (live `GET /geocoder/benchmarks`):
  - Benchmarks: `Public_AR_Current` (default), `Public_AR_ACS2026`, `Public_AR_Census2020`, `Public_AR_LUCA`.
  - Vintages under Current: `Current_Current`, `Census2010_Current`, `ACS2017_Current` … `ACS2026_Current`.
  - Benchmarks are refreshed "twice a year" (FAQ).
  - **Vintage matters for districts.** At Grangeville, ID, `Current_Current` and `ACS2026_Current` return `1699501` (a TIGER 2026 temporary code, not in the EDGE 2024-25 LEA file), while `ACS2025_Current` returns `1600139` Mountain View SD 244, which *is* in EDGE 2024-25. Pick the vintage that matches the CCD year.
- **Method.** "Coordinate results are interpolated, or approximated" from MAF/TIGER address ranges (https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html, revised May 19, 2026). For USF, the Census point is about 0.8 km from the EDGE/IPEDS point (28.061458, -82.413232). Treat large campuses with a distance tolerance, not an exact point match.
- **Terms.** No geocoder-specific terms of service or rate limit appear on the geocoder site, the API doc, the FAQ, or the documentation page (**UNVERIFIED** that none exist). Census works are not copyrighted (TIGER doc §1.2, below).

### B2. NCES EDGE geocodes

Source: https://nces.ed.gov/programs/edge/Geographic/SchoolLocations. "EDGE creates and assigns address geocodes (estimated latitude/latitude values) … to public schools, public local education agencies, private schools, and postsecondary schools." Files ship as TXT (pipe-delimited, no header), XLSX, SAS, and shapefile.

| File | Latest posted | Key | Live check |
|---|---|---|---|
| Public schools | **2024-25** (`EDGE_GEOCODE_PUBLICSCH_2425.zip`, Last-Modified 2025-12-19). The 2025-26 link is commented out in the page HTML and returns HTTP 404 | `NCESSCH` (12), `LEAID` (7) | HEAD only |
| Public LEAs (district offices) | **2024-25** (`EDGE_GEOCODE_PUBLICLEA_2425.zip`). 2025-26 returns 404 | `LEAID` | 19,636 rows. Columns `LEAID, NAME, OPSTFIPS, STREET, CITY, STATE, ZIP, STFIP, CNTY, NMCNTY, LAT, LON, CBSA, …, CD, SLDL, SLDU, SCHOOLYEAR, LOCALE, PCT_*` |
| Postsecondary | **2025-26** (`EDGE_GEOCODE_POSTSECSCH_2526.zip`, Last-Modified 2026-09-25) | `UNITID` | 6,438 rows. Columns `UNITID, NAME, STREET, CITY, STATE, ZIP, STFIP, CNTY, NMCNTY, LOCALE, LAT, LON, CBSA, …, CD, SLDL, SLDU, SCHOOLYEAR` |

- **How the points are made.** Points come from the CCD-reported physical address, geocoded against "commercial and non-commercial address point information", with manual review of problem cases. Points "may potentially change, even if the reported address has not" (https://nces.ed.gov/programs/edge/docs/EDGE_GEOCODE_PUBLIC_TECHDOC.pdf, §2.0).
- **LEA points are office locations.** An LEA point is the *administrative office*, and its county and CD are assigned from that office. Full district-to-geography relationships are in the separate Geographic Relationship Files (§4.0).
- **Terms.** NCES documentation states: "Unless specifically noted, all information contained herein is in the public domain" (EDGE tech docs, front matter).

### B3. School district boundaries

**Census TIGER/Line.** https://www2.census.gov/geo/tiger/TIGER2026/{UNSD,ELSD,SCSD}/

- **Latest vintage is 2026.** The TIGER/Line page states: "The 2026 TIGER/Line Shapefiles were released on October 14, 2026" (https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html).
  - The state school-district zips in the directory are timestamped 2026-10-06. `tl_2026_12_unsd.zip` contains `.shp` files dated 2026-09-24.
  - Per the 2026 technical doc, "These shapefiles represent boundaries and attributes of school districts in operation as of January 1, 2026" (https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2026/TGRSHP2026_TechDoc.pdf, p. 4-42). The 2025 doc says its files contain "information from the 2024-2025 school year".
- **Formats:** state-based shapefiles (`tl_2026_<STATEFP>_unsd.zip`, etc.), plus state geodatabases (`TGRGDB26/`, dated 2026-07-29) and GeoPackages (`TGRGPKG26/`) under https://www2.census.gov/geo/tiger/.
- **Fields** (Appendix P): `STATEFP`, `ELSDLEA|SCSDLEA|UNSDLEA`, `GEOID` ("a concatenation of the state FIPS code and … SDLEA code"), `GEOIDFQ`, `NAME`, `LSAD`, `LOGRADE`, `HIGRADE`, `MTFCC`, `SDTYP`, `FUNCSTAT`, `ALAND`, `AWATER`, `INTPTLAT`, `INTPTLON`.
- **Codes that won't match a LEAID** (same doc, p. 4-42):
  - "SDLEA Code 99997 is assigned to water or land where the state has not defined an official school district."
  - "SDLEA codes starting with 995 are temporary codes created by the Census Bureau." In 2026 these are `99501` Grangeville SD 246 and `99502` Clearwater Valley SD 245, both in Idaho.
  - Pseudo-districts have `SDTYP = 'A'`.
- **Terms** (doc §1.1–1.2): no warranty. "TIGER/Line" is a registered trademark and may not be used in commercial product names. Repackaged distributions should carry a conspicuous statement to that effect. "Copyright protection is not available for any work of the United States Government … you are free to reproduce census materials."

**NCES EDGE composite school district boundaries.** https://nces.ed.gov/programs/edge/Geographic/DistrictBoundaries

- **Latest is 2025:** `EDGE_SCHOOLDISTRICT_TL25_SY2425.zip` (single composite, 207 MB) and `TL_2025_SD.zip` (layers by type, 169 MB). "Files represent the 2024-2025 school year and apply to the 2021-2025 ACS Period." There is no EDGE composite for TIGER 2026 yet.
- **Contents:** one national layer of Elementary, Secondary, Unified, and (Vermont-only) Administrative districts, clipped to the shoreline. It is a shapefile in NAD83 (https://nces.ed.gov/programs/edge/docs/EDGE_SDBOUNDARIES_COMPOSITE_TECHDOC.pdf).
- **Mapping to LEAID:** "GEOID … School district identifier; a concatenation of the current state FIPS code and school district local education agency code. **The GEOID is consistent with the NCES LEAID except in the case of pseudo-districts.**" The composite adds `SCHOOLYEAR` and `GEO_YEAR`.
- **Live check (FL, TIGER 2026 UNSD × EDGE 2024-25 LEA points):**
  - 85 FL LEA offices and 67 UNSD polygons. All 85 points fell inside a polygon.
  - For all 67 regular districts, the polygon `GEOID` equalled the LEA's own `LEAID`.
  - The other 18 LEAs (charter, state-operated, and similar) **have no boundary polygon**. Their offices sit inside a county district. Point-in-polygon can only resolve *geographic* districts.

### B4. Point-in-polygon in Python

A live run of the same FL join gave identical results with both tools: geopandas 1.2.0 `sjoin(predicate="within")` and DuckDB 1.5.6 + spatial `ST_Read('/vsizip/…')` + `ST_Contains`. The script is in `/tmp/topo_research/scripts/pip_test.py` and is not committed.

- **DuckDB spatial** (https://github.com/duckdb/duckdb-spatial):
  - Fits our DuckDB/Parquet stack. It reads shapefiles, GDB, and GPKG straight from zip through GDAL (`ST_Read`).
  - `EXPLAIN` showed a dedicated `SPATIAL_JOIN` operator. The optimizer recognises `ST_Contains`, `ST_Within`, `ST_Intersects`, `ST_DWithin`, and others (`src/spatial/operators/spatial_join_optimizer.cpp`). The repo also has an R-tree index (`src/spatial/index/rtree/`).
  - The README is stale and still says "No support for spatial indexing" (last README commit 2025-04-28). It also warns of planar-only geometry: "No support for spherical geometry", so compute distances in a projected CRS or with haversine.
  - Run time on the FL join was 0.03 s.
- **geopandas** (https://github.com/geopandas/geopandas, v1.2.0 released 2026-09-28):
  - It has a mature CRS handling story (`to_crs`) and built-in plotting for QA.
  - It means a pandas/shapely round-trip outside polars.
  - Run time on the FL join was 1.6 s, including the file read.
- **Choice.** At about 5,000 points against roughly 13,000 polygons, either works. Use DuckDB for the pipeline and geopandas only for ad-hoc maps or QA.
- **Caveats for both:**
  - Make sure points and polygons share a CRS. TIGER and EDGE are NAD83 (EPSG:4269). Census Geocoder output is lon/lat.
  - A point can fall in both an ELSD and an SCSD polygon (the Tempe example), so keep all hits.

---

## Part C: Splink

Source: https://github.com/moj-analytical-services/splink (MIT).

- **Version.** The current release is **v5.0.0**, published on GitHub 2026-09-18, and `pyproject.toml` has `version = "5.0.0"`. The CHANGELOG entry is dated 2026-09-28, which disagrees with the GitHub date. The prior line is v4.0.17 (2026-09-03).
- **Splink 5 breaking changes** (CHANGELOG):
  - Inputs must be registered with `db_api.register()` before they are passed to `Linker`.
  - Output prefixes change from `bf_` to `mw_`.
  - Python ≥3.10 is required (README still says 3.9+). Athena support is dropped.
  - Runtime dependencies are only DuckDB, PyArrow, and SQLGlot; pandas is optional.
  - New features: chunked prediction with "optional direct Parquet materialisation in DuckDB", plus `predict_between()` and `score_pairs()`.
  - Older blog posts and tutorials use the v4 API.
- **DuckDB backend.** DuckDB is the default and core backend (`core = ["sqlglot", "duckdb"]`). Spark and Postgres are extras. The repo includes a DuckDB `link_only` example (`docs/demos/examples/duckdb/link_only.nb.py`).
- **Scale.** The README says "Capable of linking a million records on a laptop in around a minute." Our job is 5k recipients × (6k IPEDS + 19.6k LEAs). Even an unblocked cross product is about 128M pairs, and blocking on state cuts that by roughly 50×. That is well within DuckDB on a laptop.
- **Clerical review:**
  - `linker.evaluation.labelling_tool_for_specific_record(unique_id, …)` writes a standalone, offline HTML labelling tool (`splink/internals/linker_components/evaluation.py`).
  - Labels go in a table with columns `source_dataset_l, unique_id_l, source_dataset_r, unique_id_r, clerical_match_score`.
  - The prose guide `docs/topic_guides/evaluation/labelling.md` says only "This page is under construction".
- **Threshold selection:**
  - `docs/topic_guides/evaluation/edge_overview.md` says to decide first whether precision or recall matters more, then use the Threshold Selection Tool. That tool "requires labelled data".
  - Then iterate by spot-checking pairs on either side of the threshold in the Comparison Viewer Dashboard and with `prediction_errors_from_labels_table`.
  - API: `accuracy_analysis_from_labels_table(labels, output_type="threshold_selection"|"roc"|"precision_recall"|"table"|"accuracy", add_metrics=[…f1, f2, …])`.
  - Doc: `docs/charts/threshold_selection_tool_from_labels_table.nb.py`.

---

## Open questions / UNVERIFIED

1. **SAM API key.** Someone on the team needs a SAM.gov account. Whether an api.data.gov key works is UNVERIFIED. The unauthenticated and `DEMO_KEY` calls returned 404. The 10/day no-role limit is enough for the monthly extract but not for per-UEI synchronous lookups (5,000 UEIs is 50 calls even at 100 UEIs per call).
2. **Opted-out entities.** How many of our ~5,000 recipients are `NPDY` (opted out), and therefore missing from the public extract, is UNVERIFIED.
3. **Active registrations still D&B-sourced.** The share of active registrations with EVS source D&B is UNVERIFIED (inferred to be small). Count it after the first download.
4. **Commercial use.** No commercial or marketing limit was found on *public, non-D&B* SAM data. Have a legal read confirm it for an education-services business-development use.
5. **Census Geocoder terms and rate limits.** None are published on the geocoder pages (UNVERIFIED that none exist). Which TIGER year backs `Current_Current` was inferred from the Grangeville test (it matches TIGER 2026). It was not documented.
6. **EDGE 2025-26 public school and LEA geocodes.** Not posted yet (HTTP 404). The release date is UNVERIFIED.
7. **Business-type codes.** The code list (`H6`, `M8`, `1R`, `OH`, …) is from the 2021 layout workbook. Re-check it against the current SAM Functional Data Dictionary (https://sam.gov/data-services/Data%20Dictionary/Entity%20Information is JS-rendered and was not read).
8. **sam.gov file-listing call.** One unauthenticated call was made to the `sam.gov/api/prod/fileextractservices` listing endpoint, the backend of the public data-services page. The pipeline should use the documented `api.sam.gov/data-services/v1/extracts` endpoint with a key instead. Do not use the `API_UMBRELLA_KEY` embedded in sam.gov's HTML.
