"""The CCD LEA directory source: Urban bulk CSV pulled with fake HTTP (never the network) and cleaned."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from support.ccd import LEA_COLUMNS, LEA_CSV, lea_row
from support.ipeds import write_csv

from topo.config import load_config
from topo.guards import StructuralBreak
from topo.sources import SOURCES, ccd


def raw_ccd(project) -> Path:
    return project.root / "data" / "raw" / "ccd"


def test_ccd_is_a_registered_source():
    assert SOURCES["ccd"] is ccd


def test_pull_fetches_the_bulk_csv_into_the_pull_date_folder(project):
    fetched: list[str] = []

    def download(url, dest: Path):
        fetched.append(url)
        dest.write_text("leaid,year\n")

    pulled = ccd.pull(load_config(project.config), dt.date(2026, 10, 7), download=download)

    assert len(fetched) == 1 and "/csv/ccd/" in fetched[0]
    assert [p.path for p in pulled] == [raw_ccd(project) / "2026-10-07" / LEA_CSV]
    assert pulled[0].source == "ccd" and len(pulled[0].sha256) == 64
    assert "ODC Attribution" in pulled[0].licence_citation


def test_pull_refuses_urbans_api(project):
    project.set_config(
        'lea_directory_url = "https://educationdata.urban.org/csv/ccd/school-districts_lea_directory.csv"',
        'lea_directory_url = "https://educationdata.urban.org/api/v1/school-districts/ccd/directory/2024/"',
    )

    def download(url, dest):
        raise AssertionError("no request may be made")

    with pytest.raises(StructuralBreak, match="/api/"):
        ccd.pull(load_config(project.config), dt.date(2026, 10, 7), download=download)


def test_clean_keeps_district_history_of_district_agency_types(project):
    write_csv(raw_ccd(project) / "2026-10-07" / LEA_CSV, LEA_COLUMNS, [
        lea_row("4900630", "Ogden School District", "UT", year=2014),
        lea_row("4900630", "Ogden City School District", "UT", year=2016),
        lea_row("4900630", "Ogden City School District", "UT", year=2024, zip="84401", city="OGDEN"),
        lea_row("4800001", "Region 12 Education Service Center", "TX", agency_type=4),
        lea_row("2500001", "Some Supervisory Union", "MA", agency_type=3),
        lea_row("0600001", "A Specialized School", "CA", agency_type=9, zip="-2"),
    ])

    project.topo("clean", "ccd")

    leas = ccd.read_lea_directory(load_config(project.config))
    assert leas.select("leaid", "year").rows() == [("4800001", 2024), ("4900630", 2016), ("4900630", 2024)]
    ogden = leas.row(2, named=True)
    assert (ogden["lea_name"], ogden["state_location"], ogden["city_location"], ogden["zip_location"]) == (
        "Ogden City School District", "UT", "OGDEN", "84401",
    )
    assert leas["agency_type"].to_list() == [4, 1, 1]
    assert "phone" not in leas.columns and "number_of_schools" not in leas.columns


def test_urban_missing_codes_become_nulls(project):
    write_csv(raw_ccd(project) / "2026-10-07" / LEA_CSV, LEA_COLUMNS, [
        lea_row("4900630", "Ogden City School District", "UT", zip="-2", city="-1"),
    ])
    project.topo("clean", "ccd")
    ogden = ccd.read_lea_directory(load_config(project.config)).row(0, named=True)
    assert ogden["zip_location"] is None and ogden["city_location"] is None


def test_clean_without_a_ccd_pull_is_a_no_op(project):
    project.topo("clean", "ccd")
    assert ccd.read_lea_directory(load_config(project.config)).height == 0


def test_a_directory_lacking_a_read_column_stops_the_run(project):
    columns = [c for c in LEA_COLUMNS if c != "state_location"]
    write_csv(raw_ccd(project) / "2026-10-07" / LEA_CSV, columns, [
        {k: v for k, v in lea_row("4900630", "Ogden City School District", "UT").items() if k in columns},
    ])
    result = project.topo("clean", "ccd", expect_exit=2)
    assert "state_location" in result.output


def test_a_pull_missing_the_directory_file_stops_the_run(project):
    (raw_ccd(project) / "2026-10-07").mkdir(parents=True)
    result = project.topo("clean", "ccd", expect_exit=2)
    assert LEA_CSV in result.output


def test_a_duplicate_district_year_stops_the_run(project):
    write_csv(raw_ccd(project) / "2026-10-07" / LEA_CSV, LEA_COLUMNS, [
        lea_row("4900630", "Ogden City School District", "UT"),
        lea_row("4900630", "Ogden City School District", "UT"),
    ])
    project.topo("clean", "ccd", expect_exit=2)
