"""Seam 1: `topo run` links each Grant to its Host institution and keeps every outcome visible."""

from __future__ import annotations

import polars as pl
from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, enrollment_row, write_csv
from support.usaspending import action, write_actions

PULL = "2026-10-07"
IHE = "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"
NONPROFIT = "NONPROFIT WITH 501C3 IRS STATUS (OTHER THAN AN INSTITUTION OF HIGHER EDUCATION)"


def one_year(fain, recipient, uei, state, business_types, **kw):
    return action(fain, 1, "2025-07-01", 300000, ("2025-09-01", "2026-08-31"), action_type="A1",
                  recipient=recipient, uei=uei, state=state, business_types_description=business_types, **kw)


GRANTS = [
    one_year("P042A250001", "ROCKY MOUNTAIN COLLEGE", "RMCUEI000001", "MT", IHE),           # matched
    one_year("P042A250002", "REGENTS OF THE UNIVERSITY OF MINNESOTA", "UMNUEI000001", "MN", IHE),  # review
    one_year("P044A250003", "MASSACHUSETTS HIGHER EDUCATION ASSISTANCE CORPORATION", "MHEAC0000001", "MA",
             NONPROFIT),                                                                       # no single Host
    one_year("P334S250004", "MARYLAND STATE DEPARTMENT OF EDUCATION", "MSDE00000001", "MD", "STATE GOVERNMENT"),
    one_year("P042A250005", "OKLAHOMA COLLEGE", "CROSSSTATE01", "OK", IHE),                    # unmatched
]


def write_ipeds(project):
    folder = project.root / "data" / "raw" / "ipeds" / PULL
    write_csv(folder / "colleges_ipeds_directory.csv", DIRECTORY_COLUMNS, [
        directory_row("180595", "Rocky Mountain College", "MT", ueis=("RMCUEI000001",)),
        directory_row("174066", "University of Minnesota-Twin Cities", "MN", ueis=("UMNUEI000001",)),
        directory_row("174233", "University of Minnesota-Duluth", "MN", ueis=("UMNUEI000001",)),
        directory_row("228778", "The University of Texas at Austin", "TX", ueis=("CROSSSTATE01",)),
    ])
    write_csv(folder / "colleges_ipeds_fall-enrollment-race_2024.csv", ENROLLMENT_COLUMNS,
              [enrollment_row("180595", 2024, 900)])


def by_fain(rows):
    return {r["FAIN"]: r for r in rows}


def test_target_list_shows_host_case_label_and_confidence_next_to_the_recipient(project):
    write_actions(project.raw_usaspending, PULL, GRANTS)
    write_ipeds(project)

    project.topo("run", "--as-of", PULL)

    rows = project.read_csv(f"target_list_{PULL}.csv")
    columns = list(rows[0])
    assert columns[:6] == ["Recipient", "Recipient UEI", "Host institution", "Host ID", "Host confidence", "Case label"]
    got = {
        fain: (r["Host institution"], r["Host ID"], r["Host confidence"], r["Case label"])
        for fain, r in by_fain(rows).items()
    }
    assert got == {
        "P042A250001": ("Rocky Mountain College", "UNITID 180595", "matched", "uei_confirmed"),
        "P042A250002": ("", "", "in review", "system_campus_not_stated"),
        "P044A250003": ("", "", "lower-confidence: no single Host", "nonprofit_no_site_named"),
        "P334S250004": ("", "", "lower-confidence: no single Host", "gearup_state"),
        "P042A250005": ("", "", "unmatched", "no_candidate_ihe"),
    }
    rocky = by_fain(rows)["P042A250001"]
    assert (rocky["Recipient"], rocky["Recipient UEI"]) == ("ROCKY MOUNTAIN COLLEGE", "RMCUEI000001")


def test_review_candidates_and_their_signals_are_kept_in_the_joined_layer(project):
    write_actions(project.raw_usaspending, PULL, GRANTS)
    write_ipeds(project)

    project.topo("run", "--as-of", PULL)

    joined = project.root / "data" / "joined"
    links = pl.read_parquet(joined / "host_links.parquet")
    assert links.height == len(GRANTS)
    candidates = pl.read_parquet(joined / "host_link_candidates.parquet")
    assert candidates.filter(pl.col("fain") == "P042A250002").select("host_id", "signals").sort("host_id").rows() == [
        ("174066", "uei"), ("174233", "uei"),
    ]
    assert candidates.filter(pl.col("fain") == "P042A250005").height == 0


def test_without_an_ipeds_pull_every_grant_stays_on_the_target_list(project):
    write_actions(project.raw_usaspending, PULL, GRANTS)

    project.topo("run", "--as-of", PULL)

    rows = by_fain(project.read_csv(f"target_list_{PULL}.csv"))
    assert len(rows) == len(GRANTS)
    assert rows["P042A250001"]["Host confidence"] == "unmatched"
    assert rows["P334S250004"]["Case label"] == "gearup_state"
