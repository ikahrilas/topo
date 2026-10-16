"""Seam 1: Succession links, Cohort starts and the lookback, via `topo run`.

Lookback actions (back to FY2010 for TRIO, FY2015 for GEAR UP) are read only to
link Successions and derive Cohort starts; they never add amount columns.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest
from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, write_csv
from support.usaspending import action, write_actions

PULL = "2026-10-07"
IHE = "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"

ROCKY = dict(recipient="ROCKY MOUNTAIN COLLEGE", uei="RMCUEI000001", state="MT", business_types_description=IHE)
CARROLL = dict(recipient="CARROLL COLLEGE", uei="CARROLLUEI01", state="MT", business_types_description=IHE)


def five_years(fain, a1_date, start_year, amount=300000, **who):
    """A Grant funded for five 12-month Budget periods from Sept 1 of start_year."""
    return [
        action(fain, i + 1, a1_date if i == 0 else f"{start_year + i}-06-01", amount,
               (f"{start_year + i}-09-01", f"{start_year + i + 1}-08-31"),
               action_type="A1" if i == 0 else "B1", **who)
        for i in range(5)
    ]


def write_ipeds(project, *rows):
    folder = project.root / "data" / "raw" / "ipeds" / PULL
    write_csv(folder / "colleges_ipeds_directory.csv", DIRECTORY_COLUMNS, list(rows))
    write_csv(folder / "colleges_ipeds_fall-enrollment-race_2024.csv", ENROLLMENT_COLUMNS, [])


def joined(project, name):
    return pl.read_parquet(project.root / "data" / "joined" / f"{name}.parquet")


def successions(project):
    return sorted(joined(project, "successions").select("fain", "successor_fain").rows())


def test_a_lookback_grant_links_to_the_grant_that_renewed_it_but_adds_no_amounts(project):
    write_actions(project.raw_usaspending, PULL, [
        *five_years("P042A150001", "2015-07-01", 2015, **ROCKY),  # lookback only: ends 2020-08-31
        *five_years("P042A200001", "2020-07-01", 2020, **ROCKY),
    ])
    write_ipeds(project, directory_row("180595", "Rocky Mountain College", "MT", ueis=("RMCUEI000001",)))

    project.topo("run", "--as-of", PULL)

    assert successions(project) == [("P042A150001", "P042A200001")]
    rows = project.read_csv(f"target_list_{PULL}.csv")
    assert [r["FAIN"] for r in rows] == ["P042A200001"]
    fy_columns = [c for c in rows[0] if c.startswith("FY20")]
    assert fy_columns == ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]
    assert float(rows[0]["Cumulative obligation"]) == 4 * 300000  # FY2020's A1 is lookback


FOUNDATION = dict(recipient="ROCKY MOUNTAIN COLLEGE FOUNDATION", uei="RMCFOUND0001", state="MT",
                  business_types_description=IHE)


@pytest.mark.parametrize(
    "earlier, later",
    [
        pytest.param(("P042A150001", ROCKY), ("P042A200002", FOUNDATION), id="same Host, another Recipient"),
        pytest.param(("P042A150001", ROCKY), ("P047A200002", ROCKY), id="same Recipient and Host, another Program"),
        pytest.param(("P042A150001", CARROLL), ("P042A200002", CARROLL), id="no Host institution to compare"),
    ],
)
def test_succession_needs_the_same_recipient_program_and_host_institution(project, earlier, later):
    write_actions(project.raw_usaspending, PULL, [
        *five_years(earlier[0], "2015-07-01", 2015, **earlier[1]),
        *five_years(later[0], "2020-07-01", 2020, **later[1]),
    ])
    write_ipeds(project, directory_row("180595", "Rocky Mountain College", "MT",
                                       ueis=("RMCUEI000001", "RMCFOUND0001")))

    project.topo("run", "--as-of", PULL)

    assert successions(project) == []


def test_lookback_reaches_back_to_fy2010_for_trio_and_fy2015_for_gear_up(project):
    gear_up = dict(ROCKY, business_types_description="STATE GOVERNMENT")
    write_actions(project.raw_usaspending, PULL, [
        *five_years("P042A050001", "2005-07-01", 2005, **ROCKY),  # ended 2010-08-31: FY2010
        *five_years("P042A040002", "2004-07-01", 2004, **ROCKY),  # ended 2009-08-31: before the lookback
        *five_years("P334A100003", "2010-07-01", 2010, **gear_up),  # ended 2015-08-31: FY2015
        *five_years("P334A090004", "2009-07-01", 2009, **gear_up),  # ended 2014-08-31: before the lookback
        *five_years("P042A200005", "2020-07-01", 2020, **ROCKY),
    ])

    project.topo("run", "--as-of", PULL)

    assert sorted(joined(project, "lookback_grants")["fain"]) == ["P042A050001", "P334A100003"]
    assert [r["FAIN"] for r in project.read_csv(f"target_list_{PULL}.csv")] == ["P042A200005"]


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)
