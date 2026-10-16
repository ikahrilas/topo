"""Seam 1: renewal timing and Re-competing soon, via `topo run`.

The Predicted due date is set per Program Cohort: the prior Cohort's published
deadline (from the cited, hand-curated deadline table) plus 60 months. Fixtures
put an Upward Bound Cohort in FY2017 and the next in FY2022, so the observed
gap is 60 months and the FY2022 Cohort's next competition is FY2027.
"""

from __future__ import annotations

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
