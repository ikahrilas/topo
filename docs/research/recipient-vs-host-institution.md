# Recipient vs. Host institution in USAspending TRIO and GEAR UP awards

Researched 2026-10-14. All data came from public bulk files downloaded that day (sources below), and everything is at the organization level. **UNVERIFIED** marks anything I could not confirm from a primary source.

**Terms.** The ticket points to `GLOSSARY.md`, but no `GLOSSARY.md` exists on `main`, on `docs/research-and-assumptions`, or anywhere in the repo history. I used the definitions given in the ticket:
- **Recipient**: the legal entity, keyed by UEI.
- **Grant**: one FAIN project period.
- **Host institution**: the college (IPEDS UNITID) or school district (NCES LEAID) where the project runs.
- **Program**: one of the listings below.

## Summary

- **How often Recipient ≠ Host.** Across FY2024 TRIO and GEAR UP Grants, about **31%** of Grants have a Recipient that is a different organization from the Host institution, or have no single Host institution at all. This is a weighted estimate from a 160-Grant stratified sample, with a bootstrap 95% interval of 22–41%. Section 3 gives the method.
  - **Single colleges** (46 sampled): 0% differ.
  - **School districts** (16 sampled): 19% differ.
  - **Multi-campus systems / college districts / boards** (31 sampled): 58% differ.
  - **College foundations and research corporations** (16 sampled): 100% differ.
  - **Nonprofits** (39 sampled): 100% differ. Two-thirds have no single Host.
  - **State agencies** (12 sampled): 100% differ. None has a single Host.
- **Linking by recipient name alone.** Among Grants that do have a single Host, about **20%** (95% interval 11–30%) would be linked wrongly or ambiguously. About 10% would land on a specific *wrong* college, usually a system's main campus or system office. Most of the error comes from systems: 80% of system-recipient Grants mislink by name.
- **Linking by place of performance alone.** About **6%** (95% interval 2–11%) would point to the wrong place.
  - That number is low only because PoP is the same as the recipient address. All ZIP5, city, county, state, and congressional district values match on **4,315/4,315** FY2024 Grants, and on every FY2024 ED assistance row checked (579,783 non-TRIO transactions).
  - **PoP is therefore not separate evidence of where the project runs.**
  - It still helps for systems that register one UEI per campus with that campus's address, e.g. UNM-Gallup, SUNY Fredonia, Hennepin Technical College under Minnesota State.
- **Which fields reveal the Host when it differs:**
  1. **Award description** (`transaction_description` / `prime_award_base_transaction_description`). It named the Host in **43 of 46** sampled Recipient≠Host Grants that have a single Host. It is free text: it uses abbreviations ("UC CLERMONT", "CSUMB", "HGTC", "SKCTC") and former names ("WEST HILLS COLLEGE LEMOORE", now IPEDS "Lemoore College").
  2. **UEI → IPEDS `ueis` bridge.** IPEDS lists campus-specific UEIs, so the UEI often resolves a system or foundation Recipient to the right campus. Weighted, it is correct for ~79% of single-Host college Grants. It is ambiguous when one UEI is shared by several UNITIDs (263 UEIs, 221 Grants), and it has errors (below).
  3. **Recipient address / PoP.** These are the same field in practice. They point to the Host's city/ZIP in 31 of 46 Recipient≠Host Grants that have a single Host.
  4. **`recipient_name_raw`.** It names a specific campus under a system name on only about 15 Grants, for example "SOUTH MOUNTAIN COMMUNITY COLLEGE" under Maricopa and "…ON BEHALF OF THE COLLEGE OF SOUTHERN NEVADA".
  5. **`recipient_parent_*`.** It **never** reveals the Host. It points *up* to systems, and it has implausible values, such as Edmonds School District 15 as the parent of 33 Washington community-college Grants.

## 1. Why Recipient and Host diverge (rules)

Who may be a Recipient, by program:
- **Student Support Services (SSS) and McNair:** only an IHE or a combination of IHEs is eligible (34 CFR 646.2, 647.2)[^ecfr].
- **Talent Search, Upward Bound and EOC:** also open to "A public or private agency or organization, including a community-based organization…", "A secondary school", and combinations (34 CFR 643.2, 645.2, 644.2)[^ecfr].
- **GEAR UP Partnership:** applicants are "Partnerships consisting of (a) at least one degree-granting IHE and (b) at least one LEA"[^frgu].

For group applications, the members "shall either: (1) Designate one member of the group to apply for the grant; or (2) Establish a separate, eligible legal entity to apply for the grant" (34 CFR 75.128)[^ecfr]. The legal Recipient can therefore be:
- a foundation or research corporation,
- a system board,
- a nonprofit, or
- one partner on behalf of others.

## 2. What the USAspending fields are defined to carry

All definitions below are from the USAspending data dictionary (`GET https://api.usaspending.gov/api/v2/references/data_dictionary/`)[^dd].

| Field (archive column) | Definition | Observed in FY2024 TRIO/GEAR UP |
|---|---|---|
| `primary_place_of_performance_city_name`, `_zip_4`, `_county_*`, `_state_*`, `prime_award_transaction_place_of_performance_cd_*` | "where the predominant performance of the award will be accomplished" | Same as the recipient city, ZIP5, ZIP+4, county, state and CD on **4,315/4,315** Grants |
| `primary_place_of_performance_scope` | "Single ZIP code" = performance "primarily in a single ZIP code" | `SINGLE ZIP CODE` on 4,311 Grants; `Foreign` on 4 (Palau, Marshall Islands) |
| PoP street address | **No such element exists** for prime awards. The PoP elements are City, Code, CongressionalDistrict, Country, County, ForeignLocationDescription, Scope, State and ZIP+4 | — |
| `recipient_address_line_1` … | "legal business address where the office represented by the Unique Entity Identifier (as registered in the System for Award Management) is located" | Campus address when a system registers a UEI per campus |
| `transaction_description`, `prime_award_base_transaction_description` (AwardDescription) | For assistance: "A plain language description of the Federal award purpose; activities to be performed; deliverables and expected outcomes; intended beneficiary(ies)…" | Usually the project title. Often names the campus, target school or district |
| `recipient_parent_uei`, `recipient_parent_name` (UltimateParent…) | "The name of the ultimate parent of the awardee or recipient" | Filled on 1,467 Grants. Different from the Recipient on 678 |
| `recipient_name`, `recipient_name_raw` | Both map to AwardeeOrRecipientLegalEntityName: "The name of the awardee or recipient that relates to the unique identifier" | Different on 168 Grants. The dictionary does not explain how the two columns differ (**UNVERIFIED**) |

**ED-wide check.** In the whole FY2024 ED assistance archive, PoP city equals recipient city on 579,783 of 579,783 non-TRIO transactions. PoP ZIP5 equals recipient ZIP5 on 574,497; the rest are foreign rows. ED's PoP therefore looks like a copy of the recipient's SAM address. *Whether ED fills PoP from SAM automatically is UNVERIFIED.* No ED or USAspending document checked says so.

## 3. Method (reproducible)

