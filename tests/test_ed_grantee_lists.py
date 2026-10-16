"""ED grantee lists (#34): hand-filed, read from the checksummed manifest, never fetched."""

from __future__ import annotations

import socket
import urllib.request

import polars as pl
import pytest
from support.ed_lists import (
    file_list,
    gearup_html_bytes,
    known_gap,
    pdf_bytes,
    trio_pdf_lines,
    trio_xlsx_bytes,
    write_manifest,
)

UB_FY2024 = [
    ("P047A221553", "University of Alaska/ Anchorage", "AK", 60, 309505),
    ("P047A220187", "Alabama State University/ Montgomery", "AL", 67, 362438),
]
SSS_FY2023 = [
    ("P042A201384", "University of Alaska/ Anchorage", "AK", 160, 282500, "Regular"),
    ("P042A200923", "University of Alaska/ Fairbanks", "AK", 140, 272364, "STEM"),
]


@pytest.fixture
def no_network(monkeypatch):
    """Any attempt to reach ed.gov (or anything else) fails the test."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"network access attempted: {args!r}")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def raw_dir(project):
    return project.root / "data" / "raw" / "ed_grantee_lists"


def cleaned(project, name):
    return pl.read_parquet(project.root / "data" / "cleaned" / f"{name}.parquet")


def test_clean_reads_only_files_in_the_manifest_and_makes_no_request(project, tmp_path, no_network):
    lists = raw_dir(project)
    write_manifest(lists, [
        file_list(lists, "ub_84047A", "2024", "fy-2024-ub-awards.pdf",
                  pdf_bytes(trio_pdf_lines(2024, "Upward Bound(UB)", UB_FY2024))),
        file_list(lists, "sss_84042A", "2023", "sss-final2023xlsx.xlsx",
                  trio_xlsx_bytes(2023, "Student Support Services(SSS)", SSS_FY2023, tmp_path)),
    ])
    # A list dropped into the folder but never entered in the manifest is not read.
    (lists / "ts_84044__FY2023__stray.xlsx").write_bytes(
        trio_xlsx_bytes(2023, "Talent Search(TS)", [("P044A210918", "Stray College", "AK", 500, 1)], tmp_path)
    )

    project.topo("clean", "ed_grantee_lists")

    rows = cleaned(project, "ed_trio_list_rows").sort("fiscal_year", "fain")
    assert rows.select("fain", "fiscal_year", "program", "state", "participants").rows() == [
        ("P042A200923", 2023, "Student Support Services", "AK", 140),
        ("P042A201384", 2023, "Student Support Services", "AK", 160),
        ("P047A220187", 2024, "Upward Bound", "AL", 67),
        ("P047A221553", 2024, "Upward Bound", "AK", 60),
    ]
