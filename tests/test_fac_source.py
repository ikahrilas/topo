"""The FAC source: bulk CSVs pulled with fake HTTP (never the network) and cleaned with a schema check."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import pytest
from support.fac import FEDERAL_AWARDS_CSV, GENERAL_CSV, audit, award_line, write_fac
from support.ipeds import write_csv

from topo.config import load_config
from topo.guards import StructuralBreak
from topo.sources import SOURCES, fac

PULL = "2026-10-07"


def test_fac_is_a_registered_source():
    assert SOURCES["fac"] is fac


def test_pull_fetches_the_bulk_csvs_into_the_pull_date_folder_without_a_key(project):
    fetched: list[str] = []

    def download(url, dest: Path):
        fetched.append(url)
        dest.write_text("report_id\n")

    pulled = fac.pull(load_config(project.config), dt.date(2026, 10, 7), download=download)

    assert sorted(Path(u).name for u in fetched) == [FEDERAL_AWARDS_CSV, GENERAL_CSV]
    assert all(u.startswith("https://app.fac.gov/dissemination/public-data/gsa/full/") for u in fetched)
    folder = project.root / "data" / "raw" / "fac" / PULL
    assert sorted(p.path for p in pulled) == [folder / FEDERAL_AWARDS_CSV, folder / GENERAL_CSV]
    assert {p.source for p in pulled} == {"fac"} and all(len(p.sha256) == 64 for p in pulled)
    assert all("Federal Audit Clearinghouse" in p.licence_citation for p in pulled)


def test_clean_keeps_trio_and_gear_up_lines_with_their_listing_and_direct_flag(project):
    write_fac(project.root, PULL, [
        award_line("AAAAAAAAAAA1", 2024, "047", 687_754),
        award_line("AAAAAAAAAAA1", 2024, "042A", 300_000, reference="AWARD-0002"),  # suffixed extension
        award_line("AAAAAAAAAAA1", 2024, "334", 50_000, is_direct="N", reference="AWARD-0003"),
        award_line("AAAAAAAAAAA1", 2024, "063", 9_000_000, reference="AWARD-0004"),  # Pell: not a Program listing
        award_line("AAAAAAAAAAA1", 2024, "103", 10_000, reference="AWARD-0005"),  # 84.103 is not a Program
        award_line("AAAAAAAAAAA1", 2024, "047", 1_000, prefix="93", reference="AWARD-0006"),  # HHS 93.047
    ])

    project.topo("clean", "fac")

    lines = fac.read_award_lines(load_config(project.config)).sort("award_reference")
    assert lines.select("listing", "amount_expended", "is_direct").rows() == [
        ("84.047", 687_754, True), ("84.042", 300_000, True), ("84.334", 50_000, False),
    ]
    audits = fac.read_audits(load_config(project.config))
    assert audits.columns == [
        "report_id", "auditee_uei", "auditee_name", "auditee_state", "entity_type", "audit_year",
        "fy_start_date", "fy_end_date", "raw_file", "pull_date",
    ]
    assert audits.height == 1


def test_clean_never_ingests_auditee_contacts_or_eins(project):
    write_fac(project.root, PULL, [award_line("AAAAAAAAAAA1", 2024, "047", 1)])
    project.topo("clean", "fac")
    cleaned = project.root / "data" / "cleaned"
    for path in cleaned.glob("fac_*.parquet"):
        columns = pl.read_parquet(path).columns
        assert not any("contact" in c or "email" in c or "phone" in c or "ein" in c.split("_") for c in columns), path


def test_a_bulk_file_missing_a_required_column_is_a_structural_break(project):
    folder = write_fac(project.root, PULL, [award_line("AAAAAAAAAAA1", 2024, "047", 1)])
    write_csv(folder / FEDERAL_AWARDS_CSV, ["report_id", "auditee_uei", "audit_year"], [
        {"report_id": "r", "auditee_uei": "AAAAAAAAAAA1", "audit_year": "2024"},
    ])
    result = project.topo("clean", "fac", expect_exit=2)
    assert "Structural break" in result.output and "is_direct" in result.output


def test_an_unreadable_amount_is_a_structural_break(project):
    write_fac(project.root, PULL, [award_line("AAAAAAAAAAA1", 2024, "047", 1) | {"amount_expended": "lots"}])
    result = project.topo("clean", "fac", expect_exit=2)
    assert "Structural break" in result.output


def test_a_pull_folder_missing_a_bulk_file_is_a_structural_break(project):
    folder = write_fac(project.root, PULL, [award_line("AAAAAAAAAAA1", 2024, "047", 1)])
    (folder / GENERAL_CSV).unlink()
    result = project.topo("clean", "fac", expect_exit=2)
    assert GENERAL_CSV in result.output


def test_clean_without_any_fac_pull_is_a_no_op(project):
    project.topo("clean", "fac")
    assert fac.read_award_lines(load_config(project.config)).height == 0


def test_clean_logs_dropped_lines_by_named_reason(project):
    write_fac(project.root, PULL, [
        award_line("AAAAAAAAAAA1", 2024, "047", 1),
        award_line("AAAAAAAAAAA1", 2024, "063", 1, reference="AWARD-0002"),
    ], audits=[audit("AAAAAAAAAAA1", 2024, "A"), audit("BBBBBBBBBBB2", 2024, "B")])
    project.topo("clean", "fac")
    log = pl.read_parquet(project.output / "run_log.parquet")
    by_source = {r["source"]: r for r in log.iter_rows(named=True)}
    lines, audits = by_source["fac_award_lines"], by_source["fac_audits"]
    assert (lines["rows_in"], lines["rows_out"]) == (2, 1)
    assert lines["drops"] == [{"reason": "not_a_trio_gear_up_listing", "rows": 1}]
    assert (audits["rows_in"], audits["rows_out"]) == (2, 1)
    assert audits["drops"] == [{"reason": "no_trio_gear_up_line", "rows": 1}]