### Universe
- **File.** FY2024 Award Data Archive, `FY2024_091_Assistance_Full_20261006.zip`[^arch]. sha256 `ca9543ef26624e869abcc664721d250893d0e41c539cd5238eaaaa6cbda07e0f`. Inside is `FY2024_091_Assistance_Full_20261007_1.csv`.
- **Filter.** `awarding_agency_code = 091` and `cfda_number` in {84.042, 84.044, 84.047, 84.066, 84.217, 84.334}. That leaves **4,391 transactions = 4,315 Grants** (distinct FAINs with an FY2024 action).
  - By listing: 84.047 1,913; 84.042 1,166; 84.044 618; 84.217 248; 84.066 207; 84.334 163.
  - One row was kept per FAIN: the highest `modification_number`.
  - Officer-name columns were dropped.

### Reference files
Both come from the Urban Education Data Portal `/csv/` path, with no `/api/` calls[^urban]:
- **IPEDS directory** `csv/ipeds/colleges_ipeds_directory.csv`, years 2023 and 2024. Its `ueis` column is labelled "Unique Entity Identifier (UEI) Numbers" in Urban's variable list.
- **CCD district directory** `csv/ccd/school-districts_lea_directory.csv`, year 2023. The file name came from Urban's `documentation/data/api-downloads.json`.

### UEI bridge
- Each Grant's `recipient_uei` was mapped to every UNITID whose IPEDS `ueis` (2023 or 2024) contains it, **restricted to the same state**.
- The state filter is there because IPEDS lists Binghamton University's UEI `NQMVAAQUFU53` under California Baptist University (CA) in 2022–2024 as well as under Binghamton (NY) in 2024. That is an IPEDS data error.

### Strata (automated)
| Stratum | Rule | Grants |
|---|---|---|
| `IHE_single` | UEI → exactly 1 UNITID | 3,176 |
| `IHE_multi` | UEI → 2+ UNITIDs | 221 |
| `IHE_unmatched` | business type H/O, or name equals an IPEDS name / contains COLLEGE or UNIVERSITY, and UEI not in IPEDS | 474 |
| `nonprofit` | business type M | 214 |
| `school_district` | LEA-like name pattern or business type G | 84 |
| `state_gov` | business type A | 54 |
| `other` | everything else | 92 |

### Sample
- **First draw:** 20 Grants per stratum, Python `random.Random(20261014).sample` over FAIN-sorted lists.
- **Second draw:** 20 more from `IHE_single` (`random.Random(20261015)`, excluding the first draw), because that stratum is 74% of Grants.
- **Total: n = 160.**

### Hand review
For each sampled Grant I read the recipient name, raw name, parent, address, description(s) and the UEI-bridge candidates, and recorded:
- **Recipient type**, assigned by hand. The automated strata are noisy: e.g. LULAC fell into `school_district`, and the CSU Dominguez Hills Foundation is business type "state government". The types are:
  - SC: single college
  - SYS: multi-campus system, college district or board
  - AUX: college foundation or research corporation
  - NP: nonprofit or for-profit
  - STATE: state agency
  - LEA: school district, county office or ESA
- **Host:**
  - a UNITID or LEAID;
  - `NONE` if no college or district is identifiable (e.g. a community-based Talent Search with no school named);
  - `MULTI` for state or partnership GEAR UP serving many districts.
- **Host rules:**
  - When the Recipient is a college or its foundation and runs TRIO, the Host is that college.
  - When a nonprofit names one target school or district, or one city with a single district, the Host is that LEA.
- **R=H:** whether the Recipient's own legal entity *is* the Host. A system board, a different campus, a foundation, or a nonprofit counts as "N".
- **Name link:** what linking `recipient_name` to IPEDS/CCD names would give: `correct`, `wrong` (a specific other unit, e.g. the main campus), `ambiguous` (several units equally), or `none`.
- **UEI bridge:** `correct`, `wrong`, `ambiguous` or `none`.
- **PoP:** whether PoP city or ZIP5 is the Host's location (`Y`/`N`).
  - This was cross-checked automatically against the IPEDS/CCD city and ZIP. There were 4 disagreements, all kept as `Y` on review: Urbana vs Champaign twin cities, and three cases where the campus named is inside one UNITID (Lone Star, Miami Dade Homestead, CCBC Dundalk).
- **Confidence:** each row is rated H/M/L in the appendix. L rows are cases where the description doesn't name a campus and I assumed the main one.

### Estimates
- Universe shares weight each stratum by (stratum size / sampled in stratum).
- The 95% intervals come from a stratified bootstrap (2,000 reps, seed 7).
- Per-type figures in §4 are unweighted sample shares within each hand-assigned type.

Scripts (not committed) were run with `python3 -I` from `/tmp/rvh_scripts/`, with data in `/tmp/rvh_data/` and `/tmp/rvh_ref/`. The full per-Grant judgments are in Appendix B.

## 4. Results

### By Recipient type (hand-assigned; sample shares)

| Recipient type | n | Recipient ≠ Host | Single Host | Name-only: wrong / ambiguous / none (of single-Host) | PoP-only wrong (of single-Host) | UEI bridge correct (of single-Host colleges) |
|---|---|---|---|---|---|---|
| Single college (SC) | 46 | 0 (0%) | 46 | 0 / 0 / 1 | 0/46 | 29/46 (14 not in IPEDS) |
| Multi-campus system / college district / board (SYS) | 31 | 18 (58%) | 30 | 11 / 13 / 4 → **80% mislink** | 8/30 (27%) | 6/30 (15 ambiguous, 3 wrong) |
| College foundation / research corp (AUX) | 16 | 16 (100%) | 15 | 1 / 1 / 2 | 1/15 (7%) | 4/15 (10 not in IPEDS) |
| Nonprofit / CBO (NP) | 39 | 39 (100%) | 13 (LEA named in description); 25 NONE, 1 MULTI | 0 / 0 / 13 (never links) | 6/13 (46%) | n/a |
| State agency (STATE) | 12 | 12 (100%) | 0 (10 MULTI, 2 NONE) | n/a | n/a | n/a |
| School district / county office / ESA (LEA) | 16 | 3 (19%) | 14 | 1 / 0 / 1 | 1/14 (7%) | n/a |
| **All (unweighted)** | 160 | 88 (55%) | 118 | 13 / 14 / 21 | 16/118 (14%) | — |
| **All (weighted to 4,315 Grants)** | — | **31.0%** (22–41%) | 94% | wrong 10.2% (3.5–17.9%); wrong+ambiguous 19.7% (10.7–29.7%); none 6.6% | **5.6%** (2.3–10.5%) | 79% |

### Patterns behind the numbers

- **Systems: the name points at the main campus or system office, the description names the branch.** Examples:
  - `P047A220217` "CINCINNATI UNIV OF" / "UC CLERMONT TRIO UPWARD BOUND". Host is UC Clermont College (Batavia). PoP is Cincinnati.
  - `P047A170955` Ohio State / "OHIO STATE ATI UPWARD BOUND". Host is in Wooster; PoP is Columbus.
  - `P047A221294` Purdue / "…AT PURDUE NORTHWEST". Host is in Hammond; PoP is West Lafayette.
  - `P042A201634` WVU / "…WEST VIRGINIA UNIVERSITY INSTITUTE OF TECHNOLOGY".
  - In these cases the UEI bridge is ambiguous or wrong, and PoP is wrong.
- **Systems that register one UEI per campus: UEI and address are right, the name is not.**
  - 60 recipient names carry more than one UEI, covering 648 Grants (15%). Examples: University of Wisconsin System 11 UEIs, Minnesota State 11, Research Foundation of CUNY 10, SUNY Research Foundation 10, KCTCS 7, University of Hawaii 6. No UEI carries more than one name.
  - Examples: `P047A221064` SUNY RF, Fredonia address → SUNY Fredonia; `P042A200204` Minnesota State, address 55445 → Hennepin Technical College; `P217A230284` "UNIVERSITY OF ARKANSAS SYSTEM", Little Rock → UA Little Rock.
