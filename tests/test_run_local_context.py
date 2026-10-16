"""Seam 1: `topo run` attaches Local context to each Grant through its Host institution, never the Recipient."""

from __future__ import annotations

import json

import polars as pl
from support.ccd import LEA_COLUMNS, LEA_CSV, lea_row
from support.geo import (
    DISTRICTS_ZIP, ELEMENTARY, GEOCODE_ZIP, SAIPE_CSV, SECONDARY, UNIFIED, box, district, geocode_row, saipe_row,
    write_districts, write_geocodes, write_saipe,
)
from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, enrollment_row, write_csv
from support.usaspending import action, write_actions

PULL = "2026-10-07"
IHE = "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"
NONPROFIT = "NONPROFIT WITH 501C3 IRS STATUS (OTHER THAN AN INSTITUTION OF HIGHER EDUCATION)"


def one_year(fain, recipient, uei, state, business_types=IHE, description=None):
    extra = {}
    if description:
        extra = {"transaction_description": description, "prime_award_base_transaction_description": description}
    return action(fain, 1, "2025-07-01", 300000, ("2025-09-01", "2026-08-31"), action_type="A1",
                  recipient=recipient, uei=uei, state=state, business_types_description=business_types, **extra)


GRANTS = [
    one_year("P042A250001", "ROCKY MOUNTAIN COLLEGE", "RMCUEI000001", "MT"),                     # college, unified
    one_year("P047A250002", "ARIZONA STATE UNIVERSITY", "ASUUEI000001", "AZ"),                   # elementary + secondary
    one_year("P334A250003", "UNIVERSITY OF TEXAS AT EL PASO", "UTEPUEI00001", "TX",
             description="GEAR UP PARTNERSHIP SERVING SOCORRO INDEPENDENT SCHOOL DISTRICT"),     # district Host
    one_year("P334A250004", "UNIVERSITY OF TEXAS AT EL PASO", "UTEPUEI00001", "TX",
             description="GEAR UP PARTNERSHIP SERVING IDEA PUBLIC SCHOOLS"),                     # charter: no SAIPE row
    one_year("P042A250005", "REGENTS OF THE UNIVERSITY OF MINNESOTA", "UMNUEI000001", "MN"),     # review
    one_year("P044A250006", "MASSACHUSETTS HIGHER EDUCATION ASSISTANCE CORPORATION", "MHEAC0000001", "MA",
             NONPROFIT),                                                                          # no single Host
    one_year("P042A250007", "OKLAHOMA COLLEGE", "OKUEI0000001", "OK"),                           # unmatched
]


def write_sources(project):
    write_actions(project.raw_usaspending, PULL, GRANTS)
    ipeds = project.root / "data" / "raw" / "ipeds" / PULL
    write_csv(ipeds / "colleges_ipeds_directory.csv", DIRECTORY_COLUMNS, [
        directory_row("180595", "Rocky Mountain College", "MT", ueis=("RMCUEI000001",), sector=1, year=2023),
        directory_row("180595", "Rocky Mountain College", "MT", ueis=("RMCUEI000001",), sector=2, year=2024),
        directory_row("104151", "Arizona State University Campus Immersion", "AZ", ueis=("ASUUEI000001",), sector=1),
        directory_row("228796", "The University of Texas at El Paso", "TX", ueis=("UTEPUEI00001",)),
        directory_row("174066", "University of Minnesota-Twin Cities", "MN", ueis=("UMNUEI000001",)),
        directory_row("174233", "University of Minnesota-Duluth", "MN", ueis=("UMNUEI000001",)),
    ])
    write_csv(ipeds / "colleges_ipeds_fall-enrollment-race_2024.csv", ENROLLMENT_COLUMNS, [
        enrollment_row("180595", 2023, 850),
        enrollment_row("180595", 2024, 900),
        enrollment_row("104151", 2024, 80000),
        enrollment_row("174066", 2024, 50000),  # a review candidate: its context must not leak onto the row
    ])
    write_csv(project.root / "data" / "raw" / "ccd" / PULL / LEA_CSV, LEA_COLUMNS, [
        lea_row("4840860", "Socorro Independent School District", "TX", enrollment=47000),
        lea_row("4800209", "IDEA Public Schools", "TX", agency_type=7, enrollment=80000),
        lea_row("0408340", "Tempe Union High School District", "AZ"),
    ])
    edge = project.root / "data" / "raw" / "edge" / PULL
    write_geocodes(edge / GEOCODE_ZIP, [
        geocode_row("180595", "Rocky Mountain College", "MT", 45.80, -108.55),
        geocode_row("104151", "Arizona State University Campus Immersion", "AZ", 33.42, -111.93),
        geocode_row("174066", "University of Minnesota-Twin Cities", "MN", 44.97, -93.23),
    ])
    write_districts(edge / DISTRICTS_ZIP, [
        district("3004380", "Billings Public Schools", UNIFIED, box(-109, 45.5, -108, 46)),
        district("0408310", "Tempe School District", ELEMENTARY, box(-112, 33, -111, 34)),
        district("0408340", "Tempe Union High School District", SECONDARY, box(-112.5, 33, -111.5, 34)),
        district("2723190", "Minneapolis Public School District", UNIFIED, box(-94, 44.5, -93, 45.5)),
        district("4840860", "Socorro Independent School District", UNIFIED, box(-106.5, 31.5, -106, 32)),
    ])
    write_saipe(project.root / "data" / "raw" / "saipe" / PULL / SAIPE_CSV, [
        saipe_row("MT", "30", "04380", "Billings Public Schools", 20000, 3000),
        saipe_row("AZ", "04", "08310", "Tempe School District", 10000, 2500),
        saipe_row("AZ", "04", "08340", "Tempe Union High School District", 20000, 2000),
        saipe_row("MN", "27", "23190", "Minneapolis Public School District", 50000, 10000),
        saipe_row("TX", "48", "40860", "Socorro Independent School District", 40000, 8000),
    ])


