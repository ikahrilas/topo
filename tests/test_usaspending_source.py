"""The USAspending source module: pull (with fake HTTP, never the network) and zipped raw files."""

from __future__ import annotations

import csv
import datetime as dt
import io
import subprocess
import sys
import urllib.error
import zipfile
from pathlib import Path

import pytest
from support.usaspending import ARCHIVE_COLUMNS, action, write_archive

from topo.config import load_config
from topo.sources import usaspending


def archive_zip(rows: list[dict]) -> bytes:
    """A zipped archive CSV, as files.usaspending.gov serves it."""
    tmp = io.BytesIO()
    with zipfile.ZipFile(tmp, "w") as zf:
        text = io.StringIO()
        writer = csv.DictWriter(text, fieldnames=ARCHIVE_COLUMNS, restval="")
        writer.writeheader()
        writer.writerows(rows)
        zf.writestr("FY2026_091_Assistance_Full_20261006_1.csv", text.getvalue())
    return tmp.getvalue()


def test_pull_fetches_full_archives_per_fiscal_year_into_the_pull_date_folder(project):
    project.set_config("pull_from_fy = 2010", "pull_from_fy = 2026")
    payload = archive_zip([action("P047A220001", 1, "2026-05-15", 5, ("2026-09-01", "2027-08-31"))])
    requests: list[dict] = []

    def post_json(url, body):
        requests.append(body)
        code = {80: "091", 18: "1601"}[body["agency"]]
        name = f"FY{body['fiscal_year']}_{code}_Assistance_"
        return {"monthly_files": [
            {"file_name": name + "Full_20261006.zip", "url": "https://files.example/" + name + "Full_20261006.zip"},
            {"file_name": name + "Delta_20261006.zip", "url": "https://files.example/" + name + "Delta_20261006.zip"},
        ]}

    def download(url, dest: Path):
        assert "_Full_" in url
        dest.write_bytes(payload)

    pulled = usaspending.pull(load_config(project.config), dt.date(2026, 10, 7), post_json=post_json, download=download)

    # Pull date 2026-10-07 is in FY2027, so FY2026 and FY2027 are fetched for ED (80) and DOL (18),
    # the agency DOL ETA runs some TRIO competitions under; delta files are not.
    assert [(r["agency"], r["fiscal_year"]) for r in requests] == [(80, 2026), (80, 2027), (18, 2026), (18, 2027)]
    assert [p.path.name for p in pulled] == [
        "FY2026_091_Assistance_Full_20261006.zip", "FY2027_091_Assistance_Full_20261006.zip",
        "FY2026_1601_Assistance_Full_20261006.zip", "FY2027_1601_Assistance_Full_20261006.zip",
    ]
    assert all(p.path.parent == project.raw_usaspending / "2026-10-07" for p in pulled)
    assert pulled[0].bytes == len(payload) and len(pulled[0].sha256) == 64
    assert pulled[0].pull_date == dt.date(2026, 10, 7) and "USAspending.gov" in pulled[0].licence_citation


def test_pull_retries_a_transient_server_error_instead_of_abandoning_the_pull(project):
    # Real pull, 2026-10-17: list_monthly_files answered HTTP 500 once, 40 minutes into the pull.
    project.set_config("pull_from_fy = 2010", "pull_from_fy = 2027")
    failures = {"list": 1, "download": 1}
    pauses: list[float] = []

    def post_json(url, body):
        if failures["list"]:
            failures["list"] -= 1
            raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)
        name = f"FY{body['fiscal_year']}_{body['agency']}_Assistance_Full_20261006.zip"
        return {"monthly_files": [{"file_name": name, "url": "https://files.example/" + name}]}

    def download(url, dest: Path):
        if failures["download"]:
            failures["download"] -= 1
            raise urllib.error.URLError("Remote end closed connection without response")
        dest.write_bytes(b"zip")

    pulled = usaspending.pull(
        load_config(project.config), dt.date(2026, 10, 7), post_json=post_json, download=download, pause=pauses.append
    )

    assert [p.path.name for p in pulled] == ["FY2027_80_Assistance_Full_20261006.zip", "FY2027_18_Assistance_Full_20261006.zip"]
    assert len(pauses) == 2 and all(p > 0 for p in pauses)


def test_pull_gives_up_on_a_client_error(project):
    project.set_config("pull_from_fy = 2010", "pull_from_fy = 2027")

    def post_json(url, body):
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        usaspending.pull(load_config(project.config), dt.date(2026, 10, 7), post_json=post_json,
                         download=lambda url, dest: None, pause=lambda s: None)


def test_clean_reads_zipped_archive_files(project):
    folder = project.raw_usaspending / "2026-10-07"
    folder.mkdir(parents=True)
    (folder / "FY2026_091_Assistance_Full_20261006.zip").write_bytes(
        archive_zip([action("P047A220001", 1, "2026-05-15", 5, ("2026-09-01", "2027-08-31"), action_type="A1")])
    )

    project.topo("clean", "usaspending")

    cleaned = usaspending.read_cleaned(load_config(project.config))
    assert cleaned["fain"].to_list() == ["P047A220001"]
    assert cleaned["raw_file"].to_list() == [
        "FY2026_091_Assistance_Full_20261006.zip:FY2026_091_Assistance_Full_20261006_1.csv"
    ]


def test_the_topo_command_is_installed_and_runs_end_to_end(project):
    write_archive(project.raw_usaspending, "2026-10-07", 2026, [
        action("P047A220001", 1, "2026-05-15", 5, ("2026-09-01", "2027-08-31"), action_type="A1"),
    ])
    topo = Path(sys.executable).parent / "topo"

    result = subprocess.run(
        [str(topo), "--config", str(project.config), "run", "--as-of", "2026-10-07"],
        capture_output=True, text=True, cwd=project.root,
    )

    assert result.returncode == 0, result.stderr
    assert (project.output / "target_list_2026-10-07.csv").exists()