- **The campus named is not a separate UNITID.** Examples: Lone Star North Harris, Pima Desert Vista, Hinds Utica, Miami Dade Homestead, CCBC Dundalk, Carl Albert Sallisaw, Georgia Southern Armstrong/Liberty. The Host is the Recipient's own UNITID, and description detail below IPEDS granularity doesn't change the link.
- **Foundations and research corporations** are separate legal entities, but their names usually contain the college name. In the sample, name-only linking was correct for 11 of 15.
  - The IPEDS `ueis` list includes some foundation UEIs: Highland CC Foundation (IL), WKU Research Foundation, Kirkwood CC Foundation.
  - Others are missing: University Corporation at Monterey Bay, Cal Poly Corporation, KU Center for Research.
- **Nonprofits never link by name.** Their Host, when there is one, is an LEA named only in the description, e.g. "…EAST HIGH SCHOOL IN MADISON, WISCONSIN" or "(EAST CLEVELAND CITY SCHOOL DISTRICT; SHAW HIGH SCHOOL)".
  - PoP is the nonprofit's office. That is often another city: Cleburne TX for Alvarado ISD and Rio Vista ISD; San Francisco for Vallejo; Danville for West Contra Costa USD.
  - Sometimes it is another state: `P047M220508` FAMILY-CENTERED EDUCATION (South Holland, IL) "UBMS CORPUS CHRISTI TEXAS"; `P047A221345` LULAC NESC (Washington, DC) "LNESC OXNARD UPWARD BOUND PROGRAM".
- **State agencies and GEAR UP State grants** have no single Host. Nothing in USAspending lists the served districts.
- **School districts** are usually their own Host. Exceptions:
  - ESAs or intermediate units serving another district: `P044A210178` Northwest Tri-County IU 5 → Erie City SD.
  - Region One ESC GEAR UP serves many districts.
  - CCD names can differ from legal names: "METROPOLITAN NASHVILLE PUBLIC SCHOOLS" is CCD "Davidson County".

### Automated signals over all 4,315 Grants (no hand review)

- UEI → UNITIDs (same state): exactly 1 for 3,176 Grants, 2+ for 221, 0 for 918.
- Of the 221 Grants whose UEI maps to 2+ UNITIDs, the description or raw name contains exactly one of the candidate IPEDS names in **87 (39%)**. Matching was exact normalized-name substring, so abbreviations are missed.
- Of the 3,176 Grants whose UEI maps to exactly one UNITID, **37** have a description containing a *different* same-state IPEDS name.
  - True cases include Los Rios CCD (UEI listed for Cosumnes River College) with descriptions naming "AMERICAN RIVER COLLEGE"; University of South Carolina (UEI → Columbia) naming the Salkehatchie, Lancaster and Sumter campuses; University of Hawaii (UEI → Manoa) naming Honolulu Community College; and Rancho Santiago CCD naming Santa Ana College.
  - False positives include "CALIFORNIA UNIVERSITY OF PENNSYLVANIA" matching "University of Pennsylvania".
- `recipient_name_raw` ≠ `recipient_name` on 168 Grants. It names a specific campus under a system name on about 15, by inspecting all 70 distinct pairs:
  - Maricopa → "SOUTH MOUNTAIN COMMUNITY COLLEGE" (2)
  - KCTCS → "HAZARD COMMUNITY AND TECHNICAL COLLEGE" (2) and "SKYCTC" (3)
  - UC Regents → "…AT RIVERSIDE" (6)
  - San Mateo CCD → "SKYLINE COLLEGE" (1)
  - NSHE → "…ON BEHALF OF THE COLLEGE OF SOUTHERN NEVADA" (1)
- `recipient_parent_name` points up a hierarchy and is sometimes implausible:
  - "EDMONDS SCHOOL DISTRICT 15" is parent to 33 Grants at 17 Washington community colleges.
  - "YORK TECHNICAL COLLEGE" is parent to 20 South Carolina technical-college Grants.
  - "CORRECTIONS, FLORIDA DEPARTMENT OF" is parent to 16 Florida college Grants.
  - Iowa College Student Aid Commission's parent is "STATE OF IOWA DEPARTMENT OF COMMERCE ALCHOHOLIC BEVERAGES DIVISION".
  - *Cause UNVERIFIED.* These look like state-level groupings in SAM hierarchy data, and SAM hierarchy is FOUO per `entity-and-geo-sources.md` §A1.

## 5. Implications for linking a Grant to its Host

These follow from the findings above. They are not tested pipeline rules.

1. **Do not use PoP as independent evidence.** It is the recipient's SAM address. Use it as "recipient address".
2. **Bridge first on UEI → IPEDS `ueis`, same state.** Then:
   - if exactly one UNITID: accept it, but check the description for a different campus name (the West Hills/Lemoore, UC Clermont and Los Rios/American River College patterns);
   - if several UNITIDs: pick using the description, then recipient address ZIP/city;
   - if none: fall back to name plus address.
3. **Parse the description against an alias table** (IPEDS `inst_name`, `inst_alias`, common abbreviations, former names). Expect LEA and school names for nonprofit-run Upward Bound and Talent Search.
4. **Mark Grants with no single Host explicitly.** These are state agencies, GEAR UP State, community-based nonprofits, and GEAR UP partnerships whose districts aren't named. Do not force a link.
5. **Ignore `recipient_parent_*` for Host linking.**

## Open questions / UNVERIFIED

- **Why PoP = recipient address.** That ED's FABS PoP is filled from the recipient's SAM address is inferred from the 100% match. No documentation was found.
- **`recipient_name` vs `recipient_name_raw`.** The data dictionary maps both columns to the same element and does not explain how they differ.
- **Parent values.** The cause of the implausible ultimate-parent values (Edmonds SD 15, York Tech, Florida DOC) is unknown.
- **IPEDS `ueis` quality.**
  - Beyond the variable label, there is no definition or collection rule.
  - The Binghamton UEI listed under California Baptist is a confirmed inconsistency.
  - How many other cross-institution errors exist was not measured.
- **Hand judgments.**
  - Rows marked L/M confidence in Appendix B assume the main campus when the description is silent: Georgia State "TRI-COUNTY UPWARD BOUND", Bowling Green, Delaware Tech, Pontifical Catholic Ponce, Vermont State.
  - Host-LEA calls for nonprofits rely on a school or city named in the description.
  - None was checked against ED's grantee lists. Those are on ed.gov, which was not fetched.
- **Sampling error.**
  - The weighted shares rest on 40 draws from the dominant `IHE_single` stratum, which drives the width of the intervals.
  - A larger hand-labelled sample, or the APR files in `apr-data-and-fy2026-awards.md`, would tighten them.
- **Other years.** Only FY2024 was sampled. PoP = recipient address was also seen for one FY2025 award in `usaspending-trio-gearup.md`, but other years were not tested systematically.

## Appendix A: reproduce

