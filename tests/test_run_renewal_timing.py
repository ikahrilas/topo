"""Seam 1: renewal timing and Re-competing soon, via `topo run`.

The Predicted due date is set per Program Cohort: the prior Cohort's published
deadline (from the cited, hand-curated deadline table) plus 60 months. Fixtures
put an Upward Bound Cohort in FY2017 and the next in FY2022, so the observed
gap is 60 months and the FY2022 Cohort's next competition is FY2027.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest
from support.usaspending import action, write_actions

PULL = "2026-10-07"
DEADLINES_HEADER = "program,competition_fy,application_deadline,citation,source_url,note\n"
UB_FY2022 = ("Upward Bound,2022,2022-01-31,"
             "Applications for New Awards; Upward Bound Program (86 FR 71477; Dec. 16 2021),"
             "https://www.federalregister.gov/documents/2021/12/16/2021-27235,\n")


def grant(fain, a1_year, funded_years, *, late_last=False, **who):
    """A1 in May of a1_year; Sept-Aug Budget periods, each funded in May before it starts.

    With `late_last`, the last funded period is funded in October, after its anniversary + 1 month.
    """
    rows = []
    for i in range(funded_years):
        year = a1_year + i
        date = f"{year}-05-15"
        if late_last and i == funded_years - 1:
            date = f"{year}-10-05"
        rows.append(action(fain, i + 1, date, 300000, (f"{year}-09-01", f"{year + 1}-08-31"),
                           action_type="A1" if i == 0 else "B1", **who))
    return rows


UB_COHORTS = [*grant("P047A170001", 2017, 5), *grant("P047A170002", 2017, 5)]  # the prior Cohort (FY2017)


def write_deadlines(project, *rows):
    curated = project.root / "data" / "curated"
    curated.mkdir(parents=True, exist_ok=True)
    (curated / "deadlines.csv").write_text(DEADLINES_HEADER + "".join(rows))


def rows_by_fain(project):
    return {r["FAIN"]: r for r in project.read_csv(f"target_list_{PULL}.csv")}


def test_with_an_empty_deadline_table_every_program_shows_date_unknown(project):
    write_deadlines(project)
    write_actions(project.raw_usaspending, PULL, [
        *UB_COHORTS, *grant("P047A220001", 2022, 5), *grant("P047A220002", 2022, 5),
    ])

    project.topo("run", "--as-of", PULL)

    ub = rows_by_fain(project)["P047A220001"]
    assert ub["Renewal timing"] == "date unknown"
    assert ub["Predicted competition FY"] == "FY2027"
    assert ub["Predicted due date"] == ""
    assert ub["Evidence tier"] == ""
    assert ub["Re-competing soon"] == "no"


def test_a_deadline_row_without_a_citation_stops_the_run(project):
    write_deadlines(project, "Upward Bound,2022,2022-01-31,,,\n")
    write_actions(project.raw_usaspending, PULL, [*UB_COHORTS, *grant("P047A220001", 2022, 5)])

    result = project.topo("run", "--as-of", PULL, expect_exit=2)

    assert "deadline table" in result.output
    assert not list(project.output.glob("target_list_*"))


@pytest.mark.parametrize(
    "funded_years, late_last, latest_readable, flagged",
    [
        pytest.param(5, False, "continued", "yes", id="continued"),
        pytest.param(5, True, "funded late", "yes", id="funded late"),
        pytest.param(3, False, "unfunded", "no", id="unfunded Grants are never flagged"),
    ],
)
def test_re_competing_soon_is_gated_by_funding_status(project, funded_years, late_last, latest_readable, flagged):
    write_deadlines(project, UB_FY2022)
    write_actions(project.raw_usaspending, PULL, [
        *UB_COHORTS, *grant("P047A220001", 2022, funded_years, late_last=late_last), *grant("P047A220002", 2022, 5),
    ])

    project.topo("run", "--as-of", PULL)

    ub = rows_by_fain(project)["P047A220001"]
    assert ub["Latest readable status"] == latest_readable
    assert ub["Re-competing soon"] == flagged
    assert ub["Predicted due date"] == "2027-01-31"  # FY2022 deadline 2022-01-31 + 60 months
    assert ub["Evidence tier"] == "inferred"
    assert ub["Renewal timing"] == "predicted"


def test_a_due_date_more_than_12_months_away_is_not_re_competing_soon(project):
    write_deadlines(project, UB_FY2022)
    write_actions(project.raw_usaspending, PULL, [*UB_COHORTS, *grant("P047A220001", 2022, 5)])

    project.topo("run", "--as-of", "2026-01-15")  # 2027-01-31 is 12.5 months away

    ub = rows_by_fain(project)["P047A220001"]
    assert ub["Latest readable status"] == "continued"
    assert ub["Re-competing soon"] == "no"


def test_a_published_notice_for_the_next_competition_outranks_the_inferred_date(project):
    write_deadlines(project, UB_FY2022, "Upward Bound,2027,2026-12-01,Notice inviting applications (FY2027),,\n")
    write_actions(project.raw_usaspending, PULL, [*UB_COHORTS, *grant("P047A220001", 2022, 5)])

    project.topo("run", "--as-of", PULL)

    ub = rows_by_fain(project)["P047A220001"]
    assert (ub["Predicted due date"], ub["Evidence tier"]) == ("2026-12-01", "notice published")
    assert ub["Predicted competition FY"] == "FY2027"
    assert ub["Re-competing soon"] == "yes"


NEW_COHORT = [*grant("P047A270001", 2027, 1), *grant("P047A270002", 2027, 1)]  # A1s dated 2027-05-15


@pytest.mark.parametrize(
    "as_of, flagged",
    [
        pytest.param("2027-03-01", "yes", id="past the due date, before the new Cohort's FAINs: still on"),
        pytest.param("2027-06-01", "no", id="the new Cohort's FAINs have appeared"),
    ],
)
def test_re_competing_soon_holds_until_a_new_cohorts_fains_appear(project, as_of, flagged):
    write_deadlines(project, UB_FY2022)
    write_actions(project.raw_usaspending, PULL, [
        *UB_COHORTS, *grant("P047A220001", 2022, 5), *grant("P047A220002", 2022, 5), *NEW_COHORT,
    ])

    project.topo("run", "--as-of", as_of)

    ub = rows_by_fain(project)["P047A220001"]
    assert ub["Latest readable status"] == "continued"
    assert ub["Re-competing soon"] == flagged


def test_a_program_whose_observed_gap_is_not_60_months_shows_timing_not_predicted(project):
    write_deadlines(project, "McNair,2021,2021-03-01,Notice inviting applications (FY2021),,\n")
    write_actions(project.raw_usaspending, PULL, [
        *grant("P217A170001", 2017, 5), *grant("P217A210001", 2021, 5),  # Cohorts FY2017 and FY2021: 48 months
    ])

    project.topo("run", "--as-of", PULL)

    mcnair = rows_by_fain(project)["P217A210001"]
    assert mcnair["Renewal timing"] == "timing not predicted"
    assert (mcnair["Predicted due date"], mcnair["Evidence tier"], mcnair["Re-competing soon"]) == ("", "", "no")
    gaps = pl.read_parquet(project.root / "data/joined/cohort_timing.parquet")
    assert gaps.select("program", "cohort_fy", "observed_gap_months").rows() == [
        ("McNair", 2017, None), ("McNair", 2021, 48),
    ]


def test_grants_whose_budget_period_end_disagrees_with_their_cohort_are_listed_as_exceptions(project):
    write_actions(project.raw_usaspending, PULL, [
        *UB_COHORTS,
        *grant("P047A220001", 2022, 5), *grant("P047A220002", 2022, 5),  # Cohort: 2022-09-01 .. 2027-08-31
        *grant("P047A220003", 2022, 5),
        action("P047A220003", 9, "2026-05-20", 1000, ("2027-09-01", "2028-08-31")),  # extended a year
        action("P047A230004", 1, "2023-01-10", 300000, ("2023-01-01", "2023-12-31"), action_type="A1"),  # off-cycle
    ])

    project.topo("run", "--as-of", PULL)

    exceptions = pl.read_parquet(project.root / "data/joined/renewal_timing_exceptions.parquet")
    assert exceptions.select("fain", "budget_period_end", "reason").rows() == [
        ("P047A220003", dt.date(2028, 8, 31), "budget_period_ends_after_cohort"),
        ("P047A230004", dt.date(2023, 12, 31), "budget_period_end_off_cohort_cycle"),
    ]
    assert exceptions["cohort_end"].unique().to_list() == [dt.date(2027, 8, 31)]


def test_gear_up_rows_say_competes_most_years_and_carry_an_end_date_fact(project):
    write_deadlines(project, UB_FY2022)
    write_actions(project.raw_usaspending, PULL, [
        *grant("P334A210001", 2021, 6),  # from 2021-09-01, six Budget periods: ends 2027-08-31
        *grant("P334S190002", 2019, 6),  # ended 2025-08-31
    ])

    project.topo("run", "--as-of", PULL)

    rows = rows_by_fain(project)
    partnership = rows["P334A210001"]
    assert partnership["Renewal timing"] == "competes most years; timing not predicted"
    assert partnership["End date"] == "expires within 12 months (end date 2027-08-31)"
    assert (partnership["Predicted due date"], partnership["Re-competing soon"]) == ("", "no")
    assert rows["P334S190002"]["End date"] == ""
