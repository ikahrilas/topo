"""Seam 1: `topo run` end to end against a fixture raw tree (USAspending only)."""

from __future__ import annotations

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