1. **Archive.** `POST https://api.usaspending.gov/api/v2/bulk_download/list_monthly_files/` with `{"agency":80,"fiscal_year":2024,"type":"assistance"}`, then download the `FY2024_091_Assistance_Full_20261006.zip` URL it returns.
2. **Urban CSVs.** `https://educationdata.urban.org/csv/ipeds/colleges_ipeds_directory.csv` and `https://educationdata.urban.org/csv/ccd/school-districts_lea_directory.csv`.
3. **Filter and strata.** Filter and collapse to FAIN as in §3. Build the strata with the rules in the §3 table, then draw the sample with the two seeds.
4. **Score.** Use the judgments in Appendix B to recompute the §4 tables. Weights per stratum are N/n: `IHE_single` 3,176/40, `IHE_unmatched` 474/20, `IHE_multi` 221/20, `nonprofit` 214/20, `other` 92/20, `school_district` 84/20, `state_gov` 54/20.

## Appendix B: sample and judgments (n = 160)

Columns:
- **Type:** hand-assigned Recipient type.
- **R=H:** Recipient is the Host.
- **Name:** outcome of linking by `recipient_name`.
- **UEI bridge:** outcome of the IPEDS `ueis` bridge.
- **PoP:** PoP city/ZIP is the Host's location.
- **Host revealed by:** fields that identify the Host. "address" means recipient address / PoP.

