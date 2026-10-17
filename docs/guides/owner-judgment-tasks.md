# Owner judgment tasks

This guide is for the repo owner. It tells you how to do each task in the `topo` pipeline that needs a person's judgment, and why. The code does the rest.

The guide is written in a simplified form of technical English. The terms in **bold** in the glossary at the end have one meaning each. The guide uses them as `GLOSSARY.md` gives them.

Sources: the spec (#28), [ADR 0002](../adr/0002-host-linking-is-a-rule-cascade-gated-by-case-label-accuracy.md), [ADR 0003](../adr/0003-provenance-by-carried-keys-and-as-of-snapshots.md), `GLOSSARY.md`, `prototypes/host-linking/README.md`, `config.toml` and the code under `src/topo/`.

## Rules for all tasks

- Run every command from the repository root. The guide writes each command as `uv run topo ...`.
- The files in `data/curated/` are committed. After you change one of them, commit it before the next run. If you do not, the dirty-tree guard stops the run (task 8).
- A rerun never overwrites a delivered file. A second file with the same Pull date gets a `_v2` suffix, then `_v3`, and so on.
- Each delivered file has a sidecar, `<file name>.provenance.json`. The sidecar gives the commit, the As-of date, the config hash and the dirty flag.

Abbreviations: ED is the U.S. Department of Education. FY is the federal fiscal year. FAIN is the Federal Award Identification Number, which identifies a **Grant**. UEI is the Unique Entity ID of a **Recipient**. IPEDS is the college directory, and UNITID is its college ID. CCD is the school-district directory, and LEAID is its district ID. NIA is an ED notice inviting applications. CSV is a comma-separated text file.

## Task order

Do the tasks in this order around the first real run. Tasks 2 and 3 then repeat after each delivered run.

| Order | Task | When |
|---|---|---|
| 1 | [6. Confirm the ASSUMPTIONs in `config.toml`](#6-confirmed-assumptions) | Done on 2026-10-17. Before the first real run. |
| 2 | [7. Check the missing ED grantee lists](#7-missing-ed-grantee-lists) | Before the first real run. Act only if a list turns up. |
| 3 | [5. Check the curated reference files](#5-keep-the-curated-reference-files-up-to-date) | Before the first real run. The files are filed; check the Talent Search FY2026 deadline. |
| 4 | [8. Commit everything; use `--allow-dirty` only for trials](#8-the-dirty-tree-guard-and---allow-dirty) | Before every run. |
| 5 | First real run: `uv run topo run` | After steps 1 to 4. |
| 6 | [4. Freeze the FY2027 predictions](#4-freeze-the-fy2027-predictions) | Right after the first real run, and before 2026-12-16. Time-critical. |
| 7 | [1. Label the frozen answer key](#1-label-the-frozen-answer-key) | After the labelling sheet is available. |
| 8 | [2. Decide items in the review queue](#2-decide-items-in-the-review-queue) | After each delivered run. |
| 9 | [3. Run the founder spot-check loop](#3-run-the-founder-spot-check-loop) | After a delivered run. Repeat as needed. |

---

## 1. Label the frozen answer key

**Purpose:** Give about 200 **Grants** a hand-checked **Host institution**, so that each **Case label** gets a measured accuracy.

**Why:** The rules decide most Hosts without a person. A Case label can decide without a person only when it scores at least 95% with at least 10 checks on this key. If you change the rules to fit the key, the score measures memory, not accuracy. Thus the key is frozen, and a separate tuning set is the only set you change rules against.

**When:** After the first real run, when the labelling sheet is available. A separate step produces the labelling sheet from that run. Until the key exists, every Case label reports `unverified` and keeps its rule outcome.

### How the gate uses the key

The settings are in `config.toml`, section `[host_linking]`: `auto_accept_accuracy = 0.95` and `auto_accept_min_checks = 10`.

- A check is a FAIN that is in the key and that the Case label decided in this run.
- A check is correct when the rule's decision is the same as the key's `host` value.
- The pipeline scores the rule's decision before overrides. An override never changes a score.
- The pipeline scores only `host`. The `second_host` value feeds only the inter-rater agreement figure.

The match-quality report (`output/match_quality_<Pull date>.md`) gives each Case label one gating value:

| Gating value | Meaning |
|---|---|
| `auto-accepted` | At least 10 checks and at least 95% correct. The rule decides. |
| `demoted to review` | At least 10 checks and less than 95% correct. Each Grant the label decided goes to review. |
| `unverified` | Fewer than 10 checks. The rule outcome stays, but the report says it is not measured. |
| `not gated` | A review or unmatched label with at least 10 checks. It decides nothing, so nothing changes. |
| `override` | A reviewer decided this Grant (task 2). |

Note: with 10 checks, 95% means 10 of 10. One error demotes the label. With 20 checks, 19 of 20 passes. Thus a large Case label needs more than 10 checks.

### The sample

- Take about 200 Grants from the labelling sheet.
- Stratify the sample by Case label. Give each Case label that decides without a person at least 10 Grants.
- Oversample the weak cases that ADR 0002 names: `nonprofit_no_site_named`, `system_campus_by_address` and `uei_only`.
- Include Grants that the rules sent to review, and Grants with the outcome **No single Host**. The review rows show how often the pick shown in review is correct.
- Give about 40 rows a second label from a different reviewer. ADR 0002 says the founder or another reviewer does this second pass.

Note: `system_campus_by_address` is a review label in the code. Its checks show how good the address pick is, but they do not gate.

### How to decide the correct Host

The Host institution is the college or school district where the project runs. It is not the Recipient by default. Use the policies of ADR 0002:

1. A college Host is an IPEDS campus (UNITID). A district Host is a CCD district (LEAID).
2. For a GEAR UP partnership, the Host is a district, never the college partner. If no district is named, the answer is `no single Host`.
3. A GEAR UP State Grant is `no single Host`.
4. A statewide agency that names no site is `no single Host`.
5. A nonprofit that names no school, district or site is `no single Host`. Read the award text carefully first. The prototype found school names in shorthand, for example "OMAHA BENSON". A named school gives its district.
6. Use the same state as the Recipient only.
7. If IPEDS merged the campus, use the unit as of the Grant's start year. If that unit has no current record, use the surviving unit in the same state.
8. An IPEDS system office (sector 0) is never the Host when a real campus runs the project.
9. Use as evidence the ED grantee-list "Recipient/ campus" text, the award description and the campus's own web pages. Write the evidence in `note`.

### File format

File: `data/curated/host_answer_key.csv`. One row per FAIN. A FAIN must not repeat.

| Column | Value |
|---|---|
| `fain` | The Grant's FAIN, for example `P047A221553`. |
| `host` | `UNITID <id>`, `LEAID <id>` or `no single Host`. Examples: `UNITID 180595`, `LEAID 0100005`. |
| `reviewer` | Your name or initials. |
| `labelled_on` | The date you labelled the row, as `YYYY-MM-DD`. |
| `note` | The evidence, short. Can be blank. |
| `second_host` | The second reviewer's Host, in the same format. Blank on most rows. |
| `second_reviewer` | The second reviewer's name. Required when `second_host` has a value. |

The tuning set, `data/curated/host_tuning_set.csv`, has the same columns. It is a separate set that grows over time. The pipeline never scores it. Use it when you change a rule. A FAIN in both files stops the run.

As of 2026-10-17, the tuning set has 326 rows with `reviewer` = `prototype`. They come from the prototype's hand checks in `prototypes/host-linking/holdout_judgments.csv`. Thus a key Grant must not be one of these 326 FAINs.

### Steps

1. Open the labelling sheet.
2. Remove each FAIN that is also in `data/curated/host_tuning_set.csv`.
3. Count the rows for each Case label. Make sure each Case label that decides without a person has at least 10 rows.
4. For each Grant, read the evidence and apply the Host rules above.
5. Write `fain`, `host`, `reviewer`, `labelled_on` and `note` in `data/curated/host_answer_key.csv`.

   CAUTION: A spreadsheet program can remove the leading zeros of a LEAID. Edit the file as text, or import the columns as text.

6. If you cannot decide a Host from the evidence, remove that Grant from the sample.
7. Choose about 40 rows for the second pass. Include rows from the weak cases.
8. Send those FAINs to the second reviewer without your `host` values.
9. Write the second reviewer's answers in `second_host` and `second_reviewer`.
10. Do a trial run to check the file format: `uv run topo join --allow-dirty`.
11. Commit `data/curated/host_answer_key.csv`.
12. Calculate the hash: `shasum -a 256 data/curated/host_answer_key.csv`.
13. Write the hash in `config.toml`, section `[host_linking]`, key `answer_key_sha256`.
14. Commit `config.toml`.
15. Run the pipeline: `uv run topo run`.
16. Read the sections "Accuracy per Case label" and "Inter-rater agreement" in `output/match_quality_<Pull date>.md`.

### Check

- The run does not stop with a structural break.
- "Accuracy per Case label" shows at least 10 checks for each Case label you sampled.
- No sampled Case label that decides without a person shows `unverified`.
- "Inter-rater agreement" lists about 40 double-labelled rows and the disagreements.

### Do not

- Do not copy the #3 hand labels or `prototypes/host-linking/holdout_judgments.csv` into the key. Those labels tuned the rules. The holdout judgments are already in the tuning set.
- Do not change the key after you pin its hash. Any change to the file stops the run with "the frozen answer key host_answer_key.csv changed".
- Do not pin the hash before the second pass is complete.
- Do not change a rule because a key Grant failed. Find other Grants with the same problem, put them in the tuning set, and change the rule against those.
- Do not change `host` to agree with `second_host`. The agreement figure measures how often two careful people differ.
- Do not guess a Host. The format has no "unknown" value, so leave the Grant out.

---

## 2. Decide items in the review queue

**Purpose:** Choose the Host for each Grant that the rules sent to review, and record the decision as an override.

**Why:** A review Grant has candidates, but no rule can choose safely. A person chooses from a short list. The pipeline applies overrides last, after the rules and the gate, so a decision survives each rerun. A Grant without a decision stays "in review" on the target list. The pipeline never accepts or drops it silently.

**When:** After each delivered run. A Case label that becomes `demoted to review` adds all of its Grants to the queue.

### The review queue

File: `output/review_queue_<Pull date>.csv`. One row per (FAIN, candidate). The order is by `Dollars`, then `Succession impact`, then FAIN.

| Column | Meaning |
|---|---|
| `Priority` | The Grant's place in the queue. 1 is first. |
| `FAIN` | The Grant. |
| `Recipient`, `Recipient UEI`, `State` | The legal holder of the Grant. |
| `Program` | The **Program**. |
| `Case label` | The rule that sent the Grant to review. |
| `Gating` | `demoted to review` means the label failed the gate and its pick is shown here. |
| `Dollars` | Obligations over the reporting window. |
| `Succession impact` | Other Grants with the same Recipient and Program. Your decision can make or break their Succession links. |
| `Candidate host ID` | `UNITID <id>` or `LEAID <id>`, in the same format as the overrides file. |
| `Candidate host` | The candidate's name. |
| `Signals` | The signals for this candidate, joined by `+`. |

The signals, from strongest to weakest (ADR 0002):

| Signal | Meaning |
|---|---|
| `uei` | The Recipient UEI is on this IPEDS unit, in the same state. |
| `fac_uei` | A same-state Federal Audit Clearinghouse (FAC) auditee with this UEI has the unit's exact name. Used only when no IPEDS unit lists the UEI. |
| `ed_list` | The ED grantee list names this unit for the same FAIN. |
| `ed_campus` | The campus words in the ED list text name this sibling campus. |
| `desc_campus` | The campus words in the award description name this sibling campus. |
| `desc` | The award description names this unit. |
| `name` | The Recipient name matches this unit's name. |
| `address` | The address matches. This signal only breaks a tie. |

ED text outranks the description. A candidate with `address` only is weak, because the address is the Recipient's address.

### The overrides file

File: `data/curated/host_overrides.csv`.

| Column | Value |
|---|---|
| `fain` | The Grant's FAIN. |
| `host` | `UNITID <id>`, `LEAID <id>` or `no single Host`. |
| `reviewer` | Your name or initials. |
| `date` | The decision date, as `YYYY-MM-DD`. |
| `note` | The evidence, short. |

Rules for the file:

- A FAIN can have several rows. The row with the latest `date` applies.
- Two rows for one FAIN must not have the same `date`. That stops the run.
- To change a decision, add a new row with a later date. Keep the old row. Git keeps the history.
- An override sets the outcome to `matched`, or to `no_single_host` for `no single Host`. The Case label becomes `override`.
- Overrides also apply to lookback Grants, so they feed Succession links.

### Steps

1. Open the latest `output/review_queue_<Pull date>.csv`.
2. Start at the lowest `Priority` value that has no decision.
3. Read all candidate rows for that FAIN and their `Signals`.
4. Check the candidates against the evidence: the ED list text, the award description and the campus web pages.
5. Apply the Host rules of task 1.
6. If one candidate is correct, copy its `Candidate host ID` into `host`.
7. If no candidate is correct but the evidence names the Host, write that Host's ID.
8. If the evidence gives no single Host by the rules, write `no single Host`.
9. If you cannot decide, write nothing. The Grant stays in review.
10. Add the row to `data/curated/host_overrides.csv`.
11. Commit the file.
12. Run the pipeline: `uv run topo run`.

You can also override a Grant from the "Unmatched list" section of the match-quality report. The queue holds review Grants only.

### Check

- The run gives no warning that a Host override names a FAIN not in this run.
- The Grant is not in the new review queue.
- The "Overrides" section of the match-quality report counts it.
- On the target list, its Host confidence is `matched` or `lower-confidence: no single Host`.

### Do not

- Do not copy the `Candidate host` name into `host`. Use the ID.
- Do not delete an old override row to change a decision.
- Do not ignore the warning "Host override names a FAIN not in this run". The pipeline does not apply that override. Add a new row with the correct FAIN.
- Do not add an override because of a founder mark alone (task 3).
- Do not add an override to improve a Case label's score. Scores use the rule's decision before overrides.

---

## 3. Run the founder spot-check loop

**Purpose:** Get the founder's marks on 2 or 3 states and record them as **Review findings**.

**Why:** The founder knows some states well and can see errors that the rules cannot. The findings are kept apart from the answer key, so the accuracy figures stay independent. A finding is a claim, not evidence. Thus a finding never changes the overrides file by itself.

**When:** After a delivered run, when you want fresh marks from the founder.

### Steps

1. Find the spot-check copy that `topo report` wrote: `output/spot_check_<Pull date>.xlsx`. It can have a `_v2` suffix.
2. Make sure its sidecar shows `"dirty": false`.
3. Send that file to the founder. Do not change it first.
4. Tell the founder to pick 2 or 3 states on the "States" sheet.
5. Tell the founder to fill "Looks right?" with `ok`, `wrong` or `stale` on the "Target list" and "Ended" sheets.
6. Tell the founder to pick the column in "Field" for each `wrong` or `stale` row.
7. Tell the founder that "Note" holds at most 100 characters.
8. Tell the founder to list Grants they know but do not see on the "Missing" sheet.
9. Tell the founder not to write client or personal names.
10. Save the returned workbook outside the repository, or under `output/`. Git ignores `output/`.
11. Ingest it: `uv run topo ingest-findings <path to workbook> --date <YYYY-MM-DD>`. The date is the day the founder did the review.
12. Commit `data/curated/review_findings.csv`.
13. List the findings with `mark` = `wrong` and `field` = `Host institution`, `Host ID` or `Host confidence`.
14. Check each of these Host marks against the evidence, as in task 2.
15. If the evidence agrees with the founder, add an override (task 2). Write the finding's date in `note`.
16. If the evidence does not agree, add no override.
17. Check `stale` marks and "Missing" rows against the sources. They change nothing by themselves.
18. Commit and run the pipeline: `uv run topo run`.

CAUTION: The ingest stops on a bad mark, on a "Field" that is not a column, or on a long "Note". Then ask the founder to correct the cell. Do not change the founder's marks yourself.

### Check

- The ingest prints "appended N Review findings to" and the path of `review_findings.csv`.
- The "Founder spot-check" section of the match-quality report shows the review date, the states and the counts of `ok`, `wrong`, `stale` and Missing.
- In the next run, the target list column "Last founder mark" shows each mark, for example `wrong (Host institution) on 2026-10-20: <note>`.

### Do not

- Do not edit `data/curated/review_findings.csv` by hand. It is write-once and the ingest only appends.
- Do not ingest one workbook twice with different dates. The second ingest adds every mark again.
- Do not copy findings into the answer key or the tuning set.
- Do not add an override without evidence. The spec requires each `wrong` Host mark to be checked first.

---

## 4. Freeze the FY2027 predictions

**Purpose:** Record the FY2027 TRIO renewal-timing predictions one time, before the competitions occur.

**Why:** A prediction is a real test only if it is fixed before the result is known. `topo freeze` writes the file once and stamps it with the As-of date, the commit, the config hash and the rule version. If anyone edits the file, the later score has no value. Each later scoring goes to a new file, so the frozen file stays as it is.

**When:** One time, inside the window that these two limits give. The first real run already falls inside it.

- **Earliest:** a run whose As-of date is 2026-06-10 or later. The FY2027 Predicted due dates are the FY2022 deadlines plus 60 months: Upward Bound 2027-01-31, McNair 2027-04-25, Upward Bound Math and Science 2027-06-03 and Veterans Upward Bound 2027-06-10. A Grant is flagged only when its Predicted due date is at most 12 months after the As-of date. With an earlier As-of date, some of the four Programs get no flagged Grants.
- **Latest:** the day before the Federal Register publishes the first FY2027 notice inviting applications for any of the four Programs. As of 2026-10-17, none is published. The FY2022 notices appeared on 2021-12-16 (Upward Bound), 2022-03-09 (McNair), 2022-04-19 (Upward Bound Math and Science) and 2022-04-26 (Veterans Upward Bound). Thus the first FY2027 notice can appear from about mid-December 2026. Freeze before 2026-12-16, and search the Federal Register on the day you freeze.

### Steps

1. Make sure `data/curated/deadlines.csv` has the FY2017 and FY2022 rows for the four Programs above. It has them as of 2026-10-17.
2. Search the Federal Register for an FY2027 notice for the four Programs. If one exists, the freeze is late. Write that in the commit message.

   CAUTION: Do not add an FY2027 deadline row before you freeze. If you do, the "prediction" uses the real date.

3. Commit all changes.
4. Run the pipeline: `uv run topo run`.
5. Read "Renewal-timing backtest (FY2022)" in the match-quality report. Write the result in your commit message. The freeze does not need a pass.
6. Make sure the As-of date of the run is 2026-06-10 or later. The sidecars show it.
7. Freeze: `uv run topo freeze`.
8. Open `data/curated/fy2027_predictions.csv`. Make sure it has one row for each of the four Programs, with `timing` = `predicted`.
9. Add the file and its sidecar: `git add data/curated/fy2027_predictions.csv data/curated/fy2027_predictions.csv.provenance.json`.
10. Commit the two files.
11. Tag the commit: `git tag fy2027-predictions`.
12. Push the commit and the tag.
13. Merge with a merge commit, not a squash. The tagged commit must stay in the history of `main`.

### Later: score the predictions

Do this after ED publishes the FY2027 notices and the new Cohort's FAINs appear in USAspending.

1. Add the FY2027 deadline rows to `data/curated/deadlines.csv`, with citations.
2. Commit the file.
3. Pull fresh USAspending data: `uv run topo pull usaspending`.
4. Run the pipeline: `uv run topo run`.
5. Score: `uv run topo score-predictions`.
6. Read the output. If the frozen file differs from the tagged copy, the command warns: "Warning: data/curated/fy2027_predictions.csv differs from the copy tagged fy2027-predictions".
7. If you get that warning, do not use the score. Find the edit with `git diff fy2027-predictions -- data/curated/fy2027_predictions.csv`.
8. Commit `data/curated/fy2027_predictions_scored_<As-of>.csv` and its sidecar.

The scored file gives, per Program: `actual_deadline`, `timing_error_months`, `recall`, `precision` and `result`. The `result` is `pass`, `miss` or a `not scored: ...` reason. A missing deadline row gives `not scored: no deadline for the competition in the deadline table`. A Cohort not yet in the pull gives `not scored: the competition's Cohort is not in the pull yet`. You can score again on a later As-of date. Each scoring is a new file.

### Check

- `topo freeze` prints the file path and a reminder to commit and tag.
- `git tag --list fy2027-predictions` shows the tag.
- `git log -1 fy2027-predictions -- data/curated/fy2027_predictions.csv` shows your freeze commit.
- Each row has `evidence_tier`, `timing` and `flagged_fains`. A Program with `date unknown` shows a deadline row is missing.
- `flagged_fains` has a value on each row. An empty value shows that the As-of date was too early.
- `uv run topo score-predictions` gives no "differs from the copy tagged" warning.

### Do not

- Do not edit, delete or recreate `data/curated/fy2027_predictions.csv`. `topo freeze` refuses when the file exists. Do not delete it to get around that.
- Do not freeze with `--allow-dirty`. The stamp must name a clean commit.
- Do not add FY2027 deadline rows before the freeze.
- Do not wait for a backtest pass. A frozen record of a weak rule is still a valid test.

---

## 5. Keep the curated reference files up to date

**Purpose:** Keep the hand-filed facts current and cited: deadlines, appropriations, ED allocations and cause notes.

**Why:** The pipeline never invents a number or a cause. Each fact in these files must trace to a public source, so every row has a citation. A cause note says why a Grant lost money. It needs a source and a docket entry or a page, because a funding pattern alone never proves a cause.

**When:** Each time ED publishes a notice, a budget table or a program page, or a court record names a FAIN.

As of 2026-10-17, the files hold:

| File | Rows | Content |
|---|---|---|
| `deadlines.csv` | 24 | Every TRIO competition from FY2015 to FY2026 that the current and previous Cohorts need, with FY2017 and FY2022 for Upward Bound, Upward Bound Math and Science, Veterans Upward Bound and McNair. Also 7 GEAR UP rows, which no rule reads. |
| `appropriations.csv` | 4 | TRIO, FY2021 to FY2024. |
| `ed_program_allocations.csv` | 35 | The seven TRIO Programs, FY2021 to FY2025. FY2025 has award counts only, because ED did not publish dollars. |
| `cause_notes.csv` | 11 | The Grants that ED's filings in the COE court cases name by FAIN. |

### The files

**`data/curated/deadlines.csv`** gives one published application deadline per (Program, competition FY).

| Column | Value |
|---|---|
| `program` | The exact Program name (list below). |
| `competition_fy` | The FY of the competition, as the notice names it. This is the FY of the new Cohort. |
| `application_deadline` | `YYYY-MM-DD`. |
| `citation` | Required. The notice, for example its Federal Register title and date. |
| `source_url` | The notice URL. |
| `note` | For example, a reopened deadline. |

**`data/curated/appropriations.csv`** gives the enacted appropriation per Program family and FY.

| Column | Value |
|---|---|
| `program_family` | `TRIO` or `GEAR UP`. |
| `fiscal_year` | For example `2024`. |
| `amount_usd` | Whole dollars. |
| `citation` | Required. |
| `note` | Optional. |

**`data/curated/ed_program_allocations.csv`** gives ED's published allocation and number of awards per Program and FY.

| Column | Value |
|---|---|
| `program` | The exact Program name. |
| `fiscal_year` | For example `2024`. |
| `allocation_usd` | Whole dollars. Blank when ED did not publish it. |
| `award_count` | Blank when ED did not publish it. |
| `citation` | Required. |
| `note` | Optional. |

**`data/curated/cause_notes.csv`** gives a cited cause for one FAIN.

| Column | Value |
|---|---|
| `fain` | The FAIN in capitals, for example `P217A220172`. |
| `cause_note` | The cause, as the source states it. |
| `source` | Required. For example the case name and number. |
| `docket_entry` | The docket entry, for example `ECF 14`. You need this or `page`. |
| `page` | The page. You need this or `docket_entry`. |
| `source_url` | The document URL. |

The exact Program names are: `Student Support Services`, `Talent Search`, `Upward Bound`, `Upward Bound Math and Science`, `Veterans Upward Bound`, `Educational Opportunity Centers`, `McNair`, `GEAR UP partnership` and `GEAR UP state`.

### What is still missing

Two deadline items are still open. No other deadline row is missing for the current rules.

| Item | State | What to do |
|---|---|---|
| FY2027 deadlines for Upward Bound, Upward Bound Math and Science, Veterans Upward Bound and McNair | ED has published no FY2027 notice yet. | Add each row only after you freeze (task 4) and after the notice is published. Scoring needs these rows. |
| Talent Search FY2026 | The row uses the Federal Register date, 2026-05-01. Grants.gov shows a later date, 2026-07-09, for ED-GRANT-26-022. No Federal Register extension notice was found. The row's `note` records this. | Search the Federal Register for an extension notice. If you find one, change the date and the citation in the existing row. Do not add a second row. |

The Talent Search date sets the FY2021 Cohort's Predicted due date (`notice published`) and the FY2026 Cohort's date (`inferred`, 60 months later).

The other files have these gaps. None of them stops a check:

| File | Gap | Effect |
|---|---|---|
| `appropriations.csv` | TRIO FY2025 and FY2026; GEAR UP for all years. | The TRIO check for FY2025 and later reads `not_published`, because ED published no allocation dollars. No check reads GEAR UP appropriations. You can add the rows from `docs/research/trio-gearup-funding-and-cycles.md`, section 1a. That note gives thousands of dollars. |
| `ed_program_allocations.csv` | FY2025 dollars; GEAR UP for all years. | ED did not publish FY2025 dollars, so the cells stay blank. GEAR UP rows can come from section 1c of the same note. |
| `cause_notes.csv` | Grants named only in sealed or paid filings. | Add a row only when a public source names the FAIN. |

GEAR UP needs no deadline rows. GEAR UP rows say "competes most years; timing not predicted".

### Steps: add a new competition's deadline

1. Find the ED notice inviting applications in the Federal Register.
2. Read the Program, the competition FY and the application deadline from the notice.
3. Add one row to `data/curated/deadlines.csv`.
4. Write the notice title and date in `citation` and its URL in `source_url`.
5. If ED reopened the deadline, keep the original date and write the reopening in `note`.
6. Commit the file.
7. Run the pipeline: `uv run topo run`.

### Steps: add appropriations, allocations and cause notes

1. Find the figure or the cause in the primary source.
2. For an amount in thousands, multiply by 1,000.
3. For a figure ED did not publish, leave the cell blank.
4. For a cause note, make sure the source names the FAIN.
5. Write the docket entry or the page.
6. Add the row and its citation.
7. Commit the file.
8. Run the pipeline: `uv run topo run`.

### While a Program has no deadline

- Its Cohort's timing reads `date unknown`. It shows the predicted competition FY, but no Predicted due date.
- No Grant of that Program can be **Re-competing soon**, so none goes to **Priority tier** 2.
- The FY2022 backtest for it reads `not scored: no deadline for the competition in the deadline table`, or it misses.
- The frozen FY2027 file records `date unknown` for it.

### Check

- The run does not stop. A schema failure names the file and the column.
- In the match-quality report, the backtest and Cohort tables show `notice published` or `inferred`, not `date unknown`, for the Programs you filled.
- In the reconciliation table (`output/reconciliation_<Pull date>.csv`), the rows you filled no longer read `not_published`.
- On the target list, each Grant with a cause note shows the citation in "Cause note".

### Do not

- Do not write `0` for a figure ED did not publish. Leave it blank.
- Do not write thousands where the column needs whole dollars.
- Do not add a cause note that a funding pattern suggests but no source states.
- Do not add a row without a citation. The schema refuses it.
- Do not use a Program name that differs from the list. The schema refuses it.
- Do not add two rows for one Program and competition FY.

---

## 6. Confirmed ASSUMPTIONs

**Purpose:** Know each value in `config.toml` that rests on an ASSUMPTION, and change one only in the correct way.

**Why:** The spec marks guesses as ASSUMPTION so that the founder can overturn them. Tolerances, windows and thresholds are fixed before the first run. If you change one to close a reconciliation gap or to pass a gate, the result no longer means anything. Thus a change must come from a new decision, made before a run, never from a result.

**When:** The owner confirmed all of these values on 2026-10-17. Each ASSUMPTION comment in `config.toml` ends with the line "Confirmed by the owner 2026-10-17." Change a value only when the founder makes a new decision.

| Section | Key | Value | What it controls |
|---|---|---|---|
| `[tolerances]` | `reconciliation_count_relative` | `0.01` | ED award counts against USAspending Grants funded: within 1%. |
| `[reconciliation]` | `evidence_large_share_overall` | `0.05` | ED-list evidence of unfunded Budget periods is "large" at 5% or more overall. |
| `[reconciliation]` | `evidence_large_share_program_fy` | `0.10` | The same, over 10% in any Program and FY. |
| `[funding_status.budget_periods]` | `TRIO` | `5` | Budget periods in a full TRIO project period. |
| `[funding_status.budget_periods]` | `"GEAR UP"` | `6` | Budget periods in a full GEAR UP project period. |
| `[host_linking]` | `auto_accept_accuracy` | `0.95` | The gate's accuracy bar. |
| `[host_linking]` | `auto_accept_min_checks` | `10` | The gate's minimum checks. |
| `[lookback]` | `cohort_min_share` | `0.5` | An FY is a Cohort start when its new awards are at least half of the Program's largest yearly count. |
| `[renewal_timing]` | `lead_months` | `12` | Re-competing soon starts 12 months before the Predicted due date. |
| `[renewal_backtest]` | `pass_bar` | `0.95` | The backtest's recall and precision bar. |
| `[spot_check]` | `min_states` | `2` | The fewest states the founder checks. |
| `[spot_check]` | `max_states` | `3` | The most states the founder checks. |
| `[fac]` | `plausibility_years` | `5` | Fiscal years summed in the FAC check. |
| `[fac]` | `audit_lag_years` | `1` | Years left out because audits are still being filed. |
| `[fac]` | `plausibility_ratio_low` | `0.5` | A FAC ratio below this is flagged `review`. |
| `[fac]` | `plausibility_ratio_high` | `1.5` | A FAC ratio above this is flagged `review`. |

The other tolerances, for example `reconciliation_relative` and `reconciliation_absolute_usd`, are decisions from #14. The same rule applies to them.

### Steps: change one value

1. Get the founder's decision in writing.
2. Edit the value in `config.toml`.
3. Edit the comment above it. Keep the word ASSUMPTION. Replace the "Confirmed by the owner" line with the new decision, its reason and its date.
4. Commit `config.toml`. Write the reason in the commit message.
5. Run the pipeline: `uv run topo run`.

### Check

- The new sidecars show a new `config_sha256`.
- Earlier outputs keep their old sidecars, so each output still states the config it used.

### Do not

- Do not change a value after you see a gap, a demotion or a backtest miss.
- Do not change a value for one run and then change it back.
- Do not change a value in a run that uses `--allow-dirty`.

---

## 7. Missing ED grantee lists

**Purpose:** Know what the 11 missing ED grantee lists mean, and add one if it turns up.

**Why:** ED does not publish some TRIO lists for FY2021 to FY2023 (issue #16). The spec puts their recovery out of scope. The pipeline records each gap and never chases it. ed.gov blocks automated clients, so a person downloads each list by hand.

**When:** Nothing to do until a missing list turns up.

The manifest, `data/raw/manifest.csv`, has a `missing` row for each gap:

| Manifest program | Missing FYs |
|---|---|
| `ub_84047A` | 2021, 2022, 2023 |
| `ts_84044` | 2021, 2022 |
| `sss_84042A` | 2021, 2022 |
| `eoc_84066A` | 2021, 2022 |
| `mcnair_84217A` | 2021, 2022 |

### What this means

- In the reconciliation table, the `ed_list_dollars` and `ed_list_count` rows for these Program-years have the Reconciliation status `not comparable` and the Gap reason code `no_ed_list`. They are not failures and they never warn.
- These Grants have no `ed_list` signal in those years, so Host linking has one signal fewer.
- The ED "Recipient/ campus" text and participant counts are blank in those years, not zero.
- ED-list evidence of unfunded Budget periods is not available for those years.

### Steps: add a list that turns up

1. Download the list in a browser from the ED program page.
2. Make sure it is a `.pdf` or `.xlsx` file. The cleaner has no reader for other TRIO formats.
3. Name it `<manifest program>__FY<fy>__<original name>`, for example `ub_84047A__FY2022__<original name>`.
4. Put it in `data/raw/ed_grantee_lists/`.
5. Keep a backup copy. Git ignores raw files.
6. Get the size: `wc -c < <file>`.
7. Get the hash: `shasum -a 256 <file>`.
   CAUTION: The manifest is append-only. Do not change or delete the `missing` row. When two rows name the same program and FY, the later row wins.

8. Add a new row at the end of `data/raw/manifest.csv`.
9. Set `source` to `ed_grantee_lists`, `program` to the manifest program, `fy` to the FY and `status` to `ok`.
10. Fill `source_page_url`, `file_url`, `pull_date` (the download date), `bytes`, `sha256`, `original_name` and `stored_path`.
11. Set `request` to `hand-downloaded from source_page_url`.
12. Copy `licence_citation` from the `missing` row. Write in `note` that the list was found later.
13. Do a trial clean: `uv run topo clean ed_grantee_lists --allow-dirty`.
14. Commit `data/raw/manifest.csv`.
15. Run the pipeline: `uv run topo run`.

### Check

- The clean does not stop. A wrong hash or size stops it with "fails its manifest checksum".
- The ED-list coverage shows that Program and FY as `ok`, not `missing`.
- For a PDF, the row count must equal the list's "Total No. of Projects". Otherwise the clean stops.
- In `output/reconciliation_<Pull date>.csv`, that Program and FY no longer read `no_ed_list`.

### Do not

- Do not automate a download from ed.gov.
- Do not search for the missing lists as a task. Add one only if it turns up.
- Do not edit or delete a manifest row. Append a new row.
- Do not put the new row above the `missing` row. The later row wins.

---

## 8. The dirty-tree guard and `--allow-dirty`

**Purpose:** Make each delivered output map to one commit.

**Why:** Each sidecar records the commit and a dirty flag. An output made from changed or untracked files cannot be rebuilt from its commit. Thus `clean`, `join`, `report`, `run`, `freeze` and `score-predictions` stop when the tree is dirty. `pull` and `ingest-findings` do not use the guard, because they write the files you then commit.

**When:** Before every run.

The guard counts tracked changes and untracked files that git does not ignore. `data/raw/` (except the manifest), `data/cleaned/`, `data/joined/`, `output/`, `.venv/` and `.env` are ignored. When the guard stops a run, it prints "the git tree at ... is dirty (uncommitted or untracked files); commit them or pass --allow-dirty", and the command exits with code 2.

### When `--allow-dirty` is acceptable

- A trial run, to check that an edited curated file or `config.toml` passes its schema before you commit it.
- Debugging on your own machine.

### When it is not acceptable

- Any output you send to the founder or publish.
- `topo freeze` and `topo score-predictions`. Their files are permanent records.
- A run after you change an ASSUMPTION value.
- As a way to skip a commit you forgot.

### Steps

1. Show the tree state: `git status --porcelain`.
2. If it lists files, commit them, or delete the files you do not need.
3. For a trial only, add `--allow-dirty`, for example `uv run topo run --allow-dirty`.
4. Before you deliver, commit all changes.
5. Run again without `--allow-dirty`.

CAUTION: A trial run also writes files in `output/` with the Pull date. The clean run then gets a `_v2` suffix. Send the version whose sidecar shows `"dirty": false`.

### Check

- The sidecar of each delivered file shows `"dirty": false` and a `commit` value.

### Do not

- Do not send a file whose sidecar shows `"dirty": true`.
- Do not use `--allow-dirty` as a habit.

---

## Glossary

Terms from `GLOSSARY.md`:

**Grant**: One funded project for one project period, identified by its FAIN. A renewal is a new Grant.

**Recipient**: The legal entity a federal award is made to, identified by its UEI.

**Host institution**: The college or school district a Grant's project runs at, identified by UNITID or LEAID. It can differ from the Recipient.

**Program**: One federal grant program a Grant belongs to, such as Upward Bound or GEAR UP state grants.

**Cohort**: The Grants of one Program awarded in one competition.

**Budget period**: The part of a Grant, usually 12 months, that one Continuation or the initial award funds.

**Succession**: The link from a Grant to the Grant that renewed it for the same Recipient, Program and Host institution.

**Case label**: The name of the rule that decided a Grant's Host link, for example `uei_confirmed`. Accuracy is measured per Case label.

**No single Host**: The outcome for a Grant that the rules decide has no one Host institution. It differs from unmatched (no candidate) and from review (a person must choose).

**Predicted due date**: The expected application deadline of a Program's next competition: the prior Cohort's published deadline plus 60 months. Tagged `notice published` or `inferred`.

**Re-competing soon**: A Lifecycle stage for a Grant whose Cohort's Predicted due date is 12 months or less away. Its latest readable Funding status must also be continued or funded late. Not used for GEAR UP.

**Priority tier**: The call-order bucket on each target-list row: 1 new, 2 re-competing soon, 3 continuing, 4 unfunded or reversed.

**Review finding**: One row in the write-once findings file. It records a spot-check mark (`wrong`, `stale`, or a Missing Grant) with the field and a short note. A finding never changes the overrides file by itself.

**Reconciliation status**: The outcome of one reconciliation row: reconciled, a stated difference, or not comparable. A tolerance fixed before the first run sets it.

**Gap reason code**: The closed-vocabulary label on a reconciliation row that does not reconcile, for example `no_ed_list` or `not_published`.

**Pull date**: The date a raw file or API response was fetched.

**As-of date**: The date a run reads the data as of. It defaults to the latest USAspending Pull date, never the clock.

Terms of this guide:

**Answer key**: `data/curated/host_answer_key.csv`. The frozen set of hand-checked Hosts that the gate scores.

**Tuning set**: `data/curated/host_tuning_set.csv`. The growing set of hand-checked Hosts you change rules against. The pipeline never scores it.

**Gate**: The test that lets a Case label decide without a person: at least 95% correct with at least 10 checks.

**Labelling sheet**: The sample of Grants for the answer key. A separate step produces it from the first real run.

**Override**: A reviewed decision in `data/curated/host_overrides.csv`: FAIN, Host, reviewer, date and note. The pipeline applies it last.

**Review queue**: `output/review_queue_<Pull date>.csv`. Each Grant in review, with its candidates and signals.

**Sidecar**: The `<file name>.provenance.json` file beside each delivered file.

**Structural break**: An error that stops a run, for example a schema failure or a duplicate key.
