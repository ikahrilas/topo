"""Seam 1: the target-list workbook (README, main, Ended and Missing sheets) and its CSV, via `topo run`.

Each row has one displayed label over Funding status and Lifecycle stage, and a Priority tier.
"""

from __future__ import annotations

from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, enrollment_row, write_csv
from support.usaspending import action, write_actions
from support.workbook import load_header, read_sheet, sheet_names, sheet_text

PULL = "2026-10-07"
WORKBOOK = f"target_list_{PULL}.xlsx"
MAIN = "Target list"


def grant(fain: str, start_year: int, years: int, amount: float = 100000, *, award_month: int = 5,
          start_month: int = 9, skip: tuple[int, ...] = (), **kw) -> list[dict]:
    """A Grant awarded in `award_month` of start_year with one 12-month Budget period per year
    starting in `start_month`; Budget periods whose index is in `skip` get no funding action."""
    rows = []
    for i in range(years):
        if i in skip:
            continue
        year = start_year + i
        start = f"{year}-{start_month:02d}-01"
        end_year, end_month = (year + 1, start_month - 1) if start_month > 1 else (year, 12)
        end = f"{end_year}-{end_month:02d}-{28 if end_month == 2 else 30 if end_month in (4, 6, 9, 11) else 31}"
        rows.append(action(fain, i + 1, f"{year}-{award_month:02d}-15", amount, (start, end),
                           action_type="A1" if i == 0 else "B1", **kw))
    return rows


TS = dict(recipient="IVY TECH COMMUNITY COLLEGE", uei="IVYTECHUEI01", state="IN")
REVERSED_ENDED = [  # final Budget period's Continuation reversed in full; the Grant has ended
    *grant("P044A210683", 2021, 5, 336357, award_month=6, **TS),
    action("P044A210683", 6, "2025-09-29", -336357, ("2025-09-01", "2026-08-31"), action_type="EX", **TS),
]
MCNAIR = dict(recipient="AUGSBURG UNIVERSITY", uei="MCNAIRUEI001", state="MN")
FUNDED_LATE_NOT_YET_READABLE = [  # final Budget period 2026-10-01 is not readable until 2026-12-30
    action("P217A220172", 1, "2022-07-01", 272360, ("2022-10-01", "2023-09-30"), action_type="A1", **MCNAIR),
    action("P217A220172", 2, "2023-07-12", 272360, ("2023-10-01", "2024-09-30"), **MCNAIR),
    action("P217A220172", 3, "2024-07-12", 272360, ("2024-10-01", "2025-09-30"), **MCNAIR),
    action("P217A220172", 4, "2026-03-13", 272360, ("2025-10-01", "2026-09-30"), **MCNAIR),
]

FIXTURE = [
    *grant("P042A260001", 2026, 1, award_month=8),                 # new, awarded 2026-08-15
    *grant("P042A260002", 2026, 1, award_month=5, start_month=6),  # new, awarded 2026-05-15
    *grant("P047A230003", 2023, 4),                                # continuing (4th of 5 Budget periods)
    *grant("P047A220004", 2022, 5),                                # final Budget period
    *grant("P066A230005", 2023, 3, skip=(2,)),                     # 2025-09-01 period unfunded
    *REVERSED_ENDED,
    *grant("P042A200010", 2020, 6),                                # ended 2026-08-31
    *FUNDED_LATE_NOT_YET_READABLE,
]


def by_fain(rows):
    return {r["FAIN"]: r for r in rows}


