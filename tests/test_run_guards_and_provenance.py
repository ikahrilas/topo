"""Seam 1: run guards and provenance (ADR 0003) through the `topo` command line.

The manifest row written by `pull`, provenance sidecars, the run log, the dirty-tree
guard, the row-count guard and API keys from git-ignored environment variables.
"""

from __future__ import annotations

import csv
import functools
import hashlib
import json
import shutil
from pathlib import Path

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
    project.set_config("pull_from_fy = 2015", "pull_from_fy = 2027")

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