| # | FAIN | Stratum | Recipient (USAspending `recipient_name`) | Type | Host | R=H | Name | UEI bridge | PoP | Host revealed by | Conf. | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | P047V170208 | IHE_multi | WEST HILLS COMMUNITY COLLEGE DISTRICT | SYS | UNITID 448594 | N | wrong | wrong | N | desc | H | desc uses former name West Hills College Lemoore; IPEDS 2023 name Lemoore College |
| 1 | P047A221294 | IHE_multi | PURDUE UNIVERSITY | SYS | UNITID 490805 | N | wrong | ambiguous | N | desc | H | Purdue Northwest (Hammond); recipient West Lafayette |
| 2 | P042A201697 | IHE_multi | ARIZONA STATE UNIVERSITY | SYS | UNITID 104151 | Y | ambiguous | ambiguous | Y | address | M | Downtown Phoenix campus is inside ASU Campus Immersion UNITID |
| 3 | P047M220448 | IHE_multi | KENT STATE UNIVERSITY | SYS | UNITID 203517 | Y | ambiguous | ambiguous | Y | address | M | no campus named; Kent main campus assumed |
| 4 | P066A210105 | IHE_multi | UNIVERSITY OF TENNESSEE | SYS | UNITID 221759 | Y | ambiguous | ambiguous | Y | address | M | no campus named; Knoxville assumed |
| 5 | P042A201634 | IHE_multi | WEST VIRGINIA UNIVERSITY | SYS | UNITID 237950 | N | wrong | ambiguous | N | desc | H | WVU Tech (Beckley) branch; recipient Morgantown |
| 6 | P217A220087 | IHE_multi | UNIVERSITY OF CONNECTICUT | SYS | UNITID 129020 | Y | correct | ambiguous | Y | name, address | M |  |
| 7 | P047A220778 | IHE_multi | GEORGIA STATE UNIVERSITY | SYS | UNITID 139940 | Y | correct | ambiguous | Y | name, address | L | Tri-County UB; main vs Perimeter College not stated |
| 8 | P047A221526 | IHE_multi | BOWLING GREEN STATE UNIVERSITY | SYS | UNITID 201441 | Y | ambiguous | ambiguous | Y | address | L | main vs Firelands not stated |
| 9 | P047A221070 | IHE_multi | OLD DOMINION UNIVERSITY | SC | UNITID 232982 | Y | correct | ambiguous | Y | name, address | H | UEI also listed for Eastern Virginia Medical School |
| 10 | P047A170955 | IHE_multi | OHIO STATE UNIVERSITY, THE | SYS | UNITID 204662 | N | wrong | ambiguous | N | desc | H | OSU ATI (Wooster); recipient Columbus |
| 11 | P047M220012 | IHE_multi | WEST HILLS COMMUNITY COLLEGE DISTRICT | SYS | UNITID 448594 | N | wrong | wrong | N | desc | H | as idx 0 |
| 12 | P047A171496 | IHE_multi | UNIVERSITY OF ILLINOIS | SYS | UNITID 145637 | N | ambiguous | ambiguous | Y | desc, address | H | recipient is University of Illinois (system); desc names Urbana-Champaign |
| 13 | P047A170705 | IHE_multi | DELAWARE TECHNICAL & COMMUNITY COLLEGE | SYS | UNITID 130907 | Y | ambiguous | ambiguous | Y | address | L | campus not stated |
| 14 | P047A221172 | IHE_multi | PONTIFICAL CATHOLIC UNIVERSITY OF PUERTO RICO | SYS | UNITID 241410 | Y | ambiguous | ambiguous | Y | address | L | site not stated; Ponce assumed |
| 15 | P047A171469 | IHE_multi | MIAMI UNIVERSITY | SYS | UNITID 204006/204015 | N | wrong | ambiguous | N | desc | H | desc says regional campuses (Hamilton/Middletown) without picking one |
| 16 | P217A220029 | IHE_multi | UNIVERSITY OF WASHINGTON | SYS | UNITID 236948 | Y | ambiguous | ambiguous | Y | address | M |  |
| 17 | P047A220491 | IHE_multi | SOUTHERN UNIVERSITY AND A & M COLLEGE | SC | UNITID 160621 | Y | correct | ambiguous | Y | name, address | M | UEI also listed for Southern University Board and System |
| 18 | P217A220090 | IHE_multi | OLD DOMINION UNIVERSITY | SC | UNITID 232982 | Y | correct | ambiguous | Y | name, address | H |  |
| 19 | P047A170568 | IHE_multi | PONTIFICAL CATHOLIC UNIVERSITY OF PUERTO RICO | SYS | UNITID 241410 | Y | ambiguous | ambiguous | Y | desc, address | H |  |
| 20 | P047A220217 | IHE_single | CINCINNATI UNIV OF | SYS | UNITID 201946 | N | wrong | wrong | N | desc | H | UC Clermont (Batavia); recipient Cincinnati |
| 21 | P047A220145 | IHE_single | DYERSBURG STATE COMMUNITY COLLEGE | SC | UNITID 220057 | Y | correct | correct | Y | name, uei, address | H |  |
| 22 | P044A210214 | IHE_single | CARL ALBERT STATE COLLEGE | SC | UNITID 206923 | Y | correct | correct | Y | name, uei, address | H | desc names Sallisaw campus (not a separate UNITID) |
| 23 | P044A160110 | IHE_single | UNIVERSITY OF MAINE AT PRESQUE ISLE | SC | UNITID 161341 | Y | correct | correct | Y | name, uei, address | H |  |
| 24 | P042A200448 | IHE_single | DILLARD UNIVERSITY | SC | UNITID 158802 | Y | correct | correct | Y | name, uei, address | H |  |
| 25 | P066A210251 | IHE_single | WICHITA STATE UNIVERSITY | SC | UNITID 156125 | Y | correct | correct | Y | name, uei, address | H |  |
| 26 | P047A220248 | IHE_single | UNIVERSITY OF ARKANSAS | SC | UNITID 106397 | Y | correct | correct | Y | name, uei, address | H |  |
| 27 | P066A220094 | IHE_single | BIG BEND COMMUNITY COLLEGE | SC | UNITID 234711 | Y | correct | correct | Y | name, uei, address | H | parent field says Edmonds School District 15 (wrong) |
| 28 | P044A210719 | IHE_single | LONE STAR COLLEGE SYSTEM | SC | UNITID 227182 | Y | correct | correct | Y | name, uei, address | H | desc names North Harris campus; IPEDS reports Lone Star as one UNITID |
| 29 | P047V220004 | IHE_single | DAVIS & ELKINS COLLEGE, INC. | SC | UNITID 237358 | Y | correct | correct | Y | name, uei, address | H |  |
| 30 | P047A220775 | IHE_single | BOARD OF TRUSTEES OF SOUTHERN ILLINOIS UNIVERSITY | SYS | UNITID 149222 | N | ambiguous | correct | Y | desc, uei, address | H | recipient is SIU Board of Trustees |
| 31 | P047M220206 | IHE_single | SOUTHERN UNIV AND A&M COLLEGE SYSTEM | SYS | UNITID 160630 | N | wrong | correct | Y | uei, address | M | recipient named Southern Univ System; UEI and New Orleans address = SUNO |
| 32 | P047A230092 | IHE_single | APPALACHIAN STATE UNIVERSITY | SC | UNITID 197869 | Y | correct | correct | Y | name, uei, address | H |  |
| 33 | P047M220219 | IHE_single | TRIDENT TECHNICAL COLLEGE | SC | UNITID 218894 | Y | correct | correct | Y | name, uei, address | H | parent field says York Technical College (wrong) |
| 34 | P047A171242 | IHE_single | CHEMEKETA COMMUNITY COLLEGE DISTRICT | SC | UNITID 208390 | Y | correct | correct | Y | name, uei, address | H |  |
| 35 | P044A210729 | IHE_single | UNIVERSITY OF LOUISIANA AT LAFAYETTE | SC | UNITID 160658 | Y | correct | correct | Y | name, uei, address | H |  |
| 36 | P044A210132 | IHE_single | MOREHEAD STATE UNIVERSITY | SC | UNITID 157386 | Y | correct | correct | Y | name, uei, address | H |  |
| 37 | P217A230284 | IHE_single | UNIVERSITY OF ARKANSAS SYSTEM | SYS | UNITID 106245 | N | wrong | correct | Y | uei, address | M | recipient University of Arkansas System; UEI and Little Rock address = UALR |
| 38 | P047A220056 | IHE_single | WAUBONSEE COMMUNITY COLLEGE | SC | UNITID 149727 | Y | correct | correct | Y | name, uei, address | H |  |
| 39 | P047A221443 | IHE_single | THE UNIVERSITY OF TEXAS RIO GRANDE VALLEY | SC | UNITID 227368 | Y | correct | correct | Y | name, uei, address | H |  |
| 40 | P042A201419 | IHE_unmatched | UNIVERSITY OF NEW MEXICO | SYS | UNITID 187958 | N | wrong | none | Y | desc, address | H | UNM-Gallup branch; recipient address is Gallup |
| 41 | P042A200660 | IHE_unmatched | UNIVERSITY CORPORATION AT MONTEREY BAY | AUX | UNITID 409698 | N | none | none | Y | desc, address | H | CSUMB auxiliary corporation |
| 42 | P047M170131 | IHE_unmatched | SOUTHERN METHODIST UNIVERSITY | SC | UNITID 228246 | Y | correct | none | Y | name, address | H |  |
| 43 | P044A210448 | IHE_unmatched | PIMA COUNTY COMMUNITY COLLEGE DISTRICT | SC | UNITID 105525 | Y | correct | none | Y | name, address | H | desc names Desert Vista campus (not a separate UNITID) |
| 44 | P042A201539 | IHE_unmatched | BOARD OF REGENTS OF NEVADA SYSTEM OF HIGHER EDUCATION | SYS | UNITID 182290 | N | none | none | Y | desc, address | H | NSHE Board of Regents |
| 45 | P042A200860 | IHE_unmatched | FISK UNIVERSITY | SC | UNITID 220181 | Y | correct | none | Y | name, address | H |  |
| 46 | P044A220642 | IHE_unmatched | AUSTIN COMMUNITY COLLEGE DISTRICT | SC | UNITID 222992 | Y | correct | none | Y | name, address | H |  |
| 47 | P042A200790 | IHE_unmatched | HIGHLAND COMMUNITY COLLEGE | SC | UNITID 155186 | Y | correct | none | Y | name, address | H |  |
| 48 | P042A200068 | IHE_unmatched | JACKSON COLLEGE | SC | UNITID 170444 | Y | correct | none | Y | name, address | H |  |
| 49 | P217A220127 | IHE_unmatched | SOUTHERN METHODIST UNIVERSITY | SC | UNITID 228246 | Y | correct | none | Y | name, address | H |  |
| 50 | P047M220063 | IHE_unmatched | BOARD OF REGENTS OF NEVADA SYSTEM OF HIGHER EDUCATION | SYS | UNITID 182290 | N | none | none | Y | desc, address | H | NSHE Board of Regents |
| 51 | P042A200412 | IHE_unmatched | PIMA COUNTY COMMUNITY COLLEGE DISTRICT | SC | UNITID 105525 | Y | correct | none | Y | name, address | H |  |
| 52 | P044A210913 | IHE_unmatched | UNIVERSITY OF THE DISTRICT OF COLUMBIA | SC | UNITID 131399 | Y | correct | none | Y | name, address | H |  |
| 53 | P042A211632 | IHE_unmatched | UNIVERSITY OF KANSAS CENTER FOR RESEARCH INC | AUX | UNITID 155317 | N | correct | none | Y | desc, name, address | H | KU Center for Research |
| 54 | P047A170051 | IHE_unmatched | PIMA COUNTY COMMUNITY COLLEGE DISTRICT | SC | UNITID 105525 | Y | correct | none | Y | name, address | H |  |
| 55 | P042A200890 | IHE_unmatched | HINDS COMMUNITY COLLEGE | SC | UNITID 175786 | Y | correct | none | Y | name, address | H | desc names Utica campus (not a separate UNITID) |
| 56 | P334A180017 | IHE_unmatched | UNIVERSITY OF WASHINGTON | SYS | MULTI | N | NA | NA | NA | none | M | GEAR UP partnership; partner districts not named |
| 57 | P047A170501 | IHE_unmatched | HOLY NAMES UNIVERSITY | SC | UNITID 115728 | Y | correct | none | Y | name, address | H |  |
| 58 | P042A200750 | IHE_unmatched | VERMONT STATE COLLEGES | SYS | UNITID 231165 | Y | ambiguous | none | N | address | L | Vermont State Colleges system became Vermont State University in 2023; address Johnson vs IPEDS Randolph |
| 59 | P042A200970 | IHE_unmatched | CAL POLY CORPORATION | AUX | UNITID 110422 | N | ambiguous | none | Y | address | H | Cal Poly Corporation auxiliary |
| 60 | P044A210447 | nonprofit | UNIVERSITY SETTLEMENT SOCIETY OF NEW YORK | NP | NONE | N | NA | NA | NA | none | H |  |
| 61 | P334S190008 | nonprofit | BOARD OF TRUSTEES COMMUNITY-TECHNICAL COLLEGES | STATE | MULTI | N | NA | NA | NA | none | H | state GEAR UP via CT college board |
| 62 | P066A220234 | nonprofit | NORTH ALABAMA CENTER FOR EDUCATIONAL EXCELLENCE, INC. | NP | NONE | N | NA | NA | NA | none | H |  |
| 63 | P047V220003 | nonprofit | ASPIRA INC OF PUERTO RICO | NP | NONE | N | NA | NA | NA | none | H |  |
| 64 | P066A210092 | nonprofit | COLLEGE ENTRANCE EXAMINATION BOARD | NP | NONE | N | NA | NA | NA | none | H |  |
| 65 | P217A220115 | nonprofit | GEORGIA SOUTHERN UNIVERSITY RESEARCH & SERVICE FOUNDATION INC | AUX | UNITID 139931 | N | correct | none | Y | desc, name, address | H | Georgia Southern research foundation |
| 66 | P047A170410 | nonprofit | OPPORTUNITY RESOURCE SERVICES, INC. | NP | LEAID 4837200 | N | none | NA | N | desc | M | Rio Vista; recipient Cleburne |
| 67 | P047A171206 | nonprofit | FORWARD SERVICE CORPORATION | NP | LEAID 5508520 | N | none | NA | Y | desc | H | East High School Madison |
| 68 | P044A210172 | nonprofit | COLLEGE NOW GREATER CLEVELAND INC | NP | LEAID 3904378 | N | none | NA | Y | desc | H | Cleveland Metropolitan SD named |
| 69 | P047A220136 | nonprofit | UPSTATE INSTITUTE OF YOUTH PROGRAMS INC | NP | NONE | N | NA | NA | NA | none | H |  |
| 70 | P047M220376 | nonprofit | OPPORTUNITY RESOURCE SERVICES, INC. | NP | LEAID 4800011 | N | none | NA | N | desc | H | Alvarado HS; recipient Cleburne |
| 71 | P044A210392 | nonprofit | JAPANESE COMMUNITY YOUTH COUNCIL | NP | NONE | N | NA | NA | NA | none | M | Daly City schools not named |
| 72 | P044A210917 | nonprofit | LEARN INC | NP | NONE | N | NA | NA | NA | none | H |  |
| 73 | P044A160083 | nonprofit | JAPANESE COMMUNITY YOUTH COUNCIL | NP | NONE | N | NA | NA | NA | none | M |  |
| 74 | P047A170776 | nonprofit | BOYS & GIRLS CLUBS OF GREATER TARRANT COUNTY, INC | NP | NONE | N | NA | NA | NA | none | H |  |
| 75 | P047A221037 | nonprofit | COLLEGE NOW GREATER CLEVELAND INC | NP | LEAID 3904390 | N | none | NA | N | desc | H | East Cleveland CSD; recipient Cleveland |
| 76 | P047A221336 | nonprofit | PACT, PLAN OF ACTION FOR CHALLENGING TIMES | NP | LEAID 0640740 | N | none | NA | N | desc | M | Vallejo; recipient San Francisco |
| 77 | P044A160073 | nonprofit | JAPANESE COMMUNITY YOUTH COUNCIL | NP | LEAID 0634410 | N | none | NA | Y | desc | H | SFUSD named |
| 78 | P042A201456 | nonprofit | GEORGIA SOUTHERN UNIVERSITY RESEARCH & SERVICE FOUNDATION INC | AUX | UNITID 139931 | N | correct | none | Y | desc, name, address | H | Armstrong/Liberty campuses are inside Georgia Southern UNITID |
| 79 | P334S230008 | nonprofit | EDUCATION ALLIANCE FOR NEW HAMPSHIRE | NP | MULTI | N | NA | NA | NA | none | H | state GEAR UP via nonprofit; raw name is a former name |
| 80 | P047A170551 | other | TELACU EDUCATION FOUNDATION | NP | NONE | N | NA | NA | NA | none | H |  |
| 81 | P044A210180 | other | TEHAMA COUNTY DEPARTMENT OF EDUCATION | LEA | LEAID 0691043 | Y | correct | NA | Y | name, address | H | county office of education |
| 82 | P047A220454 | other | MENTORSHIP ACADEMY ADVANCE TRAINING INSTITUTE INC. | NP | NONE | N | NA | NA | NA | none | M | Mills/Little Rock; district not determinable |
| 83 | P047M170515 | other | WAHUPA EDUCATIONAL ENTERPRISES, INC | NP | NONE | N | NA | NA | NA | none | H |  |
| 84 | P334S230009 | other | DISTRICT OF COLUMBIA, GOVERNMENT OF | STATE | MULTI | N | NA | NA | NA | none | M | 8 middle schools in Wards 7 and 8; LEA not named |
| 85 | P047A221031 | other | IMPACT EDUCATIONAL AND HOUSING DEVELOPMENT | NP | NONE | N | NA | NA | NA | none | H |  |
| 86 | P044A210238 | other | PROJECT STAY INC | NP | NONE | N | NA | NA | NA | none | H |  |
| 87 | P047A220423 | other | WAHUPA EDUCATIONAL ENTERPRISES, INC | NP | NONE | N | NA | NA | NA | none | M |  |
| 88 | P042A200204 | other | MINNESOTA STATE COLLEGES & UNIVERSITIES | SYS | UNITID 173708 | N | none | none | Y | desc, address | H | Minnesota State system; address is Hennepin Tech |
| 89 | P047A170550 | other | TELACU EDUCATION FOUNDATION | NP | NONE | N | NA | NA | NA | none | H |  |
| 90 | P044A210246 | other | FAMILY-CENTERED EDUCATION | NP | LEAID 1738970 | N | none | NA | Y | desc | M | Thornwood HS (Thornton Twp HSD 205) |
| 91 | P047M220508 | other | FAMILY-CENTERED EDUCATION | NP | NONE | N | NA | NA | NA | none | M | project in Corpus Christi TX; recipient and PoP in South Holland IL |
| 92 | P047A221014 | other | FAMILY-CENTERED EDUCATION | NP | LEAID 1709930 | N | none | NA | N | desc | M | Chicago Englewood; recipient South Holland |
| 93 | P334A180108 | other | IREDELL-STATESVILLE SCHOOLS | LEA | LEAID 3702310 | Y | correct | NA | Y | name, address | H |  |
| 94 | P042A200930 | other | ALLAN HANCOCK JOINT COMMUNITY COLLEGE DISTRICT | SC | UNITID 108807 | Y | correct | none | Y | desc, name, address | H |  |
| 95 | P044A220579 | other | COLLEGE IS REAL, INC. | NP | LEAID 0632550 | N | none | NA | N | desc | H | WCCUSD; recipient Danville |
| 96 | P042A200211 | other | MINNESOTA STATE COLLEGES & UNIVERSITIES | SYS | UNITID 173708 | N | none | none | Y | desc, address | H | as idx 88 |
| 97 | P044A210431 | other | CYPRESS HILLS LOCAL DEVELOPMENT CORPORATION, INC. | NP | NONE | N | NA | NA | NA | none | H |  |
| 98 | P047M220096 | other | C.O.P.E., INC., ETS | NP | NONE | N | NA | NA | NA | none | H |  |
| 99 | P047A220105 | other | UNITED PIEDMONT CENTER FOR EDUCATIONAL EXCELLENCE | NP | NONE | N | NA | NA | NA | none | H |  |
| 100 | P047A220997 | school_district | LULAC NATIONAL EDUCATIONAL SERVICE CENTERS, INC. | NP | LEAID 3500060 | N | none | NA | Y | desc | H | West Mesa HS Albuquerque |
| 101 | P047M220210 | school_district | LULAC NATIONAL EDUCATIONAL SERVICE CENTERS, INC. | NP | NONE | N | NA | NA | NA | none | M | San Antonio (several ISDs) |
| 102 | P047A221345 | school_district | LULAC NATIONAL EDUCATIONAL SERVICE CENTERS, INC | NP | NONE | N | NA | NA | NA | none | M | project in Oxnard CA; recipient and PoP Washington DC |
| 103 | P044A210178 | school_district | NORTHWEST TRI COUNTY INTERMEDIATE UNIT | LEA | LEAID 4209300 | N | wrong | NA | N | desc | H | IU5 serving Erie public schools; recipient Edinboro |
| 104 | P047A220936 | school_district | LULAC NATIONAL EDUCATIONAL SERVICE CENTERS, INC. | NP | LEAID 2916400 | N | none | NA | Y | desc | H | Kansas City East HS |
| 105 | P047A220851 | school_district | THRIVE EDUCATIONAL SERVICES INC | NP | NONE | N | NA | NA | NA | none | H |  |
| 106 | P047A170117 | school_district | PORTSMOUTH CITY SCHOOL BOARD | LEA | LEAID 5103000 | Y | correct | NA | Y | name, address | H |  |
| 107 | P334A210002 | school_district | MINNEAPOLIS PUBLIC SCHOOLS SPECIAL SCHOOL DISTRICT #1 | LEA | LEAID 2721240 | Y | correct | NA | Y | name, address | H |  |
| 108 | P334A210080 | school_district | SOUTH BEND COMMUNITY SCHOOL CORP | LEA | LEAID 1810290 | Y | correct | NA | Y | name, address | H |  |
| 109 | P334A220012 | school_district | DESOTO INDEPENDENT SCHOOL DISTRICT | LEA | LEAID 4816860 | Y | correct | NA | Y | name, address | H |  |
| 110 | P047A221026 | school_district | LULAC NATIONAL EDUCATIONAL SERVICE CENTERS, INC | NP | LEAID 4218990 | N | none | NA | Y | desc | M | Philadelphia (single city district) |
| 111 | P334A210108 | school_district | SCHOOL DISTRICT OF PHILADELPHIA | LEA | LEAID 4218990 | Y | correct | NA | Y | name, address | H |  |
| 112 | P334A210093 | school_district | DUVAL COUNTY SCHOOL BOARD | LEA | LEAID 1200480 | Y | correct | NA | Y | name, address | H |  |
| 113 | P047M220198 | school_district | LULAC NATIONAL EDUCATIONAL SERVICE CENTER, INC. | NP | NONE | N | NA | NA | NA | none | M | Colorado Springs (several districts) |
| 114 | P334A180082 | school_district | BOARD OF EDUCATION OF OGDEN CITY | LEA | LEAID 4900720 | Y | correct | NA | Y | name, address | H |  |
| 115 | P047A221078 | school_district | WAYNE-WESTLAND COMMUNITY SCHOOLS | LEA | LEAID 2600015 | Y | correct | NA | Y | name, address | H |  |
| 116 | P334A180037 | school_district | METROPOLITAN NASHVILLE PUBLIC SCHOOLS | LEA | LEAID 4703180 | Y | none | NA | Y | address | H | CCD name is Davidson County |
| 117 | P047A220865 | school_district | LULAC NATIONAL EDUCATIONAL SERVICE CENTERS, INC. | NP | NONE | N | NA | NA | NA | none | M |  |
| 118 | P334A180143 | school_district | FORT WAYNE COMMUNITY SCHOOLS | LEA | LEAID 1803630 | Y | correct | NA | Y | name, address | H |  |
| 119 | P334A210174 | school_district | AKRON BOARD OF EDUCATION | LEA | LEAID 3904348 | Y | correct | NA | Y | name, address | H |  |
| 120 | P042A201091 | state_gov | HORRY GEORGETOWN COMMISSION FOR TECHNICAL EDUCATION | SC | UNITID 218140 | Y | none | none | Y | desc, address | H | legal name is the college's commission; desc says HGTC |
| 121 | P334S240019 | state_gov | MINNESOTA OFFICE OF HIGHER EDUCATION | STATE | MULTI | N | NA | NA | NA | none | H |  |
| 122 | P334A180168 | state_gov | CALIFORNIA STATE UNIVERSITY, DOMINGUEZ HILLS FOUNDATION | AUX | MULTI | N | NA | NA | NA | none | M | GEAR UP partnership; districts not named |
| 123 | P334S180008 | state_gov | MASSACHUSETTS DEPARTMENT OF HIGHER EDUCATION | STATE | MULTI | N | NA | NA | NA | none | H |  |
| 124 | P334A240004 | state_gov | REGION ONE EDUCATION SRV CENTER | LEA | MULTI | N | NA | NA | NA | none | H | Region One ESC GEAR UP partnership |
| 125 | P334A210014 | state_gov | REGION ONE EDUCATION SRV CENTER | LEA | MULTI | N | NA | NA | NA | none | H | Region One ESC GEAR UP partnership |
| 126 | P334S230012 | state_gov | COLLEGE STUDENT AID COMMISSION IOWA | STATE | MULTI | N | NA | NA | NA | none | H | parent field names a liquor division (wrong) |
| 127 | P334S180012 | state_gov | IDAHO STATE BOARD OF EDUCATION | STATE | MULTI | N | NA | NA | NA | none | H |  |
| 128 | P334S240008 | state_gov | OKLAHOMA STATE REGENTS FOR HIGHER EDUCATION | STATE | MULTI | N | NA | NA | NA | none | H |  |
| 129 | P334S190012 | state_gov | WISCONSIN DEPARTMENT OF PUBLIC INSTRUCTION | STATE | MULTI | N | NA | NA | NA | none | H |  |
| 130 | P042A200917 | state_gov | CALIFORNIA STATE UNIVERSITY, DOMINGUEZ HILLS FOUNDATION | AUX | UNITID 110547 | N | correct | none | Y | desc, name, address | H | CSUDH foundation |
| 131 | P334S220007 | state_gov | NEW YORK STATE HIGHER EDUCATION SERVICES CORPORATION | STATE | MULTI | N | NA | NA | NA | none | H |  |
| 132 | P334S210008 | state_gov | EXECUTIVE OFFICE STATE OF OHIO | STATE | MULTI | N | NA | NA | NA | none | H |  |
| 133 | P047A221457 | state_gov | CALIFORNIA STATE UNIVERSITY, DOMINGUEZ HILLS FOUNDATION | AUX | UNITID 110547 | N | correct | none | Y | desc, name, address | H | CSUDH foundation; UB serving Inglewood USD |
| 134 | P047A221388 | state_gov | CALIFORNIA STATE UNIVERSITY, DOMINGUEZ HILLS FOUNDATION | AUX | UNITID 110547 | N | correct | none | Y | desc, name, address | H |  |
| 135 | P047A220969 | state_gov | WISCONSIN DEPARTMENT OF PUBLIC INSTRUCTION | STATE | NONE | N | NA | NA | NA | none | M | state agency runs UB |
| 136 | P047A221390 | state_gov | CALIFORNIA STATE UNIVERSITY, DOMINGUEZ HILLS FOUNDATION | AUX | UNITID 110547 | N | correct | none | Y | desc, name, address | H |  |
| 137 | P044A160678 | state_gov | CALIFORNIA STATE UNIVERSITY, DOMINGUEZ HILLS FOUNDATION | AUX | UNITID 110547 | N | correct | none | Y | desc, name, address | H |  |
| 138 | P066A210224 | state_gov | BOARD OF REGENTS MONTANA | STATE | NONE | N | NA | NA | NA | none | M |  |
| 139 | P334A210112 | state_gov | CALIFORNIA STATE UNIVERSITY, DOMINGUEZ HILLS FOUNDATION | AUX | LEAID 0609620 | N | wrong | NA | N | desc | H | GEAR UP partnership with Compton Unified; recipient Carson |
| 140 | P042A201822 | IHE_single | UNIVERSITY OF MAINE AT PRESQUE ISLE | SC | UNITID 161341 | Y | correct | correct | Y | name, uei, address | H |  |
| 141 | P042A201676 | IHE_single | MIAMI DADE COLLEGE | SC | UNITID 135717 | Y | correct | correct | Y | name, uei, address | H | desc names Homestead campus (not a separate UNITID); address is Homestead |
| 142 | P047A220215 | IHE_single | CASE WESTERN RESERVE UNIVERSITY | SC | UNITID 201645 | Y | correct | correct | Y | name, uei, address | H |  |
| 143 | P047A220585 | IHE_single | COMMUNITY COLLEGE OF BALTIMORE COUNTY | SC | UNITID 434672 | Y | correct | correct | Y | name, uei, address | H | desc names Dundalk campus (not a separate UNITID) |
| 144 | P042A200074 | IHE_single | ST. MARY'S UNIVERSITY OF SAN ANTONIO, TEXAS | SC | UNITID 228149 | Y | correct | correct | Y | name, uei, address | H |  |
| 145 | P042A200287 | IHE_single | COLUMBIA COLLEGE | SC | UNITID 177065 | Y | correct | correct | Y | name, uei, address | H |  |
| 146 | P042A200205 | IHE_single | PENNSYLVANIA INSTITUTE OF TECHNOLOGY | SC | UNITID 214582 | Y | correct | correct | Y | name, uei, address | H |  |
| 147 | P047M220024 | IHE_single | KENTUCKY COMMUNITY AND TECHNICAL COLLEGE SYSTEM | SYS | UNITID 157739 | N | wrong | correct | Y | desc, uei, address | H | KCTCS; desc says SKCTC; recipient name matches KCTCS system office UNITID |
| 148 | P042A201631 | IHE_single | CENTRAL CONNECTICUT STATE UNIVERSITY | SC | UNITID 128771 | Y | correct | correct | Y | name, uei, address | H | raw name is Connecticut State University System |
| 149 | P047A221064 | IHE_single | THE RESEARCH FOUNDATION FOR THE STATE UNIVERSITY OF NEW YORK | AUX | UNITID 196158 | N | none | correct | Y | desc, uei, address | H | SUNY Research Foundation; campus-specific UEI |
| 150 | P047A220074 | IHE_single | OUACHITA BAPTIST UNIVERSITY | SC | UNITID 107512 | Y | correct | correct | Y | name, uei, address | H |  |
| 151 | P047A171097 | IHE_single | NEVADA STATE UNIVERSITY | SC | UNITID 441900 | Y | correct | correct | Y | name, uei, address | H |  |
| 152 | P047A221515 | IHE_single | HIGHLAND COMMUNITY COLLEGE FOUNDATION | AUX | UNITID 145521 | N | correct | correct | Y | desc, name, uei, address | H | college foundation; IPEDS lists the foundation UEI |
| 153 | P047V170096 | IHE_single | WESTERN KENTUCKY UNIVERSITY RESEARCH FOUNDATION, INC. | AUX | UNITID 157951 | N | correct | correct | Y | desc, name, uei, address | H | research foundation; IPEDS lists the foundation UEI |
| 154 | P066A210170 | IHE_single | KIRKWOOD COMMUNITY COLLEGE FOUNDATION | AUX | UNITID 153737 | N | correct | correct | Y | desc, name, uei, address | H | college foundation; IPEDS lists the foundation UEI |
| 155 | P047M220369 | IHE_single | UNIVERSITY OF NORTH CAROLINA AT WILMINGTON | SC | UNITID 199218 | Y | correct | correct | Y | name, uei, address | H |  |
| 156 | P047V170099 | IHE_single | GADSDEN STATE COMMUNITY COLLEGE | SC | UNITID 101240 | Y | correct | correct | Y | name, uei, address | H |  |
| 157 | P047V170102 | IHE_single | EAST TENNESSEE STATE UNIVERSITY | SC | UNITID 220075 | Y | correct | correct | Y | name, uei, address | H |  |
| 158 | P047A171005 | IHE_single | NEW MEXICO STATE UNIVERSITY | SYS | UNITID 188030 | Y | ambiguous | correct | Y | uei, address | M | NMSU main vs branch campuses; UB at Hatch Valley HS |
| 159 | P042A220835 | IHE_single | COLORADO STATE UNIVERSITY | SYS | UNITID 126818 | Y | ambiguous | correct | Y | uei, address | M | Colorado State Fort Collins vs Pueblo/Global |

