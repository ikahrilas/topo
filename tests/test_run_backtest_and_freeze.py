"""Seam 1: the FY2022 TRIO renewal-timing backtest and the FY2027 freeze, via the `topo` command line.

Fixtures put Upward Bound Cohorts in FY2017 and FY2022, Budget periods running
September to August, each funded the May before it starts. The deadline table
gives the FY2017 deadline (2017-01-31) and the actual FY2022 deadline
(2022-01-31), so the backtest's As-of date for Upward Bound is 12 months before
the FY2022 deadline: 2021-01-31. Only actions dated on or before it are seen.
"""

from __future__ import annotations

import csv
import shutil
import subprocess

import pytest
from conftest import REPO_ROOT
from support.markdown import prose, table
from support.usaspending import action, write_actions

PULL = "2026-10-07"
DEADLINES_HEADER = "program,competition_fy,application_deadline,citation,source_url,note\n"
UB_2017 = "Upward Bound,2017,2017-01-31,Applications for New Awards; Upward Bound (FY2017 NIA),,\n"
UB_2022 = "Upward Bound,2022,2022-01-31,Applications for New Awards; Upward Bound (86 FR 71477),,\n"
FROZEN = "data/curated/fy2027_predictions.csv"


def grant(fain, a1_year, funded_years, **who):
    """A1 in May of a1_year; Sept-Aug Budget periods, each funded in May before it starts."""
    return [
        action(fain, i + 1, f"{a1_year + i}-05-15", 300000, (f"{a1_year + i}-09-01", f"{a1_year + i + 1}-08-31"),
               action_type="A1" if i == 0 else "B1", **who)
        for i in range(funded_years)
    ]


def write_deadlines(project, *rows):
    curated = project.root / "data" / "curated"
    curated.mkdir(parents=True, exist_ok=True)
    (curated / "deadlines.csv").write_text(DEADLINES_HEADER + "".join(rows))


UB_2017_COHORT = [*grant("P047A170001", 2017, 5), *grant("P047A170002", 2017, 5)]
UB_2022_COHORT = [*grant("P047A220001", 2022, 5), *grant("P047A220002", 2022, 5)]


def match_quality(project):
    return (project.output / f"match_quality_{PULL}.md").read_text()


def test_the_backtest_scores_timing_error_recall_and_precision_against_the_bar(project):
    write_deadlines(project, UB_2017, UB_2022)
    write_actions(project.raw_usaspending, PULL, [*UB_2017_COHORT, *UB_2022_COHORT])

    project.topo("run", "--as-of", PULL)

    rows = table(match_quality(project), "Renewal-timing backtest (FY2022)")
    assert rows == [{
        "Program": "Upward Bound", "Backtest As-of date": "2021-01-31", "Prior Cohort": "FY2017",
        "Predicted due date": "2022-01-31", "Evidence tier": "inferred", "Actual deadline": "2022-01-31",
        "Timing error (months)": "0", "Grants": "2", "Re-competed": "2", "Flagged": "2",
        "Flagged and re-competed": "2", "Recall": "100.0%", "Precision": "100.0%", "Result": "pass",
        "Succession rate": "0 of 2",
    }]
    assert "95%" in prose(match_quality(project), "Renewal-timing backtest (FY2022)")


def test_a_flag_that_disagrees_with_what_happened_is_a_miss_and_is_listed(project):
    write_deadlines(project, UB_2017, UB_2022)
    write_actions(project.raw_usaspending, PULL, [
        *UB_2017_COHORT,
        *grant("P047A170003", 2017, 6),  # flagged, but a sixth Budget period (from 2022-09-01) was funded
        *grant("P047A170004", 2017, 3),  # unfunded on the backtest As-of: not flagged, yet it re-competed
        *UB_2022_COHORT,
    ])

    project.topo("run", "--as-of", PULL)

    report = match_quality(project)
    [ub] = table(report, "Renewal-timing backtest (FY2022)")
    assert (ub["Grants"], ub["Re-competed"], ub["Flagged"], ub["Flagged and re-competed"]) == ("4", "3", "3", "2")
    assert (ub["Recall"], ub["Precision"], ub["Result"]) == ("66.7%", "66.7%", "miss")
    misses = table(report, "Backtest misses")
    assert [(m["FAIN"], m["Latest readable status (backtest As-of)"], m["Flagged"], m["Re-competed"])
            for m in misses] == [
        ("P047A170003", "continued", "yes", "no"),
        ("P047A170004", "unfunded", "no", "yes"),
    ]


