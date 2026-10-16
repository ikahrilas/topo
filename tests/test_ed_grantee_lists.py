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
from support.usaspending import action, write_actions

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


def ub_pdf(rows=UB_FY2024, **kw):
    return pdf_bytes(trio_pdf_lines(2024, "Upward Bound(UB)", rows, **kw))


def test_a_filed_list_that_fails_its_checksum_stops_the_run(project):
    lists = raw_dir(project)
    row = file_list(lists, "ub_84047A", "2024", "fy-2024-ub-awards.pdf", ub_pdf())
    write_manifest(lists, [row])
    stored = lists / row["stored_path"].rsplit("/", 1)[1]
    stored.write_bytes(stored.read_bytes().replace(b"309,505", b"309,506"))

    result = project.topo("clean", "ed_grantee_lists", expect_exit=2)

    assert "checksum" in result.output


def test_a_filed_list_absent_from_the_folder_stops_the_run(project):
    lists = raw_dir(project)
    row = file_list(lists, "ub_84047A", "2024", "fy-2024-ub-awards.pdf", ub_pdf())
    write_manifest(lists, [row])
    (lists / row["stored_path"].rsplit("/", 1)[1]).unlink()

    result = project.topo("clean", "ed_grantee_lists", expect_exit=2)

    assert "absent" in result.output


def test_ed_lists_cannot_be_pulled(project, no_network):
    result = project.topo("pull", "ed_grantee_lists", "--pull-date", "2026-10-15", expect_exit=2)

    assert "cannot be pulled" in result.output


def test_a_name_wrapped_off_its_pdf_row_is_the_line_above_plus_the_line_below(project):
    lines = trio_pdf_lines(2024, "Upward Bound(UB)", [("P047A221610", "", "WI", 110, 549735)])
    row_at = next(i for i, ln in enumerate(lines) if ln.startswith("P047A221610"))
    lines[row_at:row_at + 1] = [
        "Board of Regents of the University of Wisconsin System/", "P047A221610 WI 110 $549,735", "Milwaukee",
    ]
    lists = raw_dir(project)
    write_manifest(lists, [file_list(lists, "ub_84047A", "2024", "ub.pdf", pdf_bytes(lines))])

    project.topo("clean", "ed_grantee_lists")

    (row,) = cleaned(project, "ed_trio_list_rows").to_dicts()
    assert row["recipient_campus"] == "Board of Regents of the University of Wisconsin System/ Milwaukee"
    assert row["ed_recipient"] == "Board of Regents of the University of Wisconsin System"
    assert row["ed_campus"] == "Milwaukee"


def test_a_list_whose_rows_disagree_with_its_stated_total_stops_the_run(project):
    lists = raw_dir(project)
    write_manifest(lists, [file_list(lists, "ub_84047A", "2024", "ub.pdf", ub_pdf(total_projects=3))])

    result = project.topo("clean", "ed_grantee_lists", expect_exit=2)

    assert "states 3 projects" in result.output


def test_cleaned_output_passes_its_schema_check(project, tmp_path):
    lists = raw_dir(project)
    bad_state = [("P042A201384", "University of Alaska/ Anchorage", "Alaska", 160, 282500, "Regular")]
    write_manifest(lists, [file_list(lists, "sss_84042A", "2023", "sss.xlsx",
                                     trio_xlsx_bytes(2023, "Student Support Services(SSS)", bad_state, tmp_path))])

    result = project.topo("clean", "ed_grantee_lists", expect_exit=2)

    assert "failed its schema check" in result.output


def test_known_list_gaps_are_recorded_not_chased(project, no_network):
    lists = raw_dir(project)
    write_manifest(lists, [
        file_list(lists, "ub_84047A", "2024", "ub.pdf", ub_pdf()),
        known_gap("ub_84047A", "2023", "known gap: no FY2023 list on the Upward Bound page"),
    ])

    project.topo("clean", "ed_grantee_lists")

    coverage = cleaned(project, "ed_list_coverage").filter(pl.col("program") == "Upward Bound")
    assert coverage.sort("fiscal_year").select("fiscal_year", "status", "note").rows() == [
        (2023, "missing", "known gap: no FY2023 list on the Upward Bound page"),
        (2024, "ok", ""),
    ]


def test_the_committed_manifest_records_the_11_known_gaps():
    from conftest import REPO_ROOT
    from topo.sources.ed_grantee_lists import read_manifest

    manifest = read_manifest(REPO_ROOT / "data" / "raw" / "ed_grantee_lists" / "manifest.csv")

    gaps = sorted((r.program, r.fy) for r in manifest if r.status == "missing")
    assert len(gaps) == 11
    assert ("ub_84047A", "2021") in gaps and ("mcnair_84217A", "2022") in gaps