def test_each_row_has_one_displayed_label_beside_its_funding_status_and_lifecycle_stage(project):
    write_actions(project.raw_usaspending, PULL, FIXTURE)

    project.topo("run", "--as-of", PULL)

    path = project.output / WORKBOOK
    assert sheet_names(path) == ["README", MAIN, "Ended", "Missing"]
    rows = by_fain(read_sheet(path, MAIN) + read_sheet(path, "Ended"))
    shown = {fain: (r["Label"], r["Funding status"], r["Lifecycle stage"]) for fain, r in rows.items()}
    assert shown == {
        "P042A260001": ("New", "continued", "new"),
        "P042A260002": ("New", "continued", "new"),
        "P047A230003": ("Continuing", "continued", "continuing"),
        "P047A220004": ("Final budget period", "continued", "final budget period"),
        # Unfunded outranks the stage; the 2026-09-01 period isn't readable yet.
        "P066A230005": ("Unfunded (not yet readable; readable from 2026-11-30)", "not yet readable", "continuing"),
        "P044A210683": ("Reversed", "reversed", "ended"),
        "P042A200010": ("Ended", "continued", "ended"),
        "P217A220172": ("Final budget period (not yet readable; readable from 2026-12-30)", "not yet readable",
                        "final budget period"),
    }
    header = list(read_sheet(path, MAIN)[0])
    assert header[:4] == ["Priority tier", "Label", "Lifecycle stage", "Funding status"]


def test_priority_tier_buckets_new_continuing_and_unfunded_or_reversed_with_reason(project):
    write_actions(project.raw_usaspending, PULL, FIXTURE)

    project.topo("run", "--as-of", PULL)

    path = project.output / WORKBOOK
    rows = by_fain(read_sheet(path, MAIN) + read_sheet(path, "Ended"))
    tiers = {fain: (r["Priority tier"], r["Tier reason"]) for fain, r in rows.items()}
    assert tiers == {
        "P042A260001": ("1", "awarded 2026-08-15"),  # new, within 3 months of the award
        "P042A260002": ("3", ""),                    # new, but awarded 2026-05-15: past the 3-month window
        "P047A230003": ("3", ""),
        "P047A220004": ("3", ""),
        "P217A220172": ("3", ""),
        "P066A230005": ("4", "unfunded: Budget period 2025-09-01 to 2026-08-31"),
        "P044A210683": ("4", "reversed: Budget period 2025-09-01 to 2026-08-31"),
        "P042A200010": ("", ""),                     # ended: not a call list
    }


IHE = "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"
NONPROFIT = "NONPROFIT WITH 501C3 IRS STATUS (OTHER THAN AN INSTITUTION OF HIGHER EDUCATION)"
ROCKY = dict(recipient="ROCKY MOUNTAIN COLLEGE", uei="RMCUEI000001", state="MT", business_types_description=IHE)
UMN = dict(recipient="REGENTS OF THE UNIVERSITY OF MINNESOTA", uei="UMNUEI000001", state="MN",
           business_types_description=IHE)
MHEAC = dict(recipient="MASSACHUSETTS HIGHER EDUCATION ASSISTANCE CORPORATION", uei="MHEAC0000001", state="MA",
             business_types_description=NONPROFIT)


def write_ipeds(project):
    folder = project.root / "data" / "raw" / "ipeds" / PULL
    write_csv(folder / "colleges_ipeds_directory.csv", DIRECTORY_COLUMNS, [
        directory_row("180595", "Rocky Mountain College", "MT", ueis=("RMCUEI000001",)),
        directory_row("174066", "University of Minnesota-Twin Cities", "MN", ueis=("UMNUEI000001",)),
        directory_row("174233", "University of Minnesota-Duluth", "MN", ueis=("UMNUEI000001",)),
    ])
    write_csv(folder / "colleges_ipeds_fall-enrollment-race_2024.csv", ENROLLMENT_COLUMNS,
              [enrollment_row("180595", 2024, 900)])