def test_the_backtest_sees_only_deadlines_passed_by_its_as_of_date(project):
    # With no FY2017 deadline, the FY2022 deadline (after the As-of date) must not leak into the prediction.
    write_deadlines(project, UB_2022)
    write_actions(project.raw_usaspending, PULL, [*UB_2017_COHORT, *UB_2022_COHORT])

    project.topo("run", "--as-of", PULL)

    [ub] = table(match_quality(project), "Renewal-timing backtest (FY2022)")
    assert (ub["Predicted due date"], ub["Timing error (months)"], ub["Flagged"]) == ("date unknown", "", "0")
    assert ub["Result"] == "miss"


def test_a_late_predicted_due_date_shows_its_timing_error(project):
    write_deadlines(project, "Upward Bound,2017,2017-04-30,FY2017 NIA,,\n", UB_2022)
    write_actions(project.raw_usaspending, PULL, [*UB_2017_COHORT, *UB_2022_COHORT])

    project.topo("run", "--as-of", PULL)

    [ub] = table(match_quality(project), "Renewal-timing backtest (FY2022)")
    assert (ub["Predicted due date"], ub["Timing error (months)"]) == ("2022-04-30", "3")


def test_a_program_with_a_competition_cohort_but_no_deadline_is_not_scored(project):
    write_deadlines(project, UB_2017, UB_2022)
    write_actions(project.raw_usaspending, PULL, [
        *UB_2017_COHORT, *UB_2022_COHORT, *grant("P217A170001", 2017, 5), *grant("P217A220001", 2022, 5),
    ])

    project.topo("run", "--as-of", PULL)

    rows = {r["Program"]: r for r in table(match_quality(project), "Renewal-timing backtest (FY2022)")}
    assert rows["McNair"]["Result"] == "not scored: no deadline for the competition in the deadline table"
    assert rows["Upward Bound"]["Result"] == "pass"


def read_rows(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def test_run_never_writes_the_frozen_predictions(project):
    write_deadlines(project, UB_2017, UB_2022)
    write_actions(project.raw_usaspending, PULL, [*UB_2017_COHORT, *UB_2022_COHORT])

    project.topo("run", "--as-of", PULL)

    assert not (project.root / FROZEN).exists()


def test_freeze_writes_the_fy2027_predictions_once_and_refuses_to_overwrite(project):
    write_deadlines(project, UB_2017, UB_2022)
    write_actions(project.raw_usaspending, PULL, [
        *UB_2017_COHORT, *grant("P047A220001", 2022, 5), *grant("P047A220002", 2022, 3),  # 002 unfunded
    ])
    project.topo("run", "--as-of", PULL)

    project.topo("freeze")

    frozen = project.root / FROZEN
    [ub] = read_rows(frozen)
    assert {k: ub[k] for k in ("program", "competition_fy", "cohort_fy", "predicted_due_date", "evidence_tier",
                               "timing", "flagged_fains", "as_of", "pull_date")} == {
        "program": "Upward Bound", "competition_fy": "2027", "cohort_fy": "2022",
        "predicted_due_date": "2027-01-31", "evidence_tier": "inferred", "timing": "predicted",
        "flagged_fains": "P047A220001", "as_of": PULL, "pull_date": PULL,
    }
    assert ub["rule_version"]
    assert "source_commit" in ub
    assert frozen.with_name(frozen.name + ".provenance.json").exists()

    before = frozen.read_bytes()
    result = project.topo("freeze", expect_exit=2)
    assert "already frozen" in result.output
    assert frozen.read_bytes() == before


def test_scoring_the_frozen_predictions_writes_a_new_file_and_leaves_the_frozen_one_alone(project):
    write_deadlines(project, UB_2017, UB_2022)
    write_actions(project.raw_usaspending, PULL, [*UB_2017_COHORT, *UB_2022_COHORT])
    project.topo("run", "--as-of", PULL)
    project.topo("freeze")
    frozen = project.root / FROZEN
    before = frozen.read_bytes()

    # A later pull: the FY2027 notice is out, and the new Cohort's FAINs have appeared.
    later = "2027-10-07"
    write_deadlines(project, UB_2017, UB_2022, "Upward Bound,2027,2027-02-28,FY2027 NIA,,\n")
    write_actions(project.raw_usaspending, later, [
        *UB_2017_COHORT, *UB_2022_COHORT,
        *grant("P047A270001", 2027, 1), *grant("P047A270002", 2027, 1),
    ])
    project.topo("run", "--as-of", later)
    project.topo("score-predictions")

    assert frozen.read_bytes() == before
    scored = project.root / f"data/curated/fy2027_predictions_scored_{later}.csv"
    [ub] = read_rows(scored)
    assert {k: ub[k] for k in ("program", "predicted_due_date", "actual_deadline", "timing_error_months",
                               "grants", "re_competed", "flagged", "recall", "precision", "result")} == {
        "program": "Upward Bound", "predicted_due_date": "2027-01-31", "actual_deadline": "2027-02-28",
        "timing_error_months": "-1", "grants": "2", "re_competed": "2", "flagged": "2",
        "recall": "1.0", "precision": "1.0", "result": "pass",
    }
    project.topo("score-predictions", expect_exit=2)  # a second scoring on the same As-of date never overwrites


def git(project, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=topo-test", "-c", "user.email=topo@example.invalid", "-c", "commit.gpgsign=false",
         *args],
        cwd=project.root, capture_output=True, text=True, check=True,
    )