def test_gear_up_pages_give_new_awards_per_fy_and_years_without_a_table_are_missing(project):
    lists = raw_dir(project)
    page = gearup_html_bytes({
        2025: [("Washington State University", "WA", "2,738", "$2,190,400"),
               ("Utah State University", "UT", "2,316", "$1,852,798")],
        2023: [("Weld County School District 6&nbsp;", "CO", "1,899&nbsp;", "$1,191,076")],
    })
    write_manifest(lists, [file_list(lists, "gearup_partnership_84334A", "2023-2025", "awards.html", page)])

    project.topo("clean", "ed_grantee_lists")

    rows = cleaned(project, "ed_gearup_list_rows").sort("fiscal_year", "grantee")
    assert rows.select("program", "fiscal_year", "grantee", "state", "students", "ed_amount").rows() == [
        ("GEAR UP partnership", 2023, "Weld County School District 6", "CO", 1899, 1191076.0),
        ("GEAR UP partnership", 2025, "Utah State University", "UT", 2316, 1852798.0),
        ("GEAR UP partnership", 2025, "Washington State University", "WA", 2738, 2190400.0),
    ]
    coverage = cleaned(project, "ed_list_coverage").sort("fiscal_year")
    assert coverage.select("fiscal_year", "status").rows() == [(2023, "ok"), (2024, "missing"), (2025, "ok")]


# ------------------------------------------------------------ joined with USAspending

PULL = "2026-10-07"
ED_ONLY_AMOUNT = 777123  # distinctive ED-list amounts, so the target list can be searched for them


def grant(fain: str, start_fy: int, years: int, amount: float = 100000) -> list[dict]:
    return [
        action(fain, i + 1, f"{start_fy + i}-05-15", amount, (f"{start_fy + i}-09-01", f"{start_fy + i + 1}-08-31"),
               action_type="A1" if i == 0 else "B1")
        for i in range(years)
    ]


def joined(project, name):
    return pl.read_parquet(project.root / "data" / "joined" / f"{name}.parquet")


@pytest.fixture
def ub_grant_with_lists(project, no_network):
    """An Upward Bound Grant (FY2022-FY2025 actions) on the FY2024 list only; FY2021-23 are known gaps."""
    write_actions(project.raw_usaspending, PULL, grant("P047A221553", 2022, 4))
    lists = raw_dir(project)
    write_manifest(lists, [
        file_list(lists, "ub_84047A", "2024", "ub.pdf", ub_pdf([
            ("P047A221553", "University of Alaska/ Anchorage", "AK", 60, ED_ONLY_AMOUNT),
            ("P047A229999", "Never Funded College/ North", "AK", 75, ED_ONLY_AMOUNT + 1),  # not in USAspending
        ])),
        *(known_gap("ub_84047A", str(fy), f"known gap: no FY{fy} list") for fy in (2021, 2022, 2023)),
    ])
    project.topo("run", "--as-of", PULL)
    return project


def test_campus_text_and_participants_are_grant_year_attributes_blank_in_years_without_a_list(ub_grant_with_lists):
    attrs = joined(ub_grant_with_lists, "grant_year_ed_attributes").filter(pl.col("fain") == "P047A221553")

    by_fy = {r["fiscal_year"]: r for r in attrs.to_dicts()}
    assert sorted(by_fy) == [2021, 2022, 2023, 2024, 2025, 2026]  # the reporting window
    assert by_fy[2024]["ed_recipient_campus"] == "University of Alaska/ Anchorage"
    assert by_fy[2024]["ed_campus"] == "Anchorage"
    assert by_fy[2024]["ed_participants"] == 60
    assert by_fy[2024]["ed_list_row_id"] == "ub_84047A:FY2024:1"
    for fy in (2021, 2022, 2023, 2025, 2026):
        assert by_fy[fy]["ed_participants"] is None, fy  # blank, not zero
        assert by_fy[fy]["ed_recipient_campus"] is None, fy
    assert [by_fy[fy]["ed_list_filed"] for fy in sorted(by_fy)] == [False, False, False, True, False, False]
    assert not any("amount" in column for column in attrs.columns)


def test_ed_list_amounts_do_not_appear_on_the_target_list(ub_grant_with_lists):
    text = next(ub_grant_with_lists.output.glob("target_list_*.csv")).read_text()

    assert str(ED_ONLY_AMOUNT) not in text
    assert f"{ED_ONLY_AMOUNT:,}" not in text
    assert "100000" in text  # the USAspending obligations are there


def test_a_fain_only_on_an_ed_list_is_an_exception_not_a_grant(ub_grant_with_lists):
    project = ub_grant_with_lists

    assert joined(project, "grants")["fain"].to_list() == ["P047A221553"]
    assert "P047A229999" not in joined(project, "grant_year_ed_attributes")["fain"].to_list()
    assert "P047A229999" not in {r["FAIN"] for r in project.read_csv(f"target_list_{PULL}.csv")}
    exceptions = joined(project, "ed_list_exceptions")
    assert exceptions.select("fain", "program", "fiscal_year", "list_row_id", "reason").rows() == [
        ("P047A229999", "Upward Bound", 2024, "ub_84047A:FY2024:2", "ed_list_fain_not_in_usaspending"),
    ]
