"""The IPEDS source: Urban bulk CSVs pulled with fake HTTP (never the network) and cleaned."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, enrollment_row, write_csv

from topo.config import load_config
from topo.guards import StructuralBreak
from topo.sources import ipeds

DIRECTORY_CSV = "colleges_ipeds_directory.csv"
ENROLLMENT_CSV = "colleges_ipeds_fall-enrollment-race_2024.csv"


def raw_ipeds(project) -> Path:
    return project.root / "data" / "raw" / "ipeds"


def test_pull_fetches_the_bulk_csvs_into_the_pull_date_folder(project):
    fetched: list[str] = []

    def download(url, dest: Path):
        fetched.append(url)
        dest.write_text("unitid,year\n")

    pulled = ipeds.pull(load_config(project.config), dt.date(2026, 10, 7), download=download)

    assert all("/csv/ipeds/" in url for url in fetched) and len(fetched) == 2
    assert [p.path.name for p in pulled] == [DIRECTORY_CSV, ENROLLMENT_CSV]
    assert all(p.path.parent == raw_ipeds(project) / "2026-10-07" for p in pulled)
    assert pulled[0].source == "ipeds" and len(pulled[0].sha256) == 64
    assert "ODC Attribution" in pulled[0].licence_citation


def test_pull_refuses_urbans_api(project):
    project.set_config(
        'directory_url = "https://educationdata.urban.org/csv/ipeds/colleges_ipeds_directory.csv"',
        'directory_url = "https://educationdata.urban.org/api/v1/college-university/ipeds/directory/2024/"',
    )

    def download(url, dest):
        raise AssertionError("no request may be made")

    with pytest.raises(StructuralBreak, match="/api/"):
        ipeds.pull(load_config(project.config), dt.date(2026, 10, 7), download=download)


def test_clean_keeps_directory_history_with_urban_missing_codes_as_nulls(project):
    folder = raw_ipeds(project) / "2026-10-07"
    write_csv(folder / DIRECTORY_CSV, DIRECTORY_COLUMNS, [
        directory_row("120971", "West Hills College Lemoore", "CA", year=2014),
        directory_row("120971", "West Hills College Lemoore", "CA", year=2016),
        directory_row("120971", "West Hills Community College-Lemoore", "CA", year=2024,
                      ueis=("UEI000000001", "UEI000000002"), newid="-2"),
        directory_row("190035", "CUNY System Office", "NY", sector=0),
    ])
    write_csv(folder / ENROLLMENT_CSV, ENROLLMENT_COLUMNS, [
        enrollment_row("120971", 2024, 3500),
        enrollment_row("120971", 2024, 2000, sex=1),
        enrollment_row("120971", 2024, 1200, ftpt=1),
    ])

    project.topo("clean", "ipeds")

    config = load_config(project.config)
    directory = ipeds.read_directory(config)
    assert directory.select("unitid", "year").rows() == [("120971", 2016), ("120971", 2024), ("190035", 2024)]
    latest = directory.row(1, named=True)
    assert latest["ueis"] == "UEI000000001|UEI000000002"
    assert latest["newid"] is None and latest["inst_alias"] is None
    assert directory["sector"].to_list() == [1, 1, 0]
    assert "chief_admin_name" not in directory.columns and "phone_number" not in directory.columns
    enrollment = ipeds.read_enrollment(config)
    assert enrollment.select("unitid", "year", "enrollment").rows() == [("120971", 2024, 3500)]


def test_clean_without_an_ipeds_pull_is_a_no_op(project):
    project.topo("clean", "ipeds")
    assert ipeds.read_directory(load_config(project.config)).height == 0


def test_a_pull_missing_the_directory_file_stops_the_run(project):
    write_csv(raw_ipeds(project) / "2026-10-07" / ENROLLMENT_CSV, ENROLLMENT_COLUMNS, [])
    result = project.topo("clean", "ipeds", expect_exit=2)
    assert "colleges_ipeds_directory.csv" in result.output
