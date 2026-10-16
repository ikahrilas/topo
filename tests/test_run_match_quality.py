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

import hashlib
import shutil
from pathlib import Path

from support.curated import key_row, override_row, write_answer_key, write_overrides, write_tuning_set
from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, enrollment_row, write_csv
from support.markdown import table
from support.usaspending import action, write_actions

PULL = "2026-10-07"
REPORT = f"match_quality_{PULL}.md"
REPO_ROOT = Path(__file__).resolve().parents[1]
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


def test_the_shipped_curated_files_pass_their_schema_checks(project):
    setup(project)
    shutil.copytree(REPO_ROOT / "data" / "curated", project.root / "data" / "curated")

    project.topo("run", "--as-of", PULL)

    assert {r["Gating"] for r in accuracy(project).values()} == {"unverified"}


def gating_key():
    """uei_confirmed: 10 checks, one wrong (90%). nonprofit_no_site_named: 10 checks, all right. gearup_state: 1."""
    return [
        *(key_row(fain, f"UNITID {unitid(i)}") for i, fain in enumerate(COLLEGE_FAINS[:9], start=1)),
        key_row(COLLEGE_FAINS[9], "UNITID 999999", note="the real Host is a branch campus"),
        *(key_row(fain, "no single Host") for fain in NONPROFIT_FAINS),
        key_row("P334S250021", "no single Host"),
    ]


def test_fixture_key_auto_accepts_demotes_and_leaves_unverified(project):
    setup(project)
    write_answer_key(project.root, gating_key())

    project.topo("run", "--as-of", PULL)

    labels = accuracy(project)
    got = {k: (r["Checks"], r["Correct"], r["Accuracy"], r["Gating"]) for k, r in labels.items()}
    assert got["uei_confirmed"] == ("10", "9", "90.0%", "demoted to review")
    assert got["nonprofit_no_site_named"] == ("10", "10", "100.0%", "auto-accepted")
    assert got["gearup_state"] == ("1", "1", "100.0%", "unverified")
    assert got["system_campus_not_stated"][3] == "unverified"

    targets = by(project.read_csv(f"target_list_{PULL}.csv"), "FAIN")
    college = targets["P042A250001"]
    assert (college["Host confidence"], college["Case label"], college["Host ID"]) == (
        "in review", "uei_confirmed", f"UNITID {unitid(1)}",
    )
    assert targets["P044A250011"]["Host confidence"] == "lower-confidence: no single Host"
    assert targets["P334S250021"]["Host confidence"] == "lower-confidence: no single Host"


def test_gating_thresholds_come_from_config(project):
    setup(project)
    write_answer_key(project.root, gating_key())
    project.set_config("auto_accept_accuracy = 0.95", "auto_accept_accuracy = 0.90")
    project.set_config("auto_accept_min_checks = 10", "auto_accept_min_checks = 1")

    project.topo("run", "--as-of", PULL)

    labels = accuracy(project)
    assert labels["uei_confirmed"]["Gating"] == "auto-accepted"
    assert labels["gearup_state"]["Gating"] == "auto-accepted"
    assert by(project.read_csv(f"target_list_{PULL}.csv"), "FAIN")["P042A250001"]["Host confidence"] == "matched"


def test_the_tuning_set_is_never_scored_for_gating(project):
    setup(project)
    write_answer_key(project.root, [key_row(fain, "no single Host") for fain in NONPROFIT_FAINS])
    # Every college in the tuning set says the rule is wrong; gating must not see it.
    write_tuning_set(project.root, [key_row(fain, "UNITID 999999") for fain in COLLEGE_FAINS])

    project.topo("run", "--as-of", PULL)

    labels = accuracy(project)
    assert (labels["uei_confirmed"]["Checks"], labels["uei_confirmed"]["Gating"]) == ("0", "unverified")
    assert labels["nonprofit_no_site_named"]["Gating"] == "auto-accepted"


def test_a_fain_in_both_the_answer_key_and_the_tuning_set_stops_the_run(project):
    setup(project)
    write_answer_key(project.root, [key_row("P044A250011", "no single Host")])
    write_tuning_set(project.root, [key_row("P044A250011", "no single Host")])

    result = project.topo("run", "--as-of", PULL, expect_exit=2)

    assert "both the frozen answer key and the tuning set" in result.output
    assert "P044A250011" in result.output


