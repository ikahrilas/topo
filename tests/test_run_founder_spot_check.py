"""Seam 1: the founder spot-check loop, via `topo report` / `topo run` and `topo ingest-findings`.

`topo report` delivers a frozen spot-check copy of the pull's workbook; the founder marks rows
("Looks right?", Field, Note) and the Missing sheet; `topo ingest-findings` appends the allowed
columns to the write-once Review findings file; later pulls show "Last founder mark" by FAIN.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from openpyxl import load_workbook

from support.curated import override_row, write_overrides
from support.ipeds import DIRECTORY_COLUMNS, ENROLLMENT_COLUMNS, directory_row, enrollment_row, write_csv
from support.markdown import table
from support.usaspending import action, write_actions
from support.workbook import read_sheet, sheet_names, sheet_text

PULL = "2026-10-07"
SPOT_CHECK = f"spot_check_{PULL}.xlsx"
FINDINGS = Path("data") / "curated" / "review_findings.csv"
IHE = "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"


def one_year(fain, recipient, uei, state, amount=300000):
    return action(fain, 1, "2025-07-01", amount, ("2025-09-01", "2026-08-31"), action_type="A1",
                  recipient=recipient, uei=uei, state=state, business_types_description=IHE)


GRANTS = [
    one_year("P042A250001", "COLLEGE NUMBER 1", "MTUEI0000001", "MT"),
    one_year("P042A250002", "COLLEGE NUMBER 2", "MTUEI0000002", "MT"),
    one_year("P047A250003", "COLLEGE NUMBER 3", "MTUEI0000003", "MT"),
    one_year("P042A250004", "UNIVERSITY OF MINNESOTA DULUTH", "MNUEI0000004", "MN"),
    one_year("P042A250005", "OKLAHOMA COLLEGE", "OKUEI0000005", "OK"),
]


def setup(project):
    write_actions(project.raw_usaspending, PULL, GRANTS)
    folder = project.root / "data" / "raw" / "ipeds" / PULL
    write_csv(folder / "colleges_ipeds_directory.csv", DIRECTORY_COLUMNS, [
        directory_row("900001", "College Number 1", "MT", ueis=("MTUEI0000001",)),
        directory_row("900002", "College Number 2", "MT", ueis=("MTUEI0000002",)),
        directory_row("900003", "College Number 3", "MT", ueis=("MTUEI0000003",)),
        directory_row("174233", "University of Minnesota-Duluth", "MN", ueis=("MNUEI0000004",)),
    ])
    write_csv(folder / "colleges_ipeds_fall-enrollment-race_2024.csv", ENROLLMENT_COLUMNS,
              [enrollment_row("900001", 2024, 900)])


def by_fain(rows):
    return {r["FAIN"]: r for r in rows}


def mark(spot_check: Path, returned: Path, marks: dict[str, tuple], missing=(), extra_column=None) -> Path:
    """Fill a delivered spot-check copy as the founder would and save it as the returned workbook.

    marks: FAIN -> (Looks right?, Field, Note). missing: (State, Recipient, Program, Note) rows.
    extra_column: (header, value) written into a new column on every marked row (data the ingest must drop).
    """
    book = load_workbook(spot_check)
    sheet = book["Target list"]
    header = [c.value for c in sheet[1]]
    col = {name: header.index(name) + 1 for name in header}
    if extra_column:
        sheet.cell(row=1, column=len(header) + 1, value=extra_column[0])
    for row in range(2, sheet.max_row + 1):
        fain = sheet.cell(row=row, column=col["FAIN"]).value
        if fain in marks:
            looks, field, note = marks[fain]
            sheet.cell(row=row, column=col["Looks right?"], value=looks)
            sheet.cell(row=row, column=col["Field"], value=field)
            sheet.cell(row=row, column=col["Note"], value=note)
            if extra_column:
                sheet.cell(row=row, column=len(header) + 1, value=extra_column[1])
    for values in missing:
        book["Missing"].append(list(values))
    book.save(returned)
    return returned


def test_report_delivers_a_spot_check_copy_with_state_counts_mark_columns_and_a_names_warning(project):
    setup(project)

    project.topo("run", "--as-of", PULL)

    path = project.output / SPOT_CHECK
    assert sheet_names(path)[:2] == ["Spot check", "States"]
    assert {"Target list", "Ended", "Missing"} <= set(sheet_names(path))
    states = {r["State"]: r["Grants"] for r in read_sheet(path, "States")}
    assert states == {"MN": "1", "MT": "3", "OK": "1"}
    instructions = sheet_text(path, "Spot check")
    assert "Do not enter client or personal names" in instructions
    assert "ok / wrong / stale" in instructions
    assert "100 characters" in instructions
    rows = by_fain(read_sheet(path, "Target list"))
    assert set(rows) == {g["award_id_fain"] for g in GRANTS}
    assert {"Looks right?", "Field", "Note", "Last founder mark"} <= set(rows["P042A250001"])
    assert rows["P042A250001"]["Looks right?"] == ""
    assert list(read_sheet_header(path, "Missing")) == ["State", "Recipient", "Program", "Note"]
    assert (project.output / f"{SPOT_CHECK}.provenance.json").exists()


def read_sheet_header(path, sheet):
    return [c.value for c in next(load_workbook(path, read_only=True)[sheet].iter_rows(max_row=1))]


def test_the_spot_check_copy_locks_everything_but_the_mark_columns(project):
    setup(project)

    project.topo("run", "--as-of", PULL)

    sheet = load_workbook(project.output / SPOT_CHECK)["Target list"]
    header = [c.value for c in sheet[1]]
    assert sheet.protection.sheet
    editable = {header[c.column - 1] for c in sheet[2] if not c.protection.locked}
    assert editable == {"Looks right?", "Field", "Note"}


def test_a_rerun_never_overwrites_a_delivered_spot_check_copy(project):
    setup(project)
    project.topo("run", "--as-of", PULL)
    first = (project.output / SPOT_CHECK).read_bytes()

    project.topo("report")

    assert (project.output / SPOT_CHECK).read_bytes() == first
    assert (project.output / f"spot_check_{PULL}_v2.xlsx").exists()