def test_main_sheet_sorts_by_tier_with_lower_host_confidence_below_matched_rows(project):
    write_actions(project.raw_usaspending, PULL, [
        *grant("P042A230011", 2023, 4, **ROCKY),         # tier 3, matched, awarded 2023
        *grant("P042A210012", 2021, 6, **UMN),           # tier 3, in review, awarded earlier
        *grant("P044A210013", 2021, 6, **MHEAC),         # tier 3, no single Host
        *grant("P047A200014", 2020, 7, state="TX", uei="TXUEI0000001", recipient="TEXAS COLLEGE",
               business_types_description=IHE),       # tier 3, unmatched
        *grant("P042A260015", 2026, 1, award_month=8, state="TX", uei="TXUEI0000001",
               recipient="TEXAS COLLEGE", business_types_description=IHE),  # tier 1, unmatched
        *grant("P042A230016", 2023, 2, **ROCKY),         # tier 4: unfunded since 2025-09-01
        *grant("P042A200017", 2020, 6, **ROCKY),         # ended
    ])
    write_ipeds(project)

    project.topo("run", "--as-of", PULL)

    path = project.output / WORKBOOK
    main = [(r["FAIN"], r["Priority tier"], r["Host confidence"]) for r in read_sheet(path, MAIN)]
    assert main == [
        ("P042A260015", "1", "unmatched"),
        ("P042A230011", "3", "matched"),
        ("P044A210013", "3", "lower-confidence: no single Host"),
        ("P042A210012", "3", "in review"),
        ("P047A200014", "3", "unmatched"),
        ("P042A230016", "4", "matched"),
    ]
    assert [r["FAIN"] for r in read_sheet(path, "Ended")] == ["P042A200017"]
    assert read_sheet(path, "Missing") == [] and list(load_header(path, "Missing")) == [
        "State", "Recipient", "Program", "Note"]


def test_the_csv_holds_the_main_sheet_rows(project):
    write_actions(project.raw_usaspending, PULL, FIXTURE)

    project.topo("run", "--as-of", PULL)

    main = read_sheet(project.output / WORKBOOK, MAIN)
    csv_rows = project.read_csv(f"target_list_{PULL}.csv")
    assert list(csv_rows[0]) == list(main[0])
    assert [r["FAIN"] for r in csv_rows] == [r["FAIN"] for r in main]
    assert "P042A200010" not in {r["FAIN"] for r in csv_rows}  # ended: Ended sheet only
    text_columns = [c for c in main[0] if not c.startswith("FY") and "obligation" not in c]
    assert [{c: r[c] for c in text_columns} for r in csv_rows] == [{c: r[c] for c in text_columns} for r in main]
    assert [float(r["Cumulative obligation"]) for r in csv_rows] == [float(r["Cumulative obligation"]) for r in main]