def test_a_pinned_answer_key_that_changed_stops_the_run(project):
    setup(project)
    write_answer_key(project.root, gating_key())
    project.set_config('answer_key_sha256 = ""', f'answer_key_sha256 = "{"0" * 64}"')

    result = project.topo("run", "--as-of", PULL, expect_exit=2)

    assert "frozen answer key" in result.output


def test_overrides_win_after_the_rules_and_survive_reruns(project):
    setup(project)
    write_answer_key(project.root, gating_key())  # demotes uei_confirmed to review
    write_overrides(project.root, [
        override_row("P042A250022", "UNITID 174066", date="2026-09-01", note="first look"),
        override_row("P042A250022", "UNITID 174233", date="2026-10-01", note="desc names Duluth"),
        override_row("P042A250001", f"UNITID {unitid(1)}", note="confirmed by phone"),
        override_row("P044A250012", "no single Host"),
    ])

    project.topo("run", "--as-of", PULL)
    project.topo("run", "--as-of", PULL)  # a rerun applies the same overrides

    for name in (f"target_list_{PULL}.csv", f"target_list_{PULL}_v2.csv"):
        targets = by(project.read_csv(name), "FAIN")
        got = {f: (targets[f]["Host institution"], targets[f]["Host ID"], targets[f]["Host confidence"],
                   targets[f]["Case label"]) for f in ("P042A250022", "P042A250001", "P042A250023", "P042A250002")}
        assert got == {
            "P042A250022": ("University of Minnesota-Duluth", "UNITID 174233", "matched", "override"),
            "P042A250001": ("College Number 1", f"UNITID {unitid(1)}", "matched", "override"),
            "P042A250023": ("", "", "in review", "system_campus_not_stated"),  # unreviewed: stays review
            "P042A250002": ("College Number 2", f"UNITID {unitid(2)}", "in review", "uei_confirmed"),  # demoted
        }
        assert targets["P044A250012"]["Case label"] == "override"

    # Accuracy is measured on the rules' own decisions, never on overrides.
    assert accuracy(project, f"match_quality_{PULL}_v2.md")["uei_confirmed"]["Correct"] == "9"
    overrides = by(table((project.output / REPORT).read_text(), "Overrides"), "FAIN")
    assert overrides["P042A250022"]["Host"] == "UNITID 174233"
    assert overrides["P042A250022"]["Rule case label"] == "system_campus_not_stated"


def test_review_queue_lists_candidates_with_signals_by_dollars_and_succession_impact(project):
    setup(project, [
        *GRANTS,
        # A Minnesota Upward Bound Grant at the same dollars as the Wisconsin SSS one. The Wisconsin
        # Recipient holds two other SSS Grants (already reviewed), so its Host matters more to Successions.
        one_year("P047A250025", "REGENTS OF THE UNIVERSITY OF MINNESOTA", "UMNUEI000001", "MN", IHE, amount=200000),
        one_year("P042A200026", "UNIVERSITY OF WISCONSIN SYSTEM", "UWSUEI000001", "WI", IHE, amount=500000),
        one_year("P042A150027", "UNIVERSITY OF WISCONSIN SYSTEM", "UWSUEI000001", "WI", IHE, amount=500000),
    ])
    write_overrides(project.root, [
        override_row(fain, host) for fain, host in [
            ("P042A250001", f"UNITID {unitid(1)}"), ("P042A200026", "UNITID 240444"), ("P042A150027", "UNITID 240444"),
        ]
    ])

    project.topo("run", "--as-of", PULL)

    queue = project.read_csv(f"review_queue_{PULL}.csv")
    order = list(dict.fromkeys(r["FAIN"] for r in queue))
    assert order[:2] == ["P042A250022", "P042A250023"]  # $900k first; then $200k with Succession impact 2
    assert order == ["P042A250022", "P042A250023", "P047A250025"]
    # Reviewed (overridden) Grants such as P042A250001 and P042A200026 have left the queue.
    minnesota = [r for r in queue if r["FAIN"] == "P042A250022"]
    assert [(r["Candidate host ID"], r["Candidate host"], r["Signals"]) for r in minnesota] == [
        ("UNITID 174066", "University of Minnesota-Twin Cities", "uei"),
        ("UNITID 174233", "University of Minnesota-Duluth", "uei"),
    ]
    assert {(r["Priority"], r["Case label"], float(r["Dollars"])) for r in minnesota} == {
        ("1", "system_campus_not_stated", 900000.0),
    }
    wisconsin = next(r for r in queue if r["FAIN"] == "P042A250023")
    assert wisconsin["Succession impact"] == "2"


