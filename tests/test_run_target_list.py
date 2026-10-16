"""Seam 1: `topo run` end to end against a fixture raw tree (USAspending only)."""

from __future__ import annotations

import polars as pl
from support.usaspending import action, write_actions

PULL = "2026-10-07"

USF_UB = [  # Upward Bound, awarded FY2022; the 2025-09-17 action (FY2025) funds 2025-09-01 → 2026-08-31
    action("P047A220845", 1, "2022-05-23", 824294, ("2022-06-01", "2023-08-31"), action_type="A1"),
    action("P047A220845", 2, "2023-05-13", 857266, ("2023-09-01", "2024-08-31")),
    action("P047A220845", 3, "2024-05-15", 857266, ("2024-09-01", "2025-08-31")),
    action("P047A220845", 4, "2025-09-17", 857266, ("2025-09-01", "2026-08-31")),
    action("P047A220845", 5, "2026-07-28", 857266, ("2026-09-01", "2027-08-31")),
]


def test_run_writes_one_target_list_row_per_fain(project):
    write_actions(project.raw_usaspending, PULL, USF_UB + [
        action("P042A200010", 1, "2020-07-01", 272364, ("2020-09-01", "2021-08-31"), action_type="A1",
               recipient="COLLEGE A", uei="AAAAAAAAAAA1", state="TX"),
        action("P042A200010", 2, "2021-07-01", 272364, ("2021-09-01", "2022-08-31"),
               recipient="COLLEGE A", uei="AAAAAAAAAAA1", state="TX"),
    ])

    project.topo("run", "--as-of", "2026-10-07")

    rows = project.read_csv(f"target_list_{PULL}.csv")
    assert sorted(r["FAIN"] for r in rows) == ["P042A200010", "P047A220845"]
    usf = next(r for r in rows if r["FAIN"] == "P047A220845")
    assert usf["Recipient"] == "UNIVERSITY OF SOUTH FLORIDA"
    assert usf["Recipient UEI"] == "NKAZLXLL7Z91"
    assert usf["State"] == "FL"
    assert usf["Program"] == "Upward Bound"
    assert usf["Project start"] == "2022-06-01"
    assert usf["Project end"] == "2027-08-31"
    assert usf["Latest FY"] == "FY2026"
    assert float(usf["Latest FY obligation"]) == 857266
    assert float(usf["Cumulative obligation"]) == 4253358
    assert usf["Pull date"] == PULL
    assert usf["As-of date"] == "2026-10-07"


def grant(fain: str, start_fy: int, years: int, amount: float = 100000, **kw) -> list[dict]:
    """A Grant with one action per year: A1 in May of start_fy, B1s after; Sept-Aug Budget periods."""
    rows = []
    for i in range(years):
        year = start_fy + i
        rows.append(action(fain, i + 1, f"{year}-05-15", amount, (f"{year}-09-01", f"{year + 1}-08-31"),
                           action_type="A1" if i == 0 else "B1", **kw))
    return rows


def test_grants_are_selected_by_listing_and_fain_prefix_never_by_agency(project):
    write_actions(project.raw_usaspending, PULL, [
        *grant("P047A220001", 2022, 4),                    # Upward Bound
        *grant("P047M220002", 2022, 4),                    # UBMS (same listing 84.047)
        *grant("P047V220003", 2022, 4),                    # VUB (same listing 84.047)
        *grant("P334A230004", 2023, 3),                    # GEAR UP partnership
        *grant("P334S230005", 2023, 3),                    # GEAR UP state (same listing 84.334)
        *grant("P044A260006", 2026, 1, agency="1601"),     # ED Talent Search Grant administered by DOL
        *grant("P063P220007", 2022, 4, listing="84.063"),  # Pell: not TRIO/GEAR UP
        *grant("P103A220008", 2022, 4),                    # TRIO Training: not a service-line Program
        *grant("A08AV00094", 2022, 4, listing="84.042"),   # TRIO listing, FAIN prefix names no Program
    ])

    project.topo("run", "--as-of", PULL)

    programs = {r["FAIN"]: r["Program"] for r in project.read_csv(f"target_list_{PULL}.csv")}
    assert programs == {
        "P047A220001": "Upward Bound",
        "P047M220002": "Upward Bound Math and Science",
        "P047V220003": "Veterans Upward Bound",
        "P334A230004": "GEAR UP partnership",
        "P334S230005": "GEAR UP state",
        "P044A260006": "Talent Search",
    }
    exceptions = pl.read_parquet(project.root / "data/joined/grant_universe_exceptions.parquet")
    assert exceptions["fain"].unique().to_list() == ["A08AV00094"]
    assert exceptions["reason"].unique().to_list() == ["fain_prefix_names_no_program"]


