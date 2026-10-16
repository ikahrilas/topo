"""Seam 1: the reconciliation table (#42) via `topo run`, compared with outside totals and never adjusted."""

from __future__ import annotations

from conftest import REPO_ROOT
from support.curated import ALLOCATION_COLUMNS, APPROPRIATION_COLUMNS, research_figures, write_curated
from support.usaspending import action, write_actions

PULL = "2026-10-07"
RECONCILIATION = f"reconciliation_{PULL}.csv"


def grant(fain: str, start_fy: int, years: int, amount: float = 100000) -> list[dict]:
    return [
        action(fain, i + 1, f"{start_fy + i}-05-15", amount, (f"{start_fy + i}-09-01", f"{start_fy + i + 1}-08-31"),
               action_type="A1" if i == 0 else "B1")
        for i in range(years)
    ]


def rows(project, check: str) -> dict[tuple[str, str], dict[str, str]]:
    return {(r["Program"], r["FY"]): r for r in project.read_csv(RECONCILIATION) if r["Check"] == check}


def test_the_fy2022_allocation_overage_is_exceeds_appropriation_unexplained_and_shortfalls_are_unallocated(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A220845", 2022, 4))
    write_curated(project.root, *research_figures())

    result = project.topo("run", "--as-of", PULL)

    by_fy = rows(project, "appropriation_vs_allocations")
    assert sorted(by_fy) == [("Federal TRIO Programs", f"FY{fy}") for fy in range(2021, 2027)]
    fy2022 = by_fy[("Federal TRIO Programs", "FY2022")]
    assert (fy2022["Reference value"], fy2022["Compared value"], fy2022["Gap"]) == (
        "1137000000.00", "1138358159.00", "1358159.00")
    assert (fy2022["Reconciliation status"], fy2022["Gap reason code"]) == (
        "stated difference", "exceeds_appropriation_unexplained")
    assert fy2022["Unallocated remainder"] == ""
    fy2021 = by_fy[("Federal TRIO Programs", "FY2021")]
    assert (fy2021["Reconciliation status"], fy2021["Gap reason code"], fy2021["Unallocated remainder"]) == (
        "reconciled", "", "18076868.00")
    for fy in ("FY2025", "FY2026"):  # ED publishes no per-program dollars after FY2024
        row = by_fy[("Federal TRIO Programs", fy)]
        assert (row["Reconciliation status"], row["Gap reason code"]) == ("not comparable", "not_published")
        assert row["Note"]
    assert "Warning:" in result.output and "exceeds_appropriation_unexplained" in result.output


def test_empty_or_absent_curated_files_run_and_every_outside_figure_reads_not_published(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A220845", 2022, 4))
    project.topo("run", "--as-of", PULL)  # no data/curated at all
    write_curated(project.root, [], [])  # header-only, as committed

    project.topo("run", "--as-of", PULL)

    table = project.read_csv(f"reconciliation_{PULL}_v2.csv")
    outside = [r for r in table if r["Check"] in {"appropriation_vs_allocations", "ed_allocation_dollars",
                                                  "ed_allocation_count"}]
    assert {r["Check"] for r in outside} == {"appropriation_vs_allocations", "ed_allocation_dollars",
                                             "ed_allocation_count"}
    assert {(r["Reconciliation status"], r["Gap reason code"]) for r in outside} == {("not comparable", "not_published")}
    assert all(r["Note"] for r in table)


def test_the_committed_curated_files_have_their_schema_headers():
    curated = REPO_ROOT / "data" / "curated"
    assert (curated / "appropriations.csv").read_text().splitlines() == [",".join(APPROPRIATION_COLUMNS)]
    assert (curated / "ed_program_allocations.csv").read_text().splitlines() == [",".join(ALLOCATION_COLUMNS)]
