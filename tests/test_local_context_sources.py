"""The Local context sources: EDGE geocodes and district polygons, and the SAIPE flat file.

Pulled with fake HTTP (never the network) and cleaned from hand-built raw files.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import pytest
from support.geo import (
    DISTRICTS_ZIP, ELEMENTARY, GEOCODE_ZIP, SAIPE_CSV, UNIFIED, box, district, geocode_row, saipe_row,
    write_districts, write_geocodes, write_saipe,
)

from topo.config import load_config
from topo.guards import StructuralBreak
from topo.sources import SOURCES, edge, saipe

PULL = "2026-10-07"


def raw(project, source: str) -> Path:
    return project.root / "data" / "raw" / source / PULL


def logged(project) -> dict:
    return {(r["layer"], r["source"]): r for r in pl.read_parquet(project.output / "run_log.parquet").to_dicts()}


def drops(row) -> dict[str, int]:
    return {d["reason"]: d["rows"] for d in row["drops"]}


def test_edge_and_saipe_are_registered_sources():
    assert SOURCES["edge"] is edge
    assert SOURCES["saipe"] is saipe


def test_saipe_pull_fetches_the_census_flat_file(project):
    fetched: list[str] = []

    def download(url, dest: Path):
        fetched.append(url)
        dest.write_text("x\n")

    pulled = saipe.pull(load_config(project.config), dt.date(2026, 10, 7), download=download)

    assert fetched == ["https://www2.census.gov/programs-surveys/saipe/datasets/2024/2024-school-districts/ussd24.csv"]
    assert [p.path for p in pulled] == [raw(project, "saipe") / SAIPE_CSV]
    assert pulled[0].source == "saipe" and "Census" in pulled[0].licence_citation


def test_saipe_clean_gives_the_ages_5_17_poverty_rate_by_leaid_with_its_data_year(project):
    write_saipe(raw(project, "saipe") / SAIPE_CSV, [
        saipe_row("DC", "11", "00030", "District of Columbia Public Schools", 90393, 22266),
        saipe_row("AZ", "4", "8340", "Tempe Union High School District", 20000, 2000),
        saipe_row("AZ", "04", "99999", "Empty district", 0, 0),
    ])

    project.topo("clean", "saipe")

    rows = pl.read_parquet(project.root / "data" / "cleaned" / "saipe_school_districts.parquet")
    assert rows.select("leaid", "district_name", "children_5_17", "children_5_17_in_poverty", "data_year").rows() == [
        ("0408340", "Tempe Union High School District", 20000, 2000, 2024),
        ("1100030", "District of Columbia Public Schools", 90393, 22266, 2024),
    ]
    assert rows["poverty_rate_5_17"].round(4).to_list() == [0.1, 0.2463]
    clean = logged(project)[("clean", "saipe_school_districts")]
    assert (clean["rows_in"], clean["rows_out"]) == (3, 2)
    assert drops(clean) == {"no_children_5_17": 1}


def test_saipe_clean_without_a_pull_is_a_no_op(project):
    project.topo("clean", "saipe")
    assert not (project.root / "data" / "cleaned" / "saipe_school_districts.parquet").exists()


def test_saipe_file_without_the_expected_header_is_a_structural_break(project):
    path = raw(project, "saipe") / SAIPE_CSV
    path.parent.mkdir(parents=True)
    path.write_text("a,b,c\n1,2,3\n")

    result = project.topo("clean", "saipe", expect_exit=2)
    assert "District ID" in result.output


def test_edge_pull_fetches_the_geocodes_and_the_district_polygons(project):
    fetched: list[str] = []

    def download(url, dest: Path):
        fetched.append(url)
        dest.write_bytes(b"zip")

    pulled = edge.pull(load_config(project.config), dt.date(2026, 10, 7), download=download)

    assert [Path(u).name for u in fetched] == [GEOCODE_ZIP, DISTRICTS_ZIP]
    assert all(u.startswith("https://nces.ed.gov/programs/edge/") for u in fetched)
    assert [p.path for p in pulled] == [raw(project, "edge") / GEOCODE_ZIP, raw(project, "edge") / DISTRICTS_ZIP]
    assert "public domain" in pulled[0].licence_citation


def test_edge_clean_keeps_campus_points_and_district_polygons(project):
    write_geocodes(raw(project, "edge") / GEOCODE_ZIP, [
        geocode_row("104151", "Arizona State University Campus Immersion", "AZ", 33.42, -111.93),
        geocode_row("999999", "A college with no point", "AZ", "", ""),
    ])
    write_districts(raw(project, "edge") / DISTRICTS_ZIP, [
        district("0408310", "Tempe School District", ELEMENTARY, box(-112, 33, -111, 34)),
        district("0499997", "School District Not Defined", UNIFIED, box(-120, 30, -119, 31)),
    ])

    project.topo("clean", "edge")

    cleaned = project.root / "data" / "cleaned"
    points = pl.read_parquet(cleaned / "edge_postsecondary_geocodes.parquet")
    assert points.select("unitid", "lat", "lon", "school_year").rows() == [("104151", 33.42, -111.93, "2025-2026")]
    polygons = pl.read_parquet(cleaned / "edge_school_districts.parquet")
    assert polygons.select("leaid", "district_name", "district_type", "school_year").rows() == [
        ("0408310", "Tempe School District", "elementary", "2024-2025"),
    ]
    log = logged(project)
    assert drops(log[("clean", "edge_postsecondary_geocodes")]) == {"no_coordinates": 1}
    assert drops(log[("clean", "edge_school_districts")]) == {"no_school_district_defined": 1}


def test_edge_clean_without_a_pull_is_a_no_op_and_a_partial_pull_breaks(project):
    project.topo("clean", "edge")
    write_geocodes(raw(project, "edge") / GEOCODE_ZIP, [])
    with pytest.raises(StructuralBreak, match=DISTRICTS_ZIP):
        edge.clean(load_config(project.config))
