"""Seam 1: the reconciliation table (#42) via `topo run`, compared with outside totals and never adjusted."""

from __future__ import annotations

import polars as pl
from conftest import REPO_ROOT
from support.curated import (
    ALLOCATION_COLUMNS,
    APPROPRIATION_COLUMNS,
    allocation,
    research_figures,
    write_curated,
)
from support.ed_lists import (
    file_list,
    gearup_html_bytes,
    known_gap,
    pdf_bytes,
    trio_pdf_lines,
    write_manifest,
)
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


MCNAIR_EARLY = [  # FY2023 Budget period funded by an action dated in FY2024: a timing difference
    action("P217A220001", 1, "2022-07-01", 2_000_000, ("2022-09-01", "2023-08-31"), action_type="A1"),
    action("P217A220001", 2, "2023-10-05", 3_000_000, ("2023-09-01", "2024-08-31")),
]


def allocations_case(project):
    write_actions(project.raw_usaspending, PULL, MCNAIR_EARLY + grant("P044A210001", 2021, 6, amount=250_000))
    write_curated(project.root, [], [
        allocation("McNair", 2022, 2_400_000),  # within $1M of 2,000,000
        allocation("McNair", 2023, 3_000_000),  # action-date FY2023 has 0; Budget-period FY2023 has 3,000,000
        allocation("Talent Search", 2024, 5_000_000),  # 250,000 in USAspending
        allocation("Talent Search", 2025, None, count=1),  # FY2025: counts only
        allocation("Talent Search", 2026, None, count=2),  # FY2026 ended 7 days before the Pull date
    ])


def test_ed_allocations_reconcile_within_1_percent_or_1m_and_years_passing_only_by_budget_period_are_timing(project):
    allocations_case(project)

    project.topo("run", "--as-of", PULL)

    dollars, counts = rows(project, "ed_allocation_dollars"), rows(project, "ed_allocation_count")
    shown = {key: (r["Reconciliation status"], r["Gap reason code"]) for key, r in dollars.items()}
    assert shown[("McNair", "FY2022")] == ("reconciled", "")
    assert shown[("McNair", "FY2023")] == ("stated difference", "timing_difference")
    assert (dollars[("McNair", "FY2023")]["Compared value"], dollars[("McNair", "FY2023")]["Budget-period value"]) == (
        "0.00", "3000000.00")
    assert shown[("Talent Search", "FY2024")] == ("stated difference", "unexplained")
    assert shown[("Talent Search", "FY2025")] == ("not comparable", "not_published")
    assert shown[("McNair", "FY2021")] == ("not comparable", "not_published")  # nothing filed
    assert (counts[("Talent Search", "FY2025")]["Reconciliation status"],
            counts[("Talent Search", "FY2025")]["Compared value"]) == ("reconciled", "1.00")
    assert (counts[("Talent Search", "FY2026")]["Reconciliation status"],
            counts[("Talent Search", "FY2026")]["Gap reason code"]) == ("stated difference", "provisional")
    assert dollars[("McNair", "FY2022")]["Tolerance"] == "1000000.00"


def test_tolerances_come_from_config(project):
    allocations_case(project)
    project.set_config("reconciliation_absolute_usd = 1_000_000", "reconciliation_absolute_usd = 0")

    project.topo("run", "--as-of", PULL)

    mcnair = rows(project, "ed_allocation_dollars")[("McNair", "FY2022")]
    assert (mcnair["Reconciliation status"], mcnair["Gap reason code"], mcnair["Tolerance"]) == (
        "stated difference", "unexplained", "24000.00")


LISTS_CASE = grant("P047A221553", 2022, 4) + grant("P047A220187", 2022, 4, amount=362_438)


def ed_lists_case(project):
    write_actions(project.raw_usaspending, PULL, LISTS_CASE + [
        action("P334A250001", 1, "2025-09-20", 2_190_400, ("2025-09-26", "2026-09-25"), action_type="A1"),
        action("P334A250002", 1, "2025-10-02", 1_852_798, ("2025-09-26", "2026-09-25"), action_type="A1"),
    ])
    lists = project.root / "data" / "raw" / "ed_grantee_lists"
    write_manifest(lists, [
        file_list(lists, "ub_84047A", "2024", "ub2024.pdf", pdf_bytes(trio_pdf_lines(2024, "Upward Bound", [
            ("P047A221553", "University of Alaska/ Anchorage", "AK", 60, 100_000),
            ("P047A220187", "Alabama State University/ Montgomery", "AL", 67, 362_438),
        ]))),
        file_list(lists, "ub_84047A", "2025", "ub2025.pdf", pdf_bytes(trio_pdf_lines(2025, "Upward Bound", [
            ("P047A221553", "University of Alaska/ Anchorage", "AK", 60, 100_000),
            ("P047A220187", "Alabama State University/ Montgomery", "AL", 67, 362_000),  # $438 apart
            ("P047A229999", "Never Funded College/ North", "AK", 75, 300_000),  # not in USAspending
        ]))),
        known_gap("ub_84047A", "2023", "known gap: no FY2023 list on ed.gov"),
        file_list(lists, "gearup_partnership_84334A", "2025", "awards.html", gearup_html_bytes({
            2025: [("Washington State University", "WA", "2,738", "$2,190,400"),
                   ("Utah State University", "UT", "2,316", "$1,852,798")],
        })),
    ])


