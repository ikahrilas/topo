"""Seam 1: run guards and provenance (ADR 0003) through the `topo` command line.

The manifest row written by `pull`, provenance sidecars, the run log, the dirty-tree
guard, the row-count guard and API keys from git-ignored environment variables.
"""

from __future__ import annotations

import csv
import datetime as dt
import functools
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import polars as pl
import pytest
from support.usaspending import action, write_actions

from topo.sources import usaspending

REPO_ROOT = Path(__file__).resolve().parents[1]
PULL = "2026-10-07"
ARCHIVE = b"fake archive bytes"


def read_manifest(project) -> list[dict[str, str]]:
    with (project.root / "data/raw/manifest.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def fake_usaspending_http(monkeypatch, project):
    """`topo pull usaspending` without the network: one Full archive for FY2027."""
    project.set_config("pull_from_fy = 2010", "pull_from_fy = 2027")

    def post_json(url, body):
        name = f"FY{body['fiscal_year']}_091_Assistance_Full_20261006.zip"
        return {"monthly_files": [{"file_name": name, "url": "https://files.example/" + name}]}

    def download(url, dest: Path):
        dest.write_bytes(ARCHIVE)

    monkeypatch.setattr(
        usaspending, "pull", functools.partial(usaspending.pull, post_json=post_json, download=download)
    )


# ------------------------------------------------------------------ manifest


def test_pull_appends_its_own_manifest_row_and_keeps_the_ed_grantee_list_rows(project, monkeypatch):
    committed = REPO_ROOT / "data/raw/manifest.csv"
    (project.root / "data/raw").mkdir(parents=True)
    shutil.copy(committed, project.root / "data/raw/manifest.csv")
    before = read_manifest(project)
    fake_usaspending_http(monkeypatch, project)

    project.topo("pull", "usaspending", "--pull-date", PULL)

    after = read_manifest(project)
    assert after[: len(before)] == before  # existing rows untouched
    assert {r["source"] for r in before} == {"ed_grantee_lists"}
    [row] = after[len(before):]
    assert row["source"] == "usaspending"
    assert row["request"].startswith("POST https://api.usaspending.gov/api/v2/bulk_download/list_monthly_files/")
    assert '"fiscal_year": 2027' in row["request"]
    assert row["file_url"] == "https://files.example/FY2027_091_Assistance_Full_20261006.zip"
    assert row["pull_date"] == PULL
    assert row["bytes"] == str(len(ARCHIVE))
    assert row["sha256"] == hashlib.sha256(ARCHIVE).hexdigest()
    assert "USAspending.gov" in row["licence_citation"]
    assert row["stored_path"] == f"data/raw/usaspending/{PULL}/FY2027_091_Assistance_Full_20261006.zip"
    assert row["status"] == "ok"


def test_the_committed_manifest_rows_are_valid(project):
    from topo.manifest import read_manifest as read_validated

    rows = read_validated(REPO_ROOT / "data/raw/manifest.csv")

    ed = rows.filter(rows["source"] == "ed_grantee_lists")
    assert ed.height == rows.height > 0
    assert all(ed["licence_citation"].is_not_null())
    assert ed.filter(ed["status"] == "missing").height == 11  # the known list gaps (#16)


def test_pull_creates_the_manifest_when_there_is_none(project, monkeypatch):
    fake_usaspending_http(monkeypatch, project)

    project.topo("pull", "usaspending", "--pull-date", PULL)

    [row] = read_manifest(project)
    assert row["source"] == "usaspending" and row["sha256"] == hashlib.sha256(ARCHIVE).hexdigest()


# ------------------------------------------------- dirty tree and sidecars


def git(project, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=topo-test", "-c", "user.email=topo@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=project.root, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def committed_project(project):
    """Make the project a clean git checkout: config.toml and the repo .gitignore committed."""
    shutil.copy(REPO_ROOT / ".gitignore", project.root / ".gitignore")
    git(project, "init", "-q")
    git(project, "add", "config.toml", ".gitignore")
    git(project, "commit", "-q", "-m", "fixture")
    return git(project, "rev-parse", "HEAD")


def grant_rows(fain: str, start_fy: int, years: int) -> list[dict]:
    """One action per year: A1 in May of start_fy, B1s after; Sept-Aug Budget periods."""
    return [
        action(fain, i + 1, f"{start_fy + i}-05-15", 100, (f"{start_fy + i}-09-01", f"{start_fy + i + 1}-08-31"),
               action_type="A1" if i == 0 else "B1")
        for i in range(years)
    ]


def one_grant(project):
    write_actions(project.raw_usaspending, PULL, [
        action("P047A220001", 1, "2022-05-15", 100, ("2022-09-01", "2023-08-31"), action_type="A1"),
        action("P047A220001", 2, "2023-05-15", 100, ("2023-09-01", "2024-08-31")),
    ])


def test_each_output_gets_a_provenance_sidecar(project):
    commit = committed_project(project)
    one_grant(project)

    project.topo("run", "--as-of", "2026-09-30")

    sidecar = json.loads((project.output / f"target_list_{PULL}.csv.provenance.json").read_text())
    assert sidecar["output"] == f"target_list_{PULL}.csv"
    assert sidecar["commit"] == commit
    assert sidecar["dirty"] is False
    assert sidecar["as_of"] == "2026-09-30"
    assert sidecar["pull_date"] == PULL
    assert sidecar["config_sha256"] == hashlib.sha256(project.config.read_bytes()).hexdigest()
    assert len(sidecar["run_id"]) == 32
    raw = sorted(project.raw_usaspending.joinpath(PULL).iterdir())
    assert sidecar["raw_files"] == [
        {"source": "usaspending", "path": f"data/raw/usaspending/{PULL}/{p.name}",
         "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
        for p in raw
    ]


def test_a_rerun_gets_its_own_sidecar_and_run_id(project):
    committed_project(project)
    one_grant(project)

    project.topo("run", "--as-of", PULL)
    project.topo("run", "--as-of", PULL)

    first = json.loads((project.output / f"target_list_{PULL}.csv.provenance.json").read_text())
    second = json.loads((project.output / f"target_list_{PULL}_v2.csv.provenance.json").read_text())
    assert second["output"] == f"target_list_{PULL}_v2.csv"
    assert first["run_id"] != second["run_id"]


def test_a_dirty_tree_fails_the_run_unless_allow_dirty_is_passed(project):
    commit = committed_project(project)
    one_grant(project)
    project.set_config("start_fy = 2021", "start_fy = 2022")  # uncommitted change

    result = project.topo("run", "--as-of", PULL, expect_exit=2)

    assert "dirty" in result.output and "--allow-dirty" in result.output
    assert not project.output.exists()

    project.topo("run", "--as-of", PULL, "--allow-dirty")

    sidecar = json.loads((project.output / f"target_list_{PULL}.csv.provenance.json").read_text())
    assert sidecar["dirty"] is True and sidecar["commit"] == commit


def test_an_untracked_file_makes_the_tree_dirty(project):
    committed_project(project)
    one_grant(project)
    (project.root / "data/curated").mkdir(parents=True)
    (project.root / "data/curated/overrides.csv").write_text("fain,host\n")

    project.topo("clean", "usaspending", expect_exit=2)
    project.topo("clean", "usaspending", "--allow-dirty")


def test_outside_a_git_checkout_the_run_warns_and_records_no_commit(project):
    one_grant(project)

    result = project.topo("run", "--as-of", PULL)

    assert "Warning: not a git checkout" in result.output
    sidecar = json.loads((project.output / f"target_list_{PULL}.csv.provenance.json").read_text())
    assert sidecar["commit"] is None and sidecar["dirty"] is None


# ------------------------------------------------- run log and row counts


def run_log(project) -> list[dict]:
    return pl.read_parquet(project.output / "run_log.parquet").to_dicts()


def drops(row: dict) -> dict[str, int]:
    return {d["reason"]: d["rows"] for d in row["drops"]}


def test_every_layer_appends_rows_in_rows_out_and_named_drops_to_the_run_log(project):
    write_actions(project.raw_usaspending, PULL, [
        *grant_rows("P047A220001", 2022, 3),                                      # in the universe
        *grant_rows("P047A150002", 2015, 2),                                      # ended before FY2021
        action("P047X220003", 1, "2022-05-15", 100, ("2022-09-01", "2023-08-31")),  # no Program has prefix P047X
        action("P103A220004", 1, "2022-05-15", 100, ("2022-09-01", "2023-08-31"), listing="84.103"),
    ])

    project.topo("run", "--as-of", PULL)

    logged = {(r["layer"], r["source"]): r for r in run_log(project)}
    clean, join = logged[("clean", "usaspending")], logged[("join", "grant_universe")]
    funding, report = logged[("join", "grant_funding_status")], logged[("report", "target_list")]
    assert len({r["run_id"] for r in logged.values()}) == 1
    assert (clean["layer"], clean["source"]) == ("clean", "usaspending")
    assert (clean["rows_in"], clean["rows_out"]) == (7, 6)
    assert drops(clean) == {"not_a_trio_gear_up_listing": 1}
    assert clean["pull_date"] == dt.date(2026, 10, 7) and len(clean["input_hash"]) == 64

    assert (join["layer"], join["source"]) == ("join", "grant_universe")
    assert (join["rows_in"], join["rows_out"]) == (6, 3)
    assert drops(join) == {"fain_prefix_names_no_program": 1, "grant_outside_reporting_window": 2}
    assert join["pull_date"] == dt.date(2026, 10, 7) and len(join["input_hash"]) == 64

    assert (funding["layer"], funding["source"]) == ("join", "grant_funding_status")
    assert (funding["rows_in"], funding["rows_out"], drops(funding)) == (1, 1, {})

    assert (report["layer"], report["source"]) == ("report", "target_list")
    assert (report["rows_in"], report["rows_out"], drops(report)) == (1, 1, {})


def test_the_run_log_is_append_only(project):
    one_grant(project)

    project.topo("run", "--as-of", PULL)
    first = run_log(project)
    project.topo("run", "--as-of", PULL)
    second = run_log(project)

    n = len(first)
    assert n >= 4 and second[:n] == first and len(second) == 2 * n
    assert second[n]["run_id"] != first[0]["run_id"]


def test_a_row_count_mismatch_between_layers_stops_the_run(project):
    one_grant(project)
    project.topo("clean", "usaspending")
    cleaned = project.root / "data/cleaned/usaspending_actions.parquet"
    pl.read_parquet(cleaned).head(1).write_parquet(cleaned)  # one row lost between clean and join

    result = project.topo("join", "--as-of", PULL, expect_exit=2)

    assert "row-count mismatch: join read 1 usaspending rows but clean wrote 2" in result.output
    assert not (project.root / "data/joined/grants.parquet").exists()


def test_other_problems_only_warn(project):
    write_actions(project.raw_usaspending, PULL, [
        *grant_rows("P047A220001", 2022, 3),
        action("P047X220003", 1, "2022-05-15", 100, ("2022-09-01", "2023-08-31")),
    ])

    result = project.topo("run", "--as-of", PULL)

    assert "Warning: 1 actions in grant_universe_exceptions (fain_prefix_names_no_program)" in result.output
    assert len(project.read_csv(f"target_list_{PULL}.csv")) == 1


def test_ipeds_clean_is_logged_and_its_raw_files_reach_the_sidecar(project):
    from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, enrollment_row, write_csv

    one_grant(project)
    folder = project.root / "data/raw/ipeds" / PULL
    write_csv(folder / "colleges_ipeds_directory.csv", DIRECTORY_COLUMNS, [
        directory_row("120971", "West Hills College Lemoore", "CA", year=2014),  # before directory_from_year
        directory_row("120971", "West Hills College Lemoore", "CA", year=2016),
        directory_row("190035", "CUNY System Office", "NY", sector=0),
    ])
    write_csv(folder / "colleges_ipeds_fall-enrollment-race_2024.csv", ENROLLMENT_COLUMNS, [
        enrollment_row("120971", 2024, 3500),
        enrollment_row("120971", 2024, 2000, sex=1),  # a breakdown, not the total
    ])

    project.topo("run", "--as-of", PULL)

    logged = {(r["layer"], r["source"]): r for r in run_log(project)}
    directory, enrollment = logged[("clean", "ipeds_directory")], logged[("clean", "ipeds_enrollment")]
    assert (directory["rows_in"], directory["rows_out"], drops(directory)) == (3, 2, {"year_before_directory_from_year": 1})
    assert (enrollment["rows_in"], enrollment["rows_out"], drops(enrollment)) == (2, 1, {"not_a_total_enrollment_row": 1})
    sidecar = json.loads((project.output / f"target_list_{PULL}.csv.provenance.json").read_text())
    assert {f["source"] for f in sidecar["raw_files"]} == {"ipeds", "usaspending"}
    assert sorted(f["path"] for f in sidecar["raw_files"] if f["source"] == "ipeds") == [
        f"data/raw/ipeds/{PULL}/colleges_ipeds_directory.csv",
        f"data/raw/ipeds/{PULL}/colleges_ipeds_fall-enrollment-race_2024.csv",
    ]


# ----------------------------------------------------------------- API keys


def test_the_census_api_key_is_read_from_an_environment_variable(project, monkeypatch):
    from topo.api_keys import api_key
    from topo.config import load_config

    monkeypatch.setenv("CENSUS_API_KEY", "key-from-env")

    assert api_key(load_config(project.config), "census") == "key-from-env"


def test_the_census_api_key_can_come_from_a_git_ignored_dot_env_file(project, monkeypatch):
    from topo.api_keys import api_key
    from topo.config import load_config

    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    (project.root / ".env").write_text("# local secrets\nCENSUS_API_KEY=key-from-dot-env\n")

    assert api_key(load_config(project.config), "census") == "key-from-dot-env"
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT)
    assert ignored.returncode == 0


def test_a_missing_or_unknown_api_key_is_a_structural_break(project, monkeypatch):
    from topo.api_keys import api_key
    from topo.config import load_config
    from topo.guards import StructuralBreak

    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    config = load_config(project.config)

    with pytest.raises(StructuralBreak, match="CENSUS_API_KEY"):
        api_key(config, "census")
    with pytest.raises(StructuralBreak, match="only the Census"):
        api_key(config, "usaspending")
    assert "key-from" not in project.config.read_text()


def test_ed_grantee_list_clean_and_join_are_logged_and_their_files_reach_the_sidecar(project):
    from support.ed_lists import file_list, pdf_bytes, trio_pdf_lines, write_manifest

    one_grant(project)  # P047A220001
    lists = project.root / "data/raw/ed_grantee_lists"
    write_manifest(lists, [file_list(lists, "ub_84047A", "2024", "ub.pdf", pdf_bytes(trio_pdf_lines(2024, "Upward Bound(UB)", [
        ("P047A220001", "Example College/ Main", "AK", 60, 300000),   # attaches to a Grant-year
        ("P047A229999", "Not In USAspending/ Main", "AL", 10, 1000),  # ED-list-only FAIN
    ])))])

    project.topo("run", "--as-of", PULL)

    logged = {(r["layer"], r["source"]): r for r in run_log(project)}
    clean = logged[("clean", "ed_trio_list_rows")]
    assert (clean["rows_in"], clean["rows_out"], drops(clean)) == (2, 2, {})
    join = logged[("join", "grant_year_ed_attributes")]
    assert (join["rows_in"], join["rows_out"]) == (2, 1)
    assert drops(join) == {"ed_list_fain_not_in_usaspending": 1}
    sidecar = json.loads((project.output / f"target_list_{PULL}.csv.provenance.json").read_text())
    assert "data/raw/ed_grantee_lists/ub_84047A__FY2024__ub.pdf" in {f["path"] for f in sidecar["raw_files"]}
