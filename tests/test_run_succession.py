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


def mcnair_a1(fain, year):
    return action(fain, 1, f"{year}-07-01", 250000, (f"{year}-10-01", f"{year + 1}-09-30"), action_type="A1", **ROCKY)


def test_cohort_starts_are_derived_per_program_and_off_cycle_awards_join_the_cohort_before_them(project):
    write_actions(project.raw_usaspending, PULL, [
        *[a for n in (1, 2, 3) for a in five_years(f"P042A15000{n}", "2015-07-01", 2015, **ROCKY)],
        *five_years("P042A160004", "2016-07-01", 2016, **ROCKY),  # off-cycle: from the unfunded list
        *[a for n in (5, 6, 7) for a in five_years(f"P042A20000{n}", "2020-07-01", 2020, **ROCKY)],
        mcnair_a1("P217A170001", 2017), mcnair_a1("P217A170002", 2017),
        mcnair_a1("P217A220003", 2022), mcnair_a1("P217A220004", 2022),
    ])

    project.topo("run", "--as-of", PULL)

    assert joined(project, "cohort_starts").rows() == [
        ("McNair", 2017, d("2017-10-01"), 2),
        ("McNair", 2022, d("2022-10-01"), 2),
        ("Student Support Services", 2015, d("2015-09-01"), 3),
        ("Student Support Services", 2020, d("2020-09-01"), 3),
    ]
    cohorts = dict(joined(project, "grant_cohorts").select("fain", "cohort_fy").rows())
    assert cohorts["P042A160004"] == 2015
    assert cohorts["P042A200005"] == 2020
    assert cohorts["P217A170001"] == 2017


def who(recipient, uei, state):
    return dict(recipient=recipient, uei=uei, state=state)


def funded_then_handed_off(old, new, period, start_year, a1_date, amount, hand_off_date, old_who, new_who):
    """The old FAIN is funded on time each year; on the hand-off date its last Continuation (or A1) is
    negated in full and the new FAIN's A1 for the same amount is made the same day."""
    years = list(range(start_year, 2026))
    last = years[-1]
    start_md, end_md = period
    actions = [
        action(old, i + 1, a1_date if i == 0 else f"{y}-06-01", amount,
               (f"{y}-{start_md}", f"{y + 1}-{end_md}"), action_type="A1" if i == 0 else "B1",
               **old_who)
        for i, y in enumerate(years)
    ]
    actions.append(action(old, 99, hand_off_date, -amount, (f"{last}-{start_md}", f"{last + 1}-{end_md}"),
                          action_type="EX", **old_who))
    actions.append(action(new, 1, hand_off_date, amount, (hand_off_date, f"{int(hand_off_date[:4]) + 1}-06-30"),
                          action_type="A1", **new_who))
    return actions


SEPT, OCT = ("09-01", "08-31"), ("10-01", "09-30")  # Budget period start and end (month-day)
SIENA = who("SIENA HEIGHTS UNIVERSITY", "SIENAUEI0001", "MI")
KNOWN_HAND_OFFS = [  # docs/research/status-signals-2025-26.md, "Succession false positives"
    funded_then_handed_off("P047A221031", "P047A250002", SEPT, 2022, "2022-07-01", 513114, "2025-12-22",
                           who("IMPACT EDUCATIONAL AND HOUSING DEVELOPMENT", "IMPACTUEI001", "GA"),
                           who("IMPACT PROSPERITY PARTNERS", "IMPACTUEI002", "GA")),
    funded_then_handed_off("P217A220158", "P217A250002", OCT, 2022, "2022-07-01", 92117.37, "2026-06-15",
                           SIENA, who("ADRIAN COLLEGE", "ADRIANUEI001", "MI")),
    funded_then_handed_off("P042A250822", "P042A251923", SEPT, 2025, "2025-07-01", 202423.49, "2026-07-06",
                           SIENA, who("DEFIANCE COLLEGE", "DEFIANCEUEI1", "OH")),
    funded_then_handed_off("P042A250292", "P042A251922", SEPT, 2025, "2025-07-01", 272364, "2026-06-24",
                           who("PURDUE UNIVERSITY GLOBAL", "PURDUEGLOBL1", "IN"),
                           who("PURDUE UNIVERSITY", "PURDUEUEI001", "IN")),
]

IVY = who("IVY TECH COMMUNITY COLLEGE", "IVYTECHUEI01", "IN")
REVERSED_DESPITE_A1_ON_ANOTHER_PROGRAM = [
    action("P044A210683", 1, "2021-06-01", 336357, ("2021-09-01", "2022-08-31"), action_type="A1", **IVY),
    *[action("P044A210683", y - 2020, f"{y}-06-01", 336357, (f"{y}-09-01", f"{y + 1}-08-31"), **IVY)
      for y in range(2022, 2026)],
    action("P044A210683", 9, "2025-09-29", -336357, ("2025-09-01", "2026-08-31"), action_type="EX", **IVY),
    # Same day, same amount, but SSS, not Talent Search: not a hand-off.
    action("P042A259999", 1, "2025-09-29", 336357, ("2025-10-01", "2026-09-30"), action_type="A1",
           **who("ANOTHER COLLEGE", "ANOTHERUEI01", "IN")),
]

HANDED_OFF = ["P042A250292", "P042A250822", "P047A221031", "P217A220158"]


def test_the_four_known_succession_hand_offs_are_not_read_as_reversed(project):
    write_actions(project.raw_usaspending, PULL,
                  [a for grant in KNOWN_HAND_OFFS for a in grant] + REVERSED_DESPITE_A1_ON_ANOTHER_PROGRAM)

    project.topo("run", "--as-of", PULL)

    status = {r["FAIN"]: r["Latest readable status"] for r in project.read_csv(f"target_list_{PULL}.csv")}
    assert {fain: status[fain] for fain in HANDED_OFF} == dict.fromkeys(HANDED_OFF, "continued")
    assert status["P044A210683"] == "reversed"
    periods = joined(project, "funding_status").filter(pl.col("fain").is_in(HANDED_OFF))
    assert "reversed" not in periods["funding_status"].to_list()
    assert sorted(joined(project, "hand_offs").select("fain", "successor_fain").rows()) == [
        ("P042A250292", "P042A251922"),
        ("P042A250822", "P042A251923"),
        ("P047A221031", "P047A250002"),
        ("P217A220158", "P217A250002"),
    ]
    assert successions(project) == []  # different Recipients: hand-offs, not Successions


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)