CONTEXT_COLUMNS = [
    "Institution type", "Institution type year", "Enrollment", "Enrollment year",
    "Poverty rate (ages 5-17)", "Poverty rate of", "Poverty rate year", "Campus district year",
    "Campus district overlap", "Context reason",
]


def context(project) -> dict[str, dict[str, str]]:
    rows = project.read_csv(f"target_list_{PULL}.csv")
    return {r["FAIN"]: {c: r[c] for c in CONTEXT_COLUMNS} for r in rows}


def test_a_college_host_shows_its_campus_districts_poverty_rate_labelled_as_such(project):
    write_sources(project)

    project.topo("run", "--as-of", PULL)

    assert context(project)["P042A250001"] == {
        "Institution type": "Private nonprofit, 4-year or above",
        "Institution type year": "2024",
        "Enrollment": "900",
        "Enrollment year": "2024",
        "Poverty rate (ages 5-17)": "0.15",
        "Poverty rate of": "Campus district: Billings Public Schools (LEAID 3004380)",
        "Poverty rate year": "2024",
        "Campus district year": "2024-2025",
        "Campus district overlap": "",
        "Context reason": "",
    }


def test_a_campus_in_elementary_and_secondary_districts_keeps_both_and_shows_the_secondary_one(project):
    write_sources(project)

    project.topo("run", "--as-of", PULL)

    asu = context(project)["P047A250002"]
    assert asu["Poverty rate of"] == "Campus district: Tempe Union High School District (LEAID 0408340)"
    assert asu["Poverty rate (ages 5-17)"] == "0.1"
    assert asu["Campus district overlap"] == "also in elementary district Tempe School District (LEAID 0408310)"
    joined = pl.read_parquet(project.root / "data" / "joined" / "campus_districts.parquet")
    assert joined.filter(pl.col("unitid") == "104151").sort("leaid").select(
        "leaid", "district_type", "is_primary", "overlap", "located_by", "school_year"
    ).rows() == [
        ("0408310", "elementary", False, True, "edge_point", "2024-2025"),
        ("0408340", "secondary", True, True, "edge_point", "2024-2025"),
    ]


def test_a_district_host_takes_the_poverty_rate_of_its_own_leaid(project):
    write_sources(project)

    project.topo("run", "--as-of", PULL)

    socorro = context(project)["P334A250003"]
    assert socorro == {
        "Institution type": "Regular school district",
        "Institution type year": "2024",
        "Enrollment": "47000",
        "Enrollment year": "2024",
        "Poverty rate (ages 5-17)": "0.2",
        "Poverty rate of": "Host district: Socorro Independent School District (LEAID 4840860)",
        "Poverty rate year": "2024",
        "Campus district year": "",
        "Campus district overlap": "",
        "Context reason": "",
    }


def test_null_context_carries_a_reason_and_is_never_borrowed(project):
    write_sources(project)

    project.topo("run", "--as-of", PULL)

    rows = context(project)
    charter = rows["P334A250004"]
    assert (charter["Institution type"], charter["Enrollment"]) == ("Independent charter district", "80000")
    assert (charter["Poverty rate (ages 5-17)"], charter["Poverty rate of"], charter["Context reason"]) == (
        "", "", "no_saipe_row",
    )
    blank = {c: "" for c in CONTEXT_COLUMNS if c != "Context reason"}
    assert {fain: rows[fain] for fain in ("P042A250005", "P044A250006", "P042A250007")} == {
        "P042A250005": {**blank, "Context reason": "in_review"},
        "P044A250006": {**blank, "Context reason": "no_single_host"},
        "P042A250007": {**blank, "Context reason": "unmatched"},
    }


def test_the_match_quality_report_counts_context_reason_codes(project):
    write_sources(project)

    project.topo("run", "--as-of", PULL)

    counts = {r["Context reason"]: r["Grants"] for r in project.read_csv(f"match_quality_context_{PULL}.csv")}
    assert counts == {
        "no_saipe_row": "1", "no_campus_district": "0", "no_enrollment_row": "0",
        "no_single_host": "1", "unmatched": "1", "in_review": "1",
    }
    sidecar = json.loads((project.output / f"match_quality_context_{PULL}.csv.provenance.json").read_text())
    assert {f["source"] for f in sidecar["raw_files"]} >= {"edge", "saipe", "ipeds", "ccd"}


def test_without_any_context_source_every_matched_grant_says_why(project):
    write_actions(project.raw_usaspending, PULL, GRANTS[:1])
    write_csv(project.root / "data" / "raw" / "ipeds" / PULL / "colleges_ipeds_directory.csv", DIRECTORY_COLUMNS, [
        directory_row("180595", "Rocky Mountain College", "MT", ueis=("RMCUEI000001",), sector=2),
    ])
    write_csv(project.root / "data" / "raw" / "ipeds" / PULL / "colleges_ipeds_fall-enrollment-race_2024.csv",
              ENROLLMENT_COLUMNS, [])

    project.topo("run", "--as-of", PULL)

    rocky = context(project)["P042A250001"]
    assert rocky["Institution type"] == "Private nonprofit, 4-year or above"
    assert (rocky["Enrollment"], rocky["Poverty rate (ages 5-17)"]) == ("", "")
    assert rocky["Context reason"] == "no_enrollment_row|no_campus_district"