def test_a_fiscal_year_under_90_days_past_its_end_on_the_pull_date_is_provisional(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A230003", 2023, 4))
    write_actions(project.raw_usaspending, "2026-12-29", grant("P047A230003", 2023, 4))

    project.topo("run", "--as-of", PULL)  # Pull date 2026-12-29: FY2026 ended 90 days earlier

    settled = read_sheet(project.output / "target_list_2026-12-29.xlsx", MAIN)[0]
    assert settled["Latest FY"] == "FY2026" and settled["Data note"] == ""

    (project.raw_usaspending / "2026-12-29").rename(project.raw_usaspending / "2026-12-28")
    project.topo("run", "--as-of", PULL)  # Pull date 2026-12-28: 89 days

    path = project.output / "target_list_2026-12-28.xlsx"
    provisional = read_sheet(path, MAIN)[0]
    assert provisional["Data note"] == "FY2026 provisional (as of 2026-12-28; reporting lag)"
    assert "FY2026 provisional (as of 2026-12-28; reporting lag)" in sheet_text(path, "README")


def test_talent_search_and_eoc_rows_say_fy2026_new_awards_are_not_yet_reported_until_a26_fains_appear(project):
    old_cohort = [*grant("P044A210001", 2021, 6), *grant("P066A210002", 2021, 6), *grant("P042A210003", 2021, 6)]
    write_actions(project.raw_usaspending, PULL, old_cohort)
    project.topo("run", "--as-of", "2026-01-15")

    notes = {r["FAIN"]: r["Data note"] for r in read_sheet(project.output / WORKBOOK, MAIN)}
    assert notes == {
        "P044A210001": "FY2026 new awards not yet reported",
        "P066A210002": "FY2026 new awards not yet reported",
        "P042A210003": "",
    }

    write_actions(project.raw_usaspending, "2026-10-08", [*old_cohort, *grant("P044A260004", 2026, 1, award_month=9)])
    project.topo("run", "--as-of", "2026-10-08")

    path = project.output / "target_list_2026-10-08.xlsx"
    rows = by_fain(read_sheet(path, MAIN) + read_sheet(path, "Ended"))
    assert "not yet reported" not in rows["P044A260004"]["Data note"]
    assert "not yet reported" not in rows["P044A210001"]["Data note"]
    assert "FY2026 new awards not yet reported" in rows["P066A210002"]["Data note"]


def test_readme_carries_dates_glossary_census_notice_and_attributions(project):
    write_actions(project.raw_usaspending, PULL, FIXTURE)

    project.topo("run", "--as-of", "2026-10-01")

    text = sheet_text(project.output / WORKBOOK, "README")
    assert f"Pull date | {PULL}" in text
    assert "As-of date | 2026-10-01" in text
    for term in ("Grant", "Recipient", "Host institution", "Host confidence", "Funding status", "Lifecycle stage",
                 "2025–26 disruption", "Priority tier", "Label"):
        assert f"\n{term} | " in text, term
    assert "This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau." in text
    assert "USAspending.gov, U.S. Department of Treasury, Bureau of the Fiscal Service" in text
    assert "D&B" in text
    assert "Education Data Portal" in text and "ODC" in text


CAUSE_NOTES_HEADER = "fain,cause_note,source,docket_entry,page,source_url\n"


def write_cause_notes(project, body: str):
    path = project.root / "data" / "curated" / "cause_notes.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CAUSE_NOTES_HEADER + body)


def test_cause_notes_appear_with_their_citation_only_on_the_fain_a_source_names(project):
    write_cause_notes(project, (
        "P044A210683,Named in a list of terminated TRIO grants,Example v. Department of Education (D. Mass.),"
        "41-2,,\n"
        "P066A230005,Named as non-continued,Example agency letter,,7,https://example.org/letter.pdf\n"
        "P099A990001,A FAIN not on the list,Example source,3,,\n"
    ))
    write_actions(project.raw_usaspending, PULL, FIXTURE)

    project.topo("run", "--as-of", PULL)

    path = project.output / WORKBOOK
    notes = {fain: r["Cause note"] for fain, r in by_fain(read_sheet(path, MAIN) + read_sheet(path, "Ended")).items()}
    assert notes["P044A210683"] == (
        "Named in a list of terminated TRIO grants [Example v. Department of Education (D. Mass.), docket entry 41-2]"
    )
    assert notes["P066A230005"] == "Named as non-continued [Example agency letter, p. 7, https://example.org/letter.pdf]"
    assert {fain for fain, note in notes.items() if note} == {"P044A210683", "P066A230005"}


def test_a_cause_note_without_a_source_or_without_a_docket_entry_or_page_stops_the_run(project):
    write_actions(project.raw_usaspending, PULL, FIXTURE)

    write_cause_notes(project, "P044A210683,Named in a filing,Example v. Department of Education,,,\n")
    result = project.topo("run", "--as-of", PULL, expect_exit=2)
    assert "cause notes" in result.output and "docket entry or a page" in result.output

    write_cause_notes(project, "P044A210683,Named in a filing,,41,,\n")
    result = project.topo("run", "--as-of", PULL, expect_exit=2)
    assert "cause notes" in result.output and "source" in result.output
    assert not list(project.output.glob("target_list_*"))


def test_the_committed_cause_notes_file_passes_its_schema(project):
    from topo.domain.cause_notes import read_cause_notes

    from conftest import REPO_ROOT

    path = REPO_ROOT / "data" / "curated" / "cause_notes.csv"
    assert path.exists()
    committed = read_cause_notes(path)
    assert committed.columns == ["fain", "cause_note", "source", "docket_entry", "page", "source_url"]


def test_the_tier_1_window_comes_from_config(project):
    project.set_config("new_award_months = 3", "new_award_months = 6")
    write_actions(project.raw_usaspending, PULL, FIXTURE)

    project.topo("run", "--as-of", PULL)

    rows = by_fain(read_sheet(project.output / WORKBOOK, MAIN))
    assert rows["P042A260002"]["Priority tier"] == "1"
