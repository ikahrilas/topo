"""Seam 1: the FAC plausibility check (#43) via `topo run`: a third source compared without pass/fail.

As of 2026-10-07 the reporting window is FY2021-FY2026; the five-year span is
FY2021-FY2025 (the latest audit year is still being filed), compared with FAC
audit years 2021-2025.
"""

from __future__ import annotations

import json

import polars as pl
from support.fac import audit, award_line, write_fac
from support.usaspending import action, write_actions

PULL = "2026-10-07"
PLAUSIBILITY = f"fac_plausibility_{PULL}.csv"


def grant(fain: str, uei: str, amounts: dict[int, float], recipient: str = "FIXTURE COLLEGE") -> list[dict]:
    """One Grant with one action per FY (dated in May, so the action-date FY is that year)."""
    return [
        action(fain, i + 1, f"{fy}-05-15", amount, (f"{fy}-09-01", f"{fy + 1}-08-31"),
               action_type="A1" if i == 0 else "B1", uei=uei, recipient=recipient)
        for i, (fy, amount) in enumerate(sorted(amounts.items()))
    ]


def expended(uei: str, extension: str, amounts: dict[int, int], **kw) -> list[dict]:
    return [award_line(uei, year, extension, amount, reference=f"AWARD-{extension}-{kw.get('is_direct', 'Y')}", **kw)
            for year, amount in amounts.items()]


FIVE_YEARS = {fy: 100_000 for fy in range(2021, 2026)}  # 500,000 over the span


def case(project):
    write_actions(project.raw_usaspending, PULL, [
        *grant("P047A210001", "PLAUSIBLE001", FIVE_YEARS | {2026: 100_000}, recipient="PLAUSIBLE COLLEGE"),
        *grant("P042A210002", "LOWRATIO0002", FIVE_YEARS),
        *grant("P044A210003", "HIGHRATIO003", FIVE_YEARS),
        *grant("P066A210004", "EDGERATIO004", FIVE_YEARS),
        *grant("P217A210005", "USASPONLY005", FIVE_YEARS),
        *grant("P334A210006", "INDIRECTONLY", FIVE_YEARS),
    ])
    write_fac(project.root, PULL, [
        *expended("PLAUSIBLE001", "047", {y: 90_000 for y in range(2021, 2026)}),  # 450,000 -> 0.90
        *expended("PLAUSIBLE001", "047", {2023: 1_000_000}, is_direct="N"),  # subaward money: never compared
        *expended("PLAUSIBLE001", "047", {2020: 5_000_000}),  # before the span
        *expended("PLAUSIBLE001", "047", {2026: 5_000_000}),  # after the span
        *expended("LOWRATIO0002", "042A", {2022: 100_000, 2023: 100_000}),  # 200,000 -> 0.40
        *expended("HIGHRATIO003", "044", {y: 160_000 for y in range(2021, 2026)}),  # 800,000 -> 1.60
        *expended("EDGERATIO004", "066", {y: 150_000 for y in range(2021, 2026)}),  # 750,000 -> exactly 1.50
        *expended("FACONLY00007", "047", {2024: 300_000}),  # no USAspending Grant
        *expended("INDIRECTONLY", "334", {y: 100_000 for y in range(2021, 2026)}, is_direct="N"),
    ])


def by_uei(project, name: str = PLAUSIBILITY) -> dict[str, dict[str, str]]:
    return {r["Recipient UEI"]: r for r in project.read_csv(name)}


def test_five_year_ratios_under_half_or_over_one_and_a_half_are_review_and_nothing_passes_or_fails(project):
    case(project)

    project.topo("run", "--as-of", PULL)

    rows = by_uei(project)
    shown = {uei: (r["USAspending obligation"], r["FAC amount expended"], r["Ratio"], r["Flag"])
             for uei, r in rows.items()}
    assert shown == {
        "PLAUSIBLE001": ("500000.00", "450000.00", "0.90", "not flagged"),
        "LOWRATIO0002": ("500000.00", "200000.00", "0.40", "review"),
        "HIGHRATIO003": ("500000.00", "800000.00", "1.60", "review"),
        "EDGERATIO004": ("500000.00", "750000.00", "1.50", "not flagged"),
    }
    header = project.read_csv(PLAUSIBILITY)[0].keys()
    assert "Reconciliation status" not in header and "Gap reason code" not in header
    assert {r["Flag"] for r in rows.values()} <= {"review", "not flagged"}


def test_only_direct_lines_and_ueis_in_both_sources_are_compared(project):
    case(project)

    project.topo("run", "--as-of", PULL)

    rows = by_uei(project)
    assert "USASPONLY005" not in rows  # never in FAC
    assert "FACONLY00007" not in rows  # never in USAspending
    assert "INDIRECTONLY" not in rows  # in FAC only on pass-through (is_direct = N) lines
    plausible = rows["PLAUSIBLE001"]
    assert (plausible["Listing"], plausible["Programs"], plausible["Span"], plausible["FAC audit years"]) == (
        "84.047", "Upward Bound", "FY2021-FY2025", "5")
    assert plausible["Recipient"] == "PLAUSIBLE COLLEGE"
    assert plausible["FAC auditee"] == "FIXTURE AUDITEE"
    assert rows["LOWRATIO0002"]["FAC audit years"] == "2"


def test_every_row_is_labelled_plausibility_not_reconciliation(project):
    case(project)

    project.topo("run", "--as-of", PULL)

    rows = project.read_csv(PLAUSIBILITY)
    assert rows and {r["Basis"] for r in rows} == {"plausibility, not reconciliation"}
    assert {r["Check"] for r in rows} == {"fac_plausibility"}
    assert all(r["Note"] for r in rows)


