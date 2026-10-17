"""The USAspending source module: pull (with fake HTTP, never the network) and zipped raw files."""

from __future__ import annotations

import csv
import http.client
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


def test_a_rerun_pull_on_the_same_pull_date_keeps_the_archives_it_already_has(project):
    # Archive file names carry their build date, so a file already in the Pull date folder is that file.
    project.set_config("pull_from_fy = 2010", "pull_from_fy = 2027")
    folder = project.raw_usaspending / "2026-10-07"
    folder.mkdir(parents=True)
    (folder / "FY2027_80_Assistance_Full_20261006.zip").write_bytes(b"already here")
    (folder / "FY2027_18_Assistance_Full_20261006.zip.part").write_bytes(b"half a file")
    fetched: list[str] = []

    def post_json(url, body):
        name = f"FY{body['fiscal_year']}_{body['agency']}_Assistance_Full_20261006.zip"
        return {"monthly_files": [{"file_name": name, "url": "https://files.example/" + name}]}

    def download(url, dest: Path):
        fetched.append(url)
        dest.write_bytes(b"fresh")

    pulled = usaspending.pull(load_config(project.config), dt.date(2026, 10, 7), post_json=post_json, download=download)

    assert fetched == ["https://files.example/FY2027_18_Assistance_Full_20261006.zip"]
    assert [(p.path.name, p.bytes) for p in pulled] == [
        ("FY2027_80_Assistance_Full_20261006.zip", 12), ("FY2027_18_Assistance_Full_20261006.zip", 5),
    ]


def test_a_broken_transfer_leaves_no_archive(tmp_path):
    from topo.sources import raw as raw_tree

    def broken_urlopen(url, timeout):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                raise ConnectionResetError("dropped")

        return Response()

    dest = tmp_path / "FY2027_091_Assistance_Full_20261006.zip"
    with pytest.raises(ConnectionResetError):
        raw_tree.download("https://files.example/x.zip", dest, urlopen=broken_urlopen)
    assert not dest.exists()


def test_a_download_cut_short_of_its_content_length_is_refused_not_kept(tmp_path):
    # Real pull, 2026-10-17: files.usaspending.gov closed five archive transfers early with no error,
    # leaving truncated zips (e.g. FY2010 ED, 175 MB) that clean then failed to open.
    from topo.sources import raw as raw_tree

    def short_urlopen(url, timeout):
        class Response:
            headers = {"Content-Length": "10"}
            body = [b"PK\x03\x04", b""]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                return self.body.pop(0)

        return Response()

    dest = tmp_path / "FY2010_091_Assistance_Full_20261006.zip"
    with pytest.raises(http.client.IncompleteRead):
        raw_tree.download("https://files.example/x.zip", dest, urlopen=short_urlopen)
    assert not dest.exists()  # what arrived stays in the .part file, for a resumed attempt


def test_a_cut_download_resumes_from_its_part_file_with_a_range_request(tmp_path):
    # Real pull, 2026-10-17: files.usaspending.gov cut the 240 MB FY2010 ED archive at ~75-100 MB on
    # every attempt; starting over never finished. It answers Range requests (206).
    from topo.sources import raw as raw_tree

    whole = b"0123456789"
    ranges: list[str | None] = []

    def flaky_urlopen(request, timeout):
        start = int(request.get_header("Range", "bytes=0-")[6:-1])
        ranges.append(request.get_header("Range"))
        cut = start == 0  # the first transfer is cut after 4 bytes

        class Response:
            status = 206 if start else 200
            headers = {"Content-Length": str(len(whole) - start)}
            body = [whole[start:4], b""] if cut else [whole[start:], b""]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                return self.body.pop(0)

        return Response()

    dest = tmp_path / "FY2010_091_Assistance_Full_20261006.zip"
    download = lambda url, d: raw_tree.download(url, d, urlopen=flaky_urlopen)  # noqa: E731
    raw_tree.retrying(download, pause=lambda s: None)("https://files.example/x.zip", dest)

    assert ranges == [None, "bytes=4-"]
    assert dest.read_bytes() == whole and not (tmp_path / (dest.name + ".part")).exists()


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
