"""The USAspending source module: pull (with fake HTTP, never the network) and zipped raw files."""

from __future__ import annotations

import csv
import datetime as dt
import io
import subprocess
import sys
import zipfile
from pathlib import Path

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
        name = f"FY{body['fiscal_year']}_091_Assistance_"
        return {"monthly_files": [
            {"file_name": name + "Full_20261006.zip", "url": "https://files.example/" + name + "Full_20261006.zip"},
            {"file_name": name + "Delta_20261006.zip", "url": "https://files.example/" + name + "Delta_20261006.zip"},
        ]}

    def download(url, dest: Path):
        assert "_Full_" in url
        dest.write_bytes(payload)

    pulled = usaspending.pull(load_config(project.config), dt.date(2026, 10, 7), post_json=post_json, download=download)

    # Pull date 2026-10-07 is in FY2027, so FY2026 and FY2027 are fetched; delta files are not.
    assert [r["fiscal_year"] for r in requests] == [2026, 2027]
    assert all(r["agency"] == 80 for r in requests)
    assert [p.path.name for p in pulled] == ["FY2026_091_Assistance_Full_20261006.zip", "FY2027_091_Assistance_Full_20261006.zip"]
    assert all(p.path.parent == project.raw_usaspending / "2026-10-07" for p in pulled)
    assert pulled[0].bytes == len(payload) and len(pulled[0].sha256) == 64
    assert pulled[0].pull_date == dt.date(2026, 10, 7) and "USAspending.gov" in pulled[0].licence_citation


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
