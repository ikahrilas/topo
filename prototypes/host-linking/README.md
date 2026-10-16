# PROTOTYPE: linking Grants to Host institutions (#10)

Throwaway code. It answers one question for [#10](https://github.com/ikahrilas/topo/issues/10): on real FY2024 TRIO and GEAR UP data, what does linking each Grant to its Host institution (IPEDS UNITID or NCES LEAID) look like? Which cases are easy, which need fuzzy matching, which need a human, and what would a review queue hold? It is not pipeline code. The matching ticket ([#11](https://github.com/ikahrilas/topo/issues/11)) should take the findings below, not the script.

Run 2026-10-16. Everything is organization-level public data.

## Answer in one screen

Over all **4,315** FY2024 Grants (distinct FAINs with an FY2024 action):

| Outcome | Grants | Share |
|---|---|---|
| **Matched** automatically to one UNITID or LEAID | 3,688 | 85.5% |
| **No single Host**, decided automatically (GEAR UP State, GEAR UP partnerships naming no district, statewide agencies, community nonprofits naming no site) | 309 | 7.2% |
| **Review**: candidates found, a person must choose | 264 | 6.1% |
| **Unmatched**: no candidate found | 54 | 1.3% |

- **Decided without a person:** 3,997 Grants (92.6%). **To a person:** 318 (7.4%).
- **Accuracy of automatic decisions:** about **99%**, weighted by case size. This comes from a fresh hand-checked sample of 79 automatic decisions, drawn after the last change to the rules that affect them, with 2 wrong. The bootstrap interval is 97–100%, but it is too narrow: there are only about 5 checks per case, I was the only reviewer, and nothing was checked against a campus's own website.
- **Against the 160 hand labels from #3:** 140 of 142 automatic decisions are right. This number is *in-sample*: I tuned the rules on these labels, so it only shows the rules can reproduce #3's judgments.
- **The three outcomes are real:** "no single Host" is 7% of Grants and decided by rule, and it must stay separate from "unmatched".

## Signals, best first

Counts are among the 3,688 matched Grants. "Present" means the signal pointed at the chosen Host. "Sole" means it was the only signal besides the address.

| Signal | Present | Sole | Notes |
|---|---|---|---|
| Recipient UEI → IPEDS `ueis` (same state) | 85% | 104 | The backbone. Wrong when one UEI covers a system: it picks the main campus or the system office. |
| Recipient name → IPEDS/CCD name (same state) | 77% | 47 | Confirms more than it decides. Systems name the main campus. |
| **ED grantee list name** (joined by exact FAIN) | 75% | 24 | ED lists exist for 3,411 of 4,152 TRIO Grants. ED writes a cleaner institution name than USAspending does (e.g. "American River College" where the Recipient is "Los Rios CCD"). |
| Award description, phrase match against IPEDS names, former names, `inst_alias` and generated acronyms | 59% | 55 | The main way a Host different from the Recipient is found. |
| **Campus words** from the description or the ED "Recipient/ campus" text, checked only against the Recipient's sibling campuses | 6% | 7 | Small but decisive: UC Clermont, OSU ATI, UNM Gallup, Purdue Northwest, UM-Dearborn, USC Sumter. 784 ED rows carry a "/ campus" suffix. |
| `recipient_name_raw` | 2% | 0 | Rarely adds anything, as #3 found. |
| Address (= place of performance) | 97% | 0 | Used only to break ties, never to find candidates, because it is the Recipient's SAM address (#3). |

**An alias table was not needed beyond what IPEDS provides.** IPEDS gives names back to 2015, which covers former names such as "West Hills College Lemoore" and "Northern Vermont University". It also gives `inst_alias`, generated acronyms (e.g. "HGTC") and `newid` merge links. Together these covered every alias case in the #3 sample. A hand alias table would add little until the review queue shows which aliases recur.

## Case taxonomy

The case labels are the rule that fired. They are in `links.csv` / `review_queue.csv`.

### Easy: automatic, one Host

| Case | Grants | What it is |
|---|---|---|
| `uei_confirmed` | 2,785 | UEI points to one campus, and the name, ED list or description agrees |
| `campus_text_confirmed` | 417 | Only one college is a candidate. The description or ED list names it, and the name or address agrees. All 419 are colleges whose UEI is not in IPEDS. |
| `campus_named` | 113 | A system Recipient. Campus words in the description or ED text pick one sibling campus, and the UEI agrees or is silent. |
| `campus_text_picks_one` | 109 | Several candidates. Exactly one is named in the description or ED list. |
| `uei_only` | 92 | UEI → one campus, no other signal. Spot checks were clean. |
| `district_is_recipient` | 34 | The Recipient is a school district (name and address match CCD) |
| `name_and_address` | 28 | No UEI in IPEDS. The name and address match one college. |
| `district_named_in_desc` | 27 | A nonprofit or GEAR UP partnership whose description names exactly one district |
| `campus_named_overrides` | 23 | Campus words name a sibling campus *other than* the UEI's unit (e.g. Los Rios → American River College) |
| `ed_list_and_desc_agree`, `uei_vs_name_conflict` | 35 | Conflicting candidates, settled by the ED list plus the description, or by UEI plus address |
| `…+followed_ipeds_merge` | 25 | The matched unit was later merged in IPEDS (PennWest, Commonwealth U, CT State, Vermont State, Penn State campuses), and the link moved to the surviving unit, in the same state only |

### No single Host: automatic

| Case | Grants | What it is |
|---|---|---|
| `nonprofit_no_site_named` | 185 | A community nonprofit whose description names no school, district or one-district city. **This is the weakest automatic case:** 1 of 5 fresh checks and 2 of #3's labelled Grants actually named schools in shorthand ("OMAHA BENSON", "THORNWOOD", "MT. TAHOMA LINCOLN"). |
| `gearup_partnership_no_district_named` | 82 | A GEAR UP partnership (P334A) whose college or agency Recipient names no district. The college partner is never treated as the Host. |
| `gearup_state` | 38 | A GEAR UP State grant (P334S) |
| `state_agency_no_site_named` | 4 | A statewide agency (VSAC, Wisconsin DPI) |

### Needs a person: the review queue (318 Grants)

| Case | Grants | What the reviewer sees |
|---|---|---|
| `city_named_with_one_district` | 70 | A nonprofit's description names a city that has exactly one regular district ("LNESC PHILADELPHIA"). This is a hint, never accepted automatically: it is wrong for "SAN MATEO COUNTY" and for "POST-SECONDARY" → Post ISD. |
| `several_campuses_named` | 57 | Two or more colleges are named, e.g. consortia ("UMPI/UMFK") or a Recipient that also names a partner college |
| `system_campus_by_address` | 38 | One UEI covers many campuses and the description names none, so the address points at the main campus (Kent State, Pitt, Miami regional). #3 found the main campus is often but not always right. |
| `school_named_needs_school_lookup` | 35 | The description names a high school, not a district. Fixable by adding the CCD *school* directory (school → LEAID). |
| `campus_text_overrides_uei` | 22 | The description names a campus the UEI doesn't point to, and nothing else confirms it |
| `district_weak_signal` | 11 | Several one-district cities named ("ALVARADO, KEENE, RIO VISTA") |
| `system_campus_not_stated` | 9 | Several campuses share UEI, name and address (Delaware Tech) |
| `single_weak_signal:*`, `uei_only_non_college`, `only_candidate_is_system_office` | 22 | One weak signal only, or the only candidate is an IPEDS system office (sector 0) |
| `unmatched` (`no_candidate_*`) | 54 | Nothing found. About a third are nonprofits whose names contain "College", "Institute" or "Education" and so are treated as colleges or districts (Harlem Center for Education, Academic Institute of Central Carolina, College Success Foundation); these should become "no single Host" with a better Recipient-type rule. Also regional service agencies whose CCD names differ (ESC Region XII, Region One, Multnomah ESD, NW Tri-County IU); statewide bodies (Montana Board of Regents, WV HEPC); Palau and the Marshall Islands, which the same-state filter drops; and college legal names no IPEDS name resembles ("Palo Verde CCD Financing Corporation", "University Corporation at Monterey Bay") |

`review_queue.csv` holds all 318 Grants. Each row has its candidates and the signals behind each candidate, so a reviewer chooses from a short list instead of searching.

## Choices the prototype made that #11 must confirm

These follow #3's hand-labelling rules. They are policies, not facts:

1. **GEAR UP partnerships:** the Host is a district (named in the description, or the Recipient itself), never the college partner. With no district named, the result is "no single Host".
2. **IPEDS merges:** link to the surviving unit, but only within the state. Mills College → Northeastern University (Boston) is blocked, and the link goes to "Northeastern University Oakland" instead. The alternative is to keep the unit as of the Grant's start year. This choice matters for Penn State (its campuses merged into one UNITID) and for PennWest and Commonwealth U.
3. **Administrative units (IPEDS sector 0)** never win when a real campus is also a candidate. When the only candidate is a system office, the Grant goes to review.
4. **Nonprofits naming no site are "no single Host".** If shorthand school names are too costly to miss, send these 185 to a low-priority review instead. That costs a person about 185 quick looks.
5. **Same-state only**, for UEI, name and description matching alike. The out-of-state cases #3 found (LULAC DC → Oxnard; FCE Illinois → Corpus Christi) become "no single Host" or review, never a cross-state link.

## Not done / next

- **CCD school directory** (school → LEAID): would clear most of `school_named_needs_school_lookup` and some `nonprofit_no_site_named`. Not downloaded.
- **Other years:** FY2024 only. ED lists for FY2025 exist. FY2021–23 lists are partial (#16).
- **ED list as its own check:** 30 FY2024 ED rows have no FY2024 USAspending action. That is #8's reconciliation, not linking.
- **Second reviewer:** every judgment here, and in #3, is one person's call.

## Files

- `link_hosts.py`: the whole prototype, run as below.
- `links.csv`: one row per Grant, with outcome, case, Host, candidates and signals, plus #3's label where one exists.
- `review_queue.csv`: the `review` and `unmatched` rows.
- `holdout_judgments.csv`: 178 hand checks of automatic decisions outside #3's sample. Round 1 (98, seed 20261016) was used to find bugs. Round 2 (80, seed 20261017) was drawn after the bug fixes and gives the accuracy figure. A later fix sent one round-2 row (Miami Dade College, judged wrong) to review, so the figure uses the other 79.
- `run_output.txt`: console output of the final run.

## Reproduce

```
uv venv -p 3.12 /tmp/topo_proto/.venv && uv pip install -p /tmp/topo_proto/.venv polars==2.0.0 pdfplumber==0.11.10 rapidfuzz==3.14.6
cp docs/research/recipient-vs-host-institution.md /tmp/topo_proto/rvh.md
/tmp/topo_proto/.venv/bin/python -I prototypes/host-linking/link_hosts.py \
  --archive <FY2024_091_Assistance_Full_20261007_1.csv> --ipeds <colleges_ipeds_directory.csv> \
  --lea <school-districts_lea_directory.csv> --ed-dir data/raw/ed_grantee_lists \
  --gold /tmp/topo_proto/rvh.md --out /tmp/topo_proto/out
```

Run with Python 3.12. It takes about 2 minutes.

| Input | Source | sha256 |
|---|---|---|
| USAspending FY2024 ED assistance archive (CSV inside `FY2024_091_Assistance_Full_20261006.zip`, zip sha256 `ca9543ef…7e0f`) | `files.usaspending.gov/award_data_archive/`, as in #3 | `ba0c7fc5573a82830d0aeef8ed5424fd798cdf429493446a98f1da43df477337` |
| IPEDS directory, all years (names used from 2015, UEIs from 2022) | `educationdata.urban.org/csv/ipeds/colleges_ipeds_directory.csv` (Urban Institute Education Data Portal v0.27.0, ODC-By) | `26b451e7cd4adb4eeef01eb9e3f2556739672d46868a681690d56c91152ab088` |
| CCD LEA directory (year 2024; agency types 1, 2, 4, 5, 7) | `educationdata.urban.org/csv/ccd/school-districts_lea_directory.csv` | `144db253d2602ab207130263bbdfe4aa09f937b6a55aa48eb7603d66eb957bec` |
| ED FY2024 grantee lists, 7 TRIO PDFs | `data/raw/ed_grantee_lists/` (hashes in `manifest.csv`) | — |
| #3 hand labels (Appendix B) | `docs/research/recipient-vs-host-institution.md` (merged to `main` from `research/recipient-vs-host`, d4a43fc) | — |