def test_a_grant_overlapping_the_window_is_kept_even_if_awarded_before_it(project):
    write_actions(project.raw_usaspending, PULL, [
        *grant("P042A200010", 2020, 6),  # awarded FY2020, runs into the window
        *grant("P042A150011", 2015, 5),  # last Budget period ends 2020-08-31, before FY2021
    ])

    project.topo("run", "--as-of", PULL)

    rows = project.read_csv(f"target_list_{PULL}.csv")
    assert [r["FAIN"] for r in rows] == ["P042A200010"]
    assert rows[0]["Project start"] == "2020-09-01"
    # FY2020 is lookback: it gets no amount column and is not in the cumulative total.
    assert "FY2020" not in rows[0]
    assert float(rows[0]["Cumulative obligation"]) == 500000


def test_amount_columns_are_federal_fiscal_years_and_roll_forward_with_the_as_of_date(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A220001", 2022, 5))

    project.topo("run", "--as-of", "2025-12-01")
    project.topo("run", "--as-of", "2026-10-07")

    before = project.read_csv(f"target_list_{PULL}.csv")[0]
    after = project.read_csv(f"target_list_{PULL}_v2.csv")[0]
    fy_columns = lambda row: [c for c in row if c.startswith("FY")]
    assert fy_columns(before) == ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025"]
    assert fy_columns(after) == ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]
    assert after["FY2021"] == "0.0" and float(after["FY2026"]) == 100000
    assert after["Latest FY"] == "FY2026" and before["Latest FY"] == "FY2025"
    assert not any("–" in c or "-" in c for c in fy_columns(after))  # never academic-year labels


def test_reporting_window_start_comes_from_config(project):
    project.set_config("start_fy = 2021", "start_fy = 2023")
    write_actions(project.raw_usaspending, PULL, [
        *grant("P047A220001", 2022, 5),
        *grant("P047A170002", 2017, 5),  # ends 2022-08-31: in a 2021 window, not in a 2023 one
    ])

    project.topo("run", "--as-of", PULL)

    rows = project.read_csv(f"target_list_{PULL}.csv")
    assert [r["FAIN"] for r in rows] == ["P047A220001"]
    assert [c for c in rows[0] if c.startswith("FY")] == ["FY2023", "FY2024", "FY2025", "FY2026"]
    assert float(rows[0]["Cumulative obligation"]) == 400000


def test_each_funding_action_keeps_the_budget_period_it_funds(project):
    write_actions(project.raw_usaspending, PULL, USF_UB)

    project.topo("run", "--as-of", PULL)

    actions = pl.read_parquet(project.root / "data/joined/grant_actions.parquet")
    late = actions.filter(pl.col("action_date") == pl.date(2025, 9, 17)).row(0, named=True)
    assert late["action_fy"] == 2025
    assert (str(late["budget_period_start"]), str(late["budget_period_end"])) == ("2025-09-01", "2026-08-31")
    assert late["transaction_key"]  # carried source key
    assert actions.height == len(USF_UB)


def test_as_of_defaults_to_the_latest_usaspending_pull_date(project):
    write_actions(project.raw_usaspending, "2026-09-05", grant("P047A220001", 2022, 4))
    write_actions(project.raw_usaspending, "2025-11-03", grant("P047A220001", 2022, 4))

    project.topo("run")

    rows = project.read_csv("target_list_2026-09-05.csv")
    assert rows[0]["As-of date"] == "2026-09-05"
    assert rows[0]["Pull date"] == "2026-09-05"
    # As of 2026-09-05 the last ended fiscal year is FY2025.
    assert [c for c in rows[0] if c.startswith("FY")][-1] == "FY2025"


def test_a_delivered_file_is_never_overwritten(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A220001", 2022, 4))
    delivered = project.output / f"target_list_{PULL}.csv"
    delivered.parent.mkdir(parents=True)
    delivered.write_text("founder's marked copy\n")

    project.topo("run", "--as-of", PULL)
    project.topo("run", "--as-of", PULL)

    assert delivered.read_text() == "founder's marked copy\n"
    assert len(project.read_csv(f"target_list_{PULL}_v2.csv")) == 1
    assert len(project.read_csv(f"target_list_{PULL}_v3.csv")) == 1


def test_a_duplicate_fain_in_the_grant_table_stops_the_run(project):
    # The same FAIN reported as two awards (ED and DOL award keys) is a structural break.
    write_actions(project.raw_usaspending, PULL, [
        *grant("P044A220001", 2022, 2),
        *grant("P044A220001", 2024, 1, agency="1601"),
    ])

    result = project.topo("run", "--as-of", PULL, expect_exit=2)

    assert "duplicate fain in the Grant table: P044A220001" in result.output
    assert not list(project.output.glob("target_list_*"))


def test_no_duns_or_individual_person_field_is_ingested(project):
    write_actions(project.raw_usaspending, PULL, USF_UB)

    project.topo("run", "--as-of", PULL)

    frames = [pl.read_parquet(p) for p in (project.root / "data").rglob("*.parquet")]
    columns = {c.lower() for f in frames for c in f.columns}
    columns |= set(c.lower() for c in project.read_csv(f"target_list_{PULL}.csv")[0])
    assert frames and not any("duns" in c or "officer" in c for c in columns)
    values = {str(v) for f in frames for col in f.columns for v in f[col].to_list()}
    assert "069687242" not in values and "JANE DOE" not in values