def frozen_and_tagged(project):
    """A run, a freeze, then the freeze committed and tagged as the CLI tells the owner to."""
    write_deadlines(project, UB_2017, UB_2022)
    write_actions(project.raw_usaspending, PULL, [*UB_2017_COHORT, *UB_2022_COHORT])
    project.topo("run", "--as-of", PULL)
    project.topo("freeze")
    shutil.copy(REPO_ROOT / ".gitignore", project.root / ".gitignore")
    git(project, "init", "-q")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "freeze")
    git(project, "tag", "fy2027-predictions")


def test_scoring_warns_when_the_frozen_file_differs_from_its_tag(project):
    frozen_and_tagged(project)
    frozen = project.root / FROZEN
    frozen.write_text(frozen.read_text().replace("2027-01-31", "2027-03-31"))  # an edit after the freeze
    git(project, "commit", "-q", "-am", "edit the frozen predictions")

    result = project.topo("score-predictions")

    assert ("Warning: data/curated/fy2027_predictions.csv differs from the copy tagged fy2027-predictions"
            in result.output)


def test_scoring_an_untouched_tagged_freeze_gives_no_tag_warning(project):
    frozen_and_tagged(project)

    result = project.topo("score-predictions")

    assert "tagged" not in result.output


def test_scoring_without_a_frozen_file_stops(project):
    write_deadlines(project, UB_2017, UB_2022)
    write_actions(project.raw_usaspending, PULL, [*UB_2017_COHORT, *UB_2022_COHORT])
    project.topo("run", "--as-of", PULL)

    result = project.topo("score-predictions", expect_exit=2)

    assert "no frozen predictions" in result.output


def test_the_report_shows_the_observed_gap_table_per_program(project):
    write_deadlines(project, UB_2017, UB_2022)
    write_actions(project.raw_usaspending, PULL, [
        *grant("P047A120001", 2012, 5), *UB_2017_COHORT, *UB_2022_COHORT,
        *grant("P217A180001", 2018, 5), *grant("P217A220001", 2022, 5),
    ])

    project.topo("run", "--as-of", PULL)

    gaps = table(match_quality(project), "Observed gaps between Cohort starts")
    assert [(g["Program"], g["Cohort FY"], g["Observed gap (months)"], g["Renewal timing"]) for g in gaps] == [
        ("McNair", "FY2018", "", "timing not predicted"),
        ("McNair", "FY2022", "48", "timing not predicted"),
        ("Upward Bound", "FY2012", "", "predicted"),
        ("Upward Bound", "FY2017", "60", "predicted"),
        ("Upward Bound", "FY2022", "60", "predicted"),
    ]
