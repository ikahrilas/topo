"""Seam 1: answer-key gating, overrides, the review queue and the match-quality report.

The fixture population, by the rule that decides each Grant:
    P042A2500xx (01-10)   uei_confirmed            matched, one Montana college each
    P044A2500xx (11-20)   nonprofit_no_site_named  no single Host
    P334S250021           gearup_state             no single Host
    P042A250022           system_campus_not_stated review (two Minnesota campuses share the UEI)
    P042A250023           system_campus_not_stated review (two Wisconsin campuses), less money
    P042A250024           no_candidate_ihe         unmatched (no Oklahoma college in IPEDS)
"""

from __future__ import annotations

from support.curated import key_row, write_answer_key
from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, enrollment_row, write_csv
from support.markdown import table
from support.usaspending import action, write_actions

PULL = "2026-10-07"
REPORT = f"match_quality_{PULL}.md"
IHE = "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"
NONPROFIT = "NONPROFIT WITH 501C3 IRS STATUS (OTHER THAN AN INSTITUTION OF HIGHER EDUCATION)"

COLLEGE_FAINS = [f"P042A2500{i:02d}" for i in range(1, 11)]
NONPROFIT_FAINS = [f"P044A2500{i:02d}" for i in range(11, 21)]


def one_year(fain, recipient, uei, state, business_types, amount=300000, **kw):
    return action(fain, 1, "2025-07-01", amount, ("2025-09-01", "2026-08-31"), action_type="A1",
                  recipient=recipient, uei=uei, state=state, business_types_description=business_types, **kw)


def unitid(i: int) -> str:
    return f"9000{i:02d}"


GRANTS = [
    *(one_year(fain, f"COLLEGE NUMBER {i}", f"MTUEI00000{i:02d}", "MT", IHE)
      for i, fain in enumerate(COLLEGE_FAINS, start=1)),
    *(one_year(fain, f"HELPING HANDS {i}", f"NPUEI00000{i:02d}", "MA", NONPROFIT)
      for i, fain in enumerate(NONPROFIT_FAINS, start=11)),
    one_year("P334S250021", "MARYLAND STATE DEPARTMENT OF EDUCATION", "MSDE00000001", "MD", "STATE GOVERNMENT"),
    one_year("P042A250022", "REGENTS OF THE UNIVERSITY OF MINNESOTA", "UMNUEI000001", "MN", IHE, amount=900000),
    one_year("P042A250023", "UNIVERSITY OF WISCONSIN SYSTEM", "UWSUEI000001", "WI", IHE, amount=200000),
    one_year("P042A250024", "OKLAHOMA COLLEGE", "OKUEI0000001", "OK", IHE),
]


def write_ipeds(project):
    folder = project.root / "data" / "raw" / "ipeds" / PULL
    write_csv(folder / "colleges_ipeds_directory.csv", DIRECTORY_COLUMNS, [
        *(directory_row(unitid(i), f"College Number {i}", "MT", ueis=(f"MTUEI00000{i:02d}",)) for i in range(1, 11)),
        directory_row("174066", "University of Minnesota-Twin Cities", "MN", ueis=("UMNUEI000001",)),
        directory_row("174233", "University of Minnesota-Duluth", "MN", ueis=("UMNUEI000001",)),
        directory_row("240444", "University of Wisconsin-Madison", "WI", ueis=("UWSUEI000001",)),
        directory_row("240453", "University of Wisconsin-Milwaukee", "WI", ueis=("UWSUEI000001",)),
    ])
    write_csv(folder / "colleges_ipeds_fall-enrollment-race_2024.csv", ENROLLMENT_COLUMNS,
              [enrollment_row(unitid(1), 2024, 900)])


def setup(project, grants=GRANTS):
    write_actions(project.raw_usaspending, PULL, grants)
    write_ipeds(project)


def by(rows, key):
    return {r[key]: r for r in rows}


def accuracy(project, name=REPORT):
    return by(table((project.output / name).read_text(), "Accuracy per Case label"), "Case label")


def test_with_no_answer_key_every_case_label_is_unverified(project):
    setup(project)

    project.topo("run", "--as-of", PULL)

    labels = accuracy(project)
    assert set(labels) == {
        "uei_confirmed", "nonprofit_no_site_named", "gearup_state", "system_campus_not_stated", "no_candidate_ihe",
    }
    assert {r["Gating"] for r in labels.values()} == {"unverified"}
    assert {r["Checks"] for r in labels.values()} == {"0"}
    assert labels["uei_confirmed"]["Links"] == "10"


def test_an_empty_answer_key_file_reports_every_case_label_unverified(project):
    setup(project)
    write_answer_key(project.root, [])

    project.topo("run", "--as-of", PULL)

    assert {r["Gating"] for r in accuracy(project).values()} == {"unverified"}
    targets = by(project.read_csv(f"target_list_{PULL}.csv"), "FAIN")
    assert targets["P042A250001"]["Host confidence"] == "matched"  # unverified labels keep the rule's outcome