REPORT_GRANTS = [
    *GRANTS,
    # uei_only: the UEI points at College Number 1, the name matches nothing.
    one_year("P047A250030", "BOARD OF TRUSTEES MT TECH", "MTUEI0000001", "MT", IHE, amount=100000),
    # Awarded before UEIs, still active on the As-of date, no UEI on any action.
    action("P042A210031", 1, "2021-07-01", 50000, ("2021-09-01", "2022-08-31"), action_type="A1",
           recipient="NO UEI COLLEGE", uei="", state="MT", business_types_description=IHE),
    action("P042A210031", 2, "2026-07-01", 50000, ("2026-09-01", "2027-08-31"),
           recipient="NO UEI COLLEGE", uei="", state="MT", business_types_description=IHE),
    # Also pre-2022 with no UEI, but ended: not counted as still active.
    action("P042A200032", 1, "2020-07-01", 40000, ("2020-09-01", "2021-08-31"), action_type="A1",
           recipient="ENDED NO UEI COLLEGE", uei="", state="MT", business_types_description=IHE),
]


def test_match_quality_report_shows_linking_quality(project):
    setup(project, REPORT_GRANTS)

    project.topo("run", "--as-of", PULL)

    text = (project.output / REPORT).read_text()
    assert f"Pull date: {PULL}" in text
    split = {r["Outcome"]: (r["Grants"], r["Dollars"]) for r in table(text, "Outcome split")}
    assert split == {
        "matched": ("11", "$3,100,000"),
        "no_single_host": ("11", "$3,300,000"),
        "review": ("2", "$1,100,000"),
        "unmatched": ("3", "$400,000"),
    }
    assert table(text, "Outcome split")[0]["Share of Grants"] == "40.7%"

    assert [r["FAIN"] for r in table(text, "Review list")] == ["P042A250022", "P042A250023"]
    assert [r["FAIN"] for r in table(text, "Unmatched list")] == ["P042A200032", "P042A210031", "P042A250024"]

    no_uei_link = {(r["Recipient"], r["Recipient UEI"]) for r in table(text, "Recipients with no UEI link")}
    assert ("OKLAHOMA COLLEGE", "OKUEI0000001") in no_uei_link
    assert ("NO UEI COLLEGE", "none") in no_uei_link
    assert ("HELPING HANDS 11", "NPUEI0000011") in no_uei_link
    assert not {r for r in no_uei_link if r[0] in ("COLLEGE NUMBER 1", "REGENTS OF THE UNIVERSITY OF MINNESOTA")}
    assert len(no_uei_link) == 14

    assert table(text, "UEI error exposure") == [{"Case label": "uei_only", "Grants": "1", "Dollars": "$100,000"}]
    assert [r["FAIN"] for r in table(text, "Still-active pre-2022 Grants with no UEI")] == ["P042A210031"]

    programs = by(table(text, "By Program"), "Program")
    assert {k: programs["Student Support Services"][k] for k in ("matched", "review", "unmatched", "Grants")} == {
        "matched": "10", "review": "2", "unmatched": "3", "Grants": "15",
    }
    assert programs["Talent Search"]["no_single_host"] == "10"
    flags = by(table(text, "By Host-link flag"), "Flag")
    assert {f: (r["unmatched"], r["Grants"]) for f, r in flags.items()} == {
        "followed_ipeds_merge": ("0", "0"), "unit_as_of_start_year": ("0", "0"), "no_uei": ("2", "2"),
    }
    assert "+" not in "".join(accuracy(project))  # flags never split a Case label
    years = by(table(text, "By start year"), "Start FY")
    assert {y: r["Grants"] for y, r in years.items()} == {"2020": "1", "2021": "1", "2025": "25"}

    inputs = by(table(text, "Inputs"), "Input")
    assert inputs["config.toml"]["SHA-256"] == hashlib.sha256(project.config.read_bytes()).hexdigest()
    directory = f"data/raw/ipeds/{PULL}/colleges_ipeds_directory.csv"
    assert inputs[directory]["SHA-256"] == hashlib.sha256((project.root / directory).read_bytes()).hexdigest()
    assert any(path.startswith(f"data/raw/usaspending/{PULL}/") for path in inputs)
    for name in (REPORT, f"review_queue_{PULL}.csv"):
        assert (project.output / f"{name}.provenance.json").exists()


def test_a_malformed_answer_key_host_is_a_structural_break(project):
    setup(project)
    write_answer_key(project.root, [key_row("P044A250011", "Rocky Mountain College")])

    project.topo("run", "--as-of", PULL, expect_exit=2)