[^dd]: USAspending data dictionary, `GET https://api.usaspending.gov/api/v2/references/data_dictionary/` (fetched 2026-10-14). Elements quoted: PrimaryPlaceOfPerformanceCityName, …ZIP+4, …Scope, …CongressionalDistrict, LegalEntityAddressLine1, AwardDescription, UltimateParentLegalEntityName, UltimateParentUEI, AwardeeOrRecipientLegalEntityName.
[^arch]: https://files.usaspending.gov/award_data_archive/FY2024_091_Assistance_Full_20261006.zip, listed by `POST /api/v2/bulk_download/list_monthly_files/` (`updated_date` 2026-10-06). Columns used: `award_id_fain`, `modification_number`, `recipient_uei`, `recipient_name`, `recipient_name_raw`, `recipient_parent_uei`, `recipient_parent_name`, `recipient_city_name`, `recipient_zip_code`, `recipient_zip_last_4_code`, `primary_place_of_performance_*`, `prime_award_transaction_*_cd_original`, `transaction_description`, `prime_award_base_transaction_description`, `business_types_code`, `cfda_number`, `awarding_agency_code`.
[^urban]: Urban Institute Education Data Portal v0.27.0, ODC-By 1.0. IPEDS directory: https://educationdata.urban.org/csv/ipeds/colleges_ipeds_directory.csv (Last-Modified 2026-09-24). CCD LEA directory: https://educationdata.urban.org/csv/ccd/school-districts_lea_directory.csv. File list: https://educationdata.urban.org/documentation/data/api-downloads.json. Variable labels (`ueis`, `inst_system_name`): https://educationdata.urban.org/documentation/data/api-endpoint-varlist.json. Cite as "IPEDS, CCD, via Education Data Portal v. 0.27.0, Urban Institute, under ODC Attribution License."
[^ecfr]: eCFR versioner API, title 34 as of 2026-10-01: https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-34.xml?part=645&section=645.2 (and the same pattern for 643.2, 644.2, 646.2, 647.2, 75.127, 75.128).
[^frgu]: ED, "Applications for New Awards; Gaining Early Awareness and Readiness for Undergraduate Programs (Partnership Grants)", Federal Register 2024-27054, 2024-11-20, §III.1 Eligible Applicants: https://www.federalregister.gov/documents/2024/11/20/2024-27054/applications-for-new-awards-gaining-early-awareness-and-readiness-for-undergraduate-programs (text via https://www.federalregister.gov/documents/full_text/text/2024/11/20/2024-27054.txt).