def test_check_d_summarises_the_review_count_per_program_and_span_in_the_reconciliation_table(project):
    # Spec #28: the reconciliation table compares the data with "... and the FAC"; checks (a)-(d).
    case(project)

    project.topo("run", "--as-of", PULL)

    rows = {r["Program"]: r for r in project.read_csv(f"reconciliation_{PULL}.csv")
            if r["Check"] == "fac_plausibility"}
    assert set(rows) == {
        "Student Support Services", "Talent Search",
        "Upward Bound; Upward Bound Math and Science; Veterans Upward Bound",
        "Educational Opportunity Centers", "McNair", "GEAR UP partnership; GEAR UP state",
    }
    assert {r["FY"] for r in rows.values()} == {"FY2021-FY2025"}
    assert {(r["Reconciliation status"], r["Gap reason code"]) for r in rows.values()} == {
        ("not comparable", "plausibility_only")}
    assert all(r["Note"].startswith("plausibility, not reconciliation") for r in rows.values())
    assert "1 of 1 (Recipient UEI, listing) pairs flagged review" in rows["Talent Search"]["Note"]
    assert "0 of 1 (Recipient UEI, listing) pairs flagged review" in rows["Educational Opportunity Centers"]["Note"]
    assert "no Recipient UEI in both sources" in rows["McNair"]["Note"]
    ub = rows["Upward Bound; Upward Bound Math and Science; Veterans Upward Bound"]
    assert (ub["Reference value"], ub["Compared value"], ub["Gap"]) == ("500000.00", "450000.00", "")


def test_a_ueis_listing_with_no_direct_fac_line_reads_zero_and_review(project):
    write_actions(project.raw_usaspending, PULL, [
        *grant("P047A210001", "BOTHSOURCES1", FIVE_YEARS),
        *grant("P042A210002", "BOTHSOURCES1", FIVE_YEARS),
    ])
    write_fac(project.root, PULL, expended("BOTHSOURCES1", "047", {y: 100_000 for y in range(2021, 2026)}))

    project.topo("run", "--as-of", PULL)

    rows = {r["Listing"]: r for r in project.read_csv(PLAUSIBILITY)}
    assert (rows["84.047"]["Ratio"], rows["84.047"]["Flag"]) == ("1.00", "not flagged")
    assert (rows["84.042"]["FAC amount expended"], rows["84.042"]["Ratio"], rows["84.042"]["Flag"]) == (
        "0.00", "0.00", "review")


def test_bounds_come_from_config(project):
    case(project)
    project.set_config("plausibility_ratio_low = 0.5", "plausibility_ratio_low = 0.3")
    project.set_config("plausibility_ratio_high = 1.5", "plausibility_ratio_high = 1.7")

    project.topo("run", "--as-of", PULL)

    rows = by_uei(project)
    assert (rows["LOWRATIO0002"]["Flag"], rows["HIGHRATIO003"]["Flag"]) == ("not flagged", "not flagged")


def test_span_comes_from_config(project):
    case(project)
    project.set_config("plausibility_years = 5", "plausibility_years = 2")

    project.topo("run", "--as-of", PULL)

    rows = by_uei(project)
    assert "LOWRATIO0002" not in rows  # its FAC lines (audit years 2022-2023) fall outside FY2024-FY2025
    plausible = rows["PLAUSIBLE001"]
    assert (plausible["Span"], plausible["USAspending obligation"], plausible["FAC amount expended"],
            plausible["FAC audit years"], plausible["Ratio"]) == ("FY2024-FY2025", "200000.00", "180000.00", "2", "0.90")


def test_the_plausibility_csv_gets_a_provenance_sidecar_with_the_fac_raw_files(project):
    case(project)

    project.topo("run", "--as-of", PULL)

    sidecar = json.loads((project.output / f"{PLAUSIBILITY}.provenance.json").read_text())
    assert sidecar["as_of"] == PULL and sidecar["pull_date"] == PULL
    assert {f["source"] for f in sidecar["raw_files"]} >= {"usaspending", "fac"}


def test_without_a_fac_pull_the_run_still_delivers_an_empty_plausibility_table(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A210001", "PLAUSIBLE001", FIVE_YEARS))

    project.topo("run", "--as-of", PULL)

    assert project.read_csv(PLAUSIBILITY) == []
    assert (project.output / PLAUSIBILITY).read_text().startswith("Check,Basis,")


def test_the_fac_auditee_name_comes_from_the_audit_report(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A210001", "PLAUSIBLE001", FIVE_YEARS))
    lines = expended("PLAUSIBLE001", "047", {y: 100_000 for y in range(2021, 2026)})
    write_fac(project.root, PULL, lines, audits=[
        audit("PLAUSIBLE001", int(line["audit_year"]), f"AUDITEE {line['audit_year']}", report_id=line["report_id"])
        for line in lines
    ])

    project.topo("run", "--as-of", PULL)

    assert by_uei(project)["PLAUSIBLE001"]["FAC auditee"] == "AUDITEE 2025"  # the latest audit in the span


def test_the_join_logs_every_fac_line_as_compared_or_dropped_by_named_reason(project):
    case(project)

    project.topo("run", "--as-of", PULL)

    log = pl.read_parquet(project.output / "run_log.parquet").filter(pl.col("source") == "fac_plausibility")
    row = log.row(0, named=True)
    assert (row["layer"], row["rows_in"], row["rows_out"]) == ("join", 26, 17)
    assert sorted((d["reason"], d["rows"]) for d in row["drops"]) == [
        ("not_direct", 6), ("outside_span", 2), ("uei_not_in_both_sources", 1)]
