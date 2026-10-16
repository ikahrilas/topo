"""Seam 1: `topo run` links GEAR UP partnerships to the districts they serve, from the CCD LEA directory."""

from __future__ import annotations

import json

import polars as pl
from support.ccd import LEA_COLUMNS, LEA_CSV, lea_row
from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, write_csv
from support.usaspending import action, write_actions

PULL = "2026-10-07"
IHE = "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"


def partnership(fain, recipient, uei, state, description, business_types=IHE):
    return action(fain, 1, "2025-07-01", 500000, ("2025-09-01", "2026-08-31"), action_type="A1",
                  recipient=recipient, uei=uei, state=state, business_types_description=business_types,
                  transaction_description=description, prime_award_base_transaction_description=description)


GRANTS = [
    partnership("P334A250001", "UNIVERSITY OF TEXAS AT EL PASO", "UTEPUEI00001", "TX",
                "GEAR UP PARTNERSHIP SERVING SOCORRO INDEPENDENT SCHOOL DISTRICT"),
    partnership("P334A250002", "WEBER STATE UNIVERSITY", "WEBERUEI0001", "UT", "GEAR UP PARTNERSHIP PROJECT"),
]


def write_sources(project):
    write_actions(project.raw_usaspending, PULL, GRANTS)
    ipeds = project.root / "data" / "raw" / "ipeds" / PULL
    write_csv(ipeds / "colleges_ipeds_directory.csv", DIRECTORY_COLUMNS, [
        directory_row("228796", "The University of Texas at El Paso", "TX", ueis=("UTEPUEI00001",)),
        directory_row("230038", "Weber State University", "UT", ueis=("WEBERUEI0001",)),
    ])
    write_csv(ipeds / "colleges_ipeds_fall-enrollment-race_2024.csv", ENROLLMENT_COLUMNS, [])
    write_csv(project.root / "data" / "raw" / "ccd" / PULL / LEA_CSV, LEA_COLUMNS, [
        lea_row("4840860", "Socorro Independent School District", "TX"),
        lea_row("4900630", "Ogden City School District", "UT"),
    ])


def test_a_partnership_links_to_the_district_it_names_never_the_college(project):
    write_sources(project)

    project.topo("run", "--as-of", PULL)

    rows = {r["FAIN"]: r for r in project.read_csv(f"target_list_{PULL}.csv")}
    got = {
        fain: (r["Host institution"], r["Host ID"], r["Host confidence"], r["Case label"])
        for fain, r in rows.items()
    }
    assert got == {
        "P334A250001": ("Socorro Independent School District", "LEAID 4840860", "matched", "district_named_in_desc"),
        "P334A250002": ("", "", "lower-confidence: no single Host", "gearup_partnership_no_district_named"),
    }
    candidates = pl.read_parquet(project.root / "data" / "joined" / "host_link_candidates.parquet")
    assert candidates.select("fain", "host_kind", "host_id", "signals").rows() == [
        ("P334A250001", "LEAID", "4840860", "desc"),
    ]


def test_ccd_clean_is_logged_with_named_drops_and_its_raw_file_reaches_the_sidecar(project):
    write_sources(project)
    write_csv(project.root / "data" / "raw" / "ccd" / PULL / LEA_CSV, LEA_COLUMNS, [
        lea_row("4840860", "Socorro ISD", "TX", year=2014),                   # before directory_from_year
        lea_row("4840860", "Socorro Independent School District", "TX"),
        lea_row("2500001", "Some Supervisory Union", "MA", agency_type=3),    # not a district agency type
    ])

    project.topo("run", "--as-of", PULL)

    logged = {(r["layer"], r["source"]): r for r in pl.read_parquet(project.output / "run_log.parquet").to_dicts()}
    clean = logged[("clean", "ccd_lea_directory")]
    assert (clean["rows_in"], clean["rows_out"]) == (3, 1)
    assert {d["reason"]: d["rows"] for d in clean["drops"]} == {
        "year_before_directory_from_year": 1, "agency_type_not_a_district": 1,
    }
    sidecar = json.loads((project.output / f"target_list_{PULL}.csv.provenance.json").read_text())
    assert [f["path"] for f in sidecar["raw_files"] if f["source"] == "ccd"] == [f"data/raw/ccd/{PULL}/{LEA_CSV}"]