def test_ed_lists_are_compared_exactly_and_missing_program_years_are_no_ed_list(project):
    ed_lists_case(project)

    project.topo("run", "--as-of", PULL)

    dollars, counts = rows(project, "ed_list_dollars"), rows(project, "ed_list_count")
    shown = {key: (r["Reconciliation status"], r["Gap reason code"]) for key, r in dollars.items()}
    assert shown[("Upward Bound", "FY2024")] == ("reconciled", "")
    assert shown[("Upward Bound", "FY2025")] == ("stated difference", "unexplained")
    assert (dollars[("Upward Bound", "FY2025")]["Reference value"], dollars[("Upward Bound", "FY2025")]["Compared value"]) == (
        "762000.00", "462438.00")
    assert "1 on ED list only" in dollars[("Upward Bound", "FY2025")]["Note"]
    assert "1 amount differences" in dollars[("Upward Bound", "FY2025")]["Note"]
    assert shown[("Upward Bound", "FY2023")] == ("not comparable", "no_ed_list")
    assert "known gap: no FY2023 list on ed.gov" in dollars[("Upward Bound", "FY2023")]["Note"]
    assert shown[("McNair", "FY2024")] == ("not comparable", "no_ed_list")  # no list filed at all
    assert counts[("Upward Bound", "FY2025")]["Reconciliation status"] == "stated difference"
    # GEAR UP: count and sum of new awards; the second A1 is dated in FY2026 for a Budget period starting in FY2025
    gear_up = dollars[("GEAR UP partnership", "FY2025")]
    assert (gear_up["Reconciliation status"], gear_up["Gap reason code"]) == ("stated difference", "timing_difference")
    assert (gear_up["Reference value"], gear_up["Compared value"], gear_up["Budget-period value"]) == (
        "4043198.00", "2190400.00", "4043198.00")
    assert counts[("GEAR UP partnership", "FY2025")]["Gap reason code"] == "timing_difference"


def test_ed_list_differences_are_kept_by_fain(project):
    ed_lists_case(project)

    project.topo("run", "--as-of", PULL)

    differences = pl.read_parquet(project.root / "data" / "joined" / "ed_list_fain_differences.parquet")
    assert differences.sort("fain").select("program", "fiscal_year", "fain", "kind", "ed_amount",
                                           "usaspending_amount").rows() == [
        ("Upward Bound", 2025, "P047A220187", "amount_difference", 362_000.0, 362_438.0),
        ("Upward Bound", 2025, "P047A229999", "ed_list_only", 300_000.0, None),
    ]


EVIDENCE = f"unfunded_ed_list_evidence_{PULL}.csv"


def test_unfunded_budget_periods_with_ed_list_evidence_are_counted_and_funding_status_is_unchanged(project):
    # Both Upward Bound Grants have no action for the Budget period starting 2025-09-01 (unfunded by 2025-11-30);
    # the FY2025 list (2025-26 project year) shows funding for one of them.
    write_actions(project.raw_usaspending, PULL, grant("P047A220845", 2022, 3) + grant("P047A221553", 2022, 3))
    lists = project.root / "data" / "raw" / "ed_grantee_lists"
    write_manifest(lists, [
        file_list(lists, "ub_84047A", "2025", "ub2025.pdf", pdf_bytes(trio_pdf_lines(2025, "Upward Bound", [
            ("P047A220845", "University of South Florida/ Tampa", "FL", 60, 100_000),
        ]))),
    ])

    result = project.topo("run", "--as-of", PULL)

    evidence = {(r["Program"], r["FY"]): r for r in project.read_csv(EVIDENCE)}
    assert {key: (r["Unfunded Budget periods"], r["With ED-list evidence"], r["Share"], r["Large"])
            for key, r in evidence.items()} == {
        ("Upward Bound", "FY2025"): ("2", "1", "0.5000", "yes"),
        ("All Programs", ""): ("2", "1", "0.5000", "yes"),
    }
    assert "USAspending reporting gaps" in result.output
    periods = pl.read_parquet(project.root / "data" / "joined" / "funding_status.parquet")
    status = {(f, s.isoformat()): v for f, s, v in periods.select("fain", "budget_period_start", "funding_status").rows()}
    assert status[("P047A220845", "2025-09-01")] == "unfunded"
    assert status[("P047A221553", "2025-09-01")] == "unfunded"


def test_the_evidence_count_is_reported_even_when_nothing_is_unfunded(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A220845", 2022, 4))

    project.topo("run", "--as-of", PULL)

    assert [(r["Program"], r["Unfunded Budget periods"], r["With ED-list evidence"], r["Share"], r["Large"])
            for r in project.read_csv(EVIDENCE)] == [("All Programs", "0", "0", "", "no")]


def test_a_duplicate_reconciliation_key_stops_the_run_and_misses_only_warn(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A220845", 2022, 4))
    write_curated(project.root, [], [allocation("McNair", 2023, 5_000_000), allocation("McNair", 2023, 5_000_000)])

    result = project.topo("run", "--as-of", PULL, expect_exit=2)

    assert "Structural break: duplicate check/program/fiscal_year in the reconciliation table" in result.output
    assert "ed_allocation_dollars/McNair/2023" in result.output

    write_curated(project.root, [], [allocation("McNair", 2023, 5_000_000)])
    result = project.topo("run", "--as-of", PULL)
    assert "Warning:" in result.output and "unexplained" in result.output


def test_the_committed_curated_files_have_their_schema_headers():
    curated = REPO_ROOT / "data" / "curated"
    assert (curated / "appropriations.csv").read_text().splitlines() == [",".join(APPROPRIATION_COLUMNS)]
    assert (curated / "ed_program_allocations.csv").read_text().splitlines() == [",".join(ALLOCATION_COLUMNS)]
