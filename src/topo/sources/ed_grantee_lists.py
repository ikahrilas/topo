"""ED grantee lists: hand-downloaded TRIO and GEAR UP lists, cleaned from the manifest.

ed.gov blocks non-browser clients, so these lists are filed by hand (#5) and
never fetched: this source has no `pull`, and `clean` makes no request. It reads
only the files named by `ok` rows of the committed, checksummed manifest
(data/raw/ed_grantee_lists/manifest.csv) and stops the run when a filed file
is absent or its bytes or SHA-256 differ from the manifest. Files in the
folder that the manifest doesn't name are ignored. `missing` rows are the known
list gaps (#16): they are recorded in the coverage table, never chased.

Cleaned tables:
    ed_trio_list_rows     one row per (TRIO Program, FY, FAIN): the "Recipient/ campus"
                          text, participants and ED's amount. The amount is for
                          reconciliation only; it never reaches the target list.
    ed_gearup_list_rows   one row per GEAR UP new award per FY (the pages carry no FAIN)
    ed_list_coverage      one row per (manifest program, FY): filed or missing, with the note
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl
import pandera.polars as pa
import pdfplumber
import polars as pl

from topo.config import Config, Layout
from topo.domain.programs import PROGRAMS, Program
from topo.guards import StructuralBreak, check_schema, check_unique

SOURCE = "ed_grantee_lists"
TRIO_TABLE = "ed_trio_list_rows"
GEARUP_TABLE = "ed_gearup_list_rows"
COVERAGE_TABLE = "ed_list_coverage"
CLEANED_TABLES = (TRIO_TABLE, GEARUP_TABLE, COVERAGE_TABLE)

FILED = "ok"
MISSING = "missing"

# Manifest program key -> FAIN prefix of the Program it lists.
MANIFEST_PROGRAMS: dict[str, str] = {
    "sss_84042A": "P042A",
    "ts_84044": "P044A",
    "ub_84047A": "P047A",
    "ubms_84047M": "P047M",
    "vub_84047V": "P047V",
    "eoc_84066A": "P066A",
    "mcnair_84217A": "P217A",
    "gearup_partnership_84334A": "P334A",
    "gearup_state_84334S": "P334S",
}
_BY_PREFIX = {p.fain_prefix: p for p in PROGRAMS}


class EdTrioListRows(pa.DataFrameModel):
    """One TRIO grantee-list row: a FAIN on one Program's list for one FY."""

    list_row_id: str = pa.Field(unique=True)  # "<manifest program>:FY<fy>:<row number>"
    program: str
    fiscal_year: int = pa.Field(ge=2000)
    fain: str = pa.Field(str_matches=r"^P\d{3}[A-Z]\d{6}$")
    recipient_campus: str  # ED's "Recipient/ campus" text as printed
    ed_recipient: str  # text before the first "/"
    ed_campus: str = pa.Field(nullable=True)  # text after the first "/", if any
    state: str = pa.Field(str_matches=r"^[A-Z]{2}$")
    participants: int = pa.Field(ge=0)
    ed_amount: float = pa.Field(ge=0)  # reconciliation only
    project_type: str = pa.Field(nullable=True)  # SSS only
    raw_file: str
    sha256: str
    filed_date: dt.date  # the manifest's Pull date (hand-download date)

    class Config:
        strict = True


class EdListCoverage(pa.DataFrameModel):
    """Whether a list is filed for one (manifest program, FY); missing rows are the known gaps."""

    manifest_program: str
    program: str
    fiscal_year: int = pa.Field(ge=2000)
    status: str = pa.Field(isin=[FILED, MISSING])
    note: str
    raw_file: str = pa.Field(nullable=True)
    filed_date: dt.date

    class Config:
        strict = True


# ------------------------------------------------------------------ manifest


@dataclass(frozen=True)
class ManifestRow:
    program: str  # manifest program key, e.g. "ub_84047A"
    fy: str  # "2024" or a range "2017-2025"
    status: str  # "ok" or "missing"
    pull_date: dt.date
    bytes: int | None
    sha256: str
    stored_name: str  # file name under data/raw/ed_grantee_lists/
    note: str

    @property
    def fiscal_years(self) -> list[int]:
        first, _, last = self.fy.partition("-")
        return list(range(int(first), int(last or first) + 1))


def manifest_path(layout: Layout) -> Path:
    return layout.raw_source(SOURCE) / "manifest.csv"


def read_manifest(path: Path) -> list[ManifestRow]:
    """The ED grantee-list manifest rows. A `source` column, when present, filters to this source."""
    with path.open(newline="", encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    rows = []
    for rec in records:
        if rec.get("source") not in (None, "", SOURCE):
            continue
        program = rec["program"]
        if program not in MANIFEST_PROGRAMS:
            raise StructuralBreak(f"ED grantee-list manifest names unknown program {program!r}")
        rows.append(
            ManifestRow(
                program=program,
                fy=rec["fy"],
                status=rec["status"],
                pull_date=dt.date.fromisoformat(rec["pull_date"]),
                bytes=int(rec["bytes"]) if rec.get("bytes") else None,
                sha256=rec.get("sha256", ""),
                stored_name=Path(rec["stored_path"]).name if rec.get("stored_path") else "",
                note=rec.get("note", ""),
            )
        )
    return rows


def program_of(manifest_program: str) -> Program:
    return _BY_PREFIX[MANIFEST_PROGRAMS[manifest_program]]


def verified_bytes(layout: Layout, row: ManifestRow) -> bytes:
    """The filed file's bytes, after checking them against the manifest; any mismatch is a break."""
    path = layout.raw_source(SOURCE) / row.stored_name
    if not row.stored_name or not path.is_file():
        raise StructuralBreak(f"ED grantee list filed in the manifest is absent: {path}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != row.sha256 or (row.bytes is not None and len(data) != row.bytes):
        raise StructuralBreak(
            f"ED grantee list {row.stored_name} fails its manifest checksum "
            f"(manifest {row.bytes} bytes sha256 {row.sha256}; file {len(data)} bytes sha256 {digest})"
        )
    return data


# ---------------------------------------------------------------- TRIO lists

# 'P047A221553 University of Alaska/ Anchorage AK 60 $ 309,505' (SSS adds a project type)
_TRIO_LINE = re.compile(
    r"^(?P<fain>P\d{3}[A-Z]\d{6})\s+(?P<name>.*?)\s*\b(?P<state>[A-Z]{2})\s+(?P<participants>\d[\d,]*)"
    r"\s+\$\s*(?P<amount>\d[\d,]*)(?:\s+(?P<ptype>\S.*))?$"
)
_FAIN_START = re.compile(r"^P\d{3}[A-Z]\d{6}\b")
_TOTAL_LINE = re.compile(r"^Total No\. of Projects:\s*(?P<count>\d+)")


def _number(text: str) -> int:
    return int(re.sub(r"[^\d]", "", text))


def parse_trio_pdf_lines(lines: list[str], label: str) -> list[dict]:
    """Rows from the text lines of a TRIO list PDF.

    A name wrapped off its row (the row starts with the FAIN and the state) is
    the line above plus the line below. The parsed row count must equal the
    list's own "Total No. of Projects".
    """
    rows: list[dict] = []
    stated_total = None
    for i, line in enumerate(lines):
        match = _TRIO_LINE.match(line)
        if match:
            name = match["name"]
            if not name:
                above = lines[i - 1] if i > 0 and not _FAIN_START.match(lines[i - 1]) else ""
                below = lines[i + 1] if i + 1 < len(lines) and not _FAIN_START.match(lines[i + 1]) else ""
                name = f"{above} {below}".strip()
            rows.append(
                {
                    "fain": match["fain"],
                    "recipient_campus": name,
                    "state": match["state"],
                    "participants": _number(match["participants"]),
                    "ed_amount": float(_number(match["amount"])),
                    "project_type": match["ptype"],
                }
            )
        elif _FAIN_START.match(line):
            raise StructuralBreak(f"{label}: unreadable list row {line!r}")
        elif total := _TOTAL_LINE.match(line):
            stated_total = int(total["count"])
    if stated_total is None:
        raise StructuralBreak(f"{label}: no 'Total No. of Projects' line")
    if stated_total != len(rows):
        raise StructuralBreak(f"{label}: read {len(rows)} rows but the list states {stated_total} projects")
    return rows


def _read_trio_pdf(path: Path, label: str) -> list[dict]:
    with pdfplumber.open(path) as pdf:
        lines = [ln.strip() for page in pdf.pages for ln in (page.extract_text() or "").splitlines()]
    return parse_trio_pdf_lines([ln for ln in lines if ln], label)


def _read_trio_xlsx(path: Path, label: str) -> list[dict]:
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book[book.sheetnames[0]]
        cells = [list(r) for r in sheet.iter_rows(values_only=True)]
    finally:
        book.close()
    header_at = next(
        (i for i, r in enumerate(cells) if r and str(r[0] or "").strip() == "PR Award Number"), None
    )
    if header_at is None:
        raise StructuralBreak(f"{label}: no 'PR Award Number' header row")
    header = [str(c or "").strip() for c in cells[header_at]]
    has_type = "Project Type" in header
    rows = []
    for r in cells[header_at + 1 :]:
        first = str(r[0] or "").strip()
        if not first:
            continue  # trailing "Data as of ..." and blank rows
        if not _FAIN_START.match(first):
            raise StructuralBreak(f"{label}: unreadable list row {r!r}")
        try:
            rows.append(
                {
                    "fain": first,
                    "recipient_campus": str(r[1] or "").strip(),
                    "state": str(r[2] or "").strip(),
                    "participants": _number(str(r[3])),
                    "ed_amount": float(_number(str(r[4]))),
                    "project_type": (str(r[header.index("Project Type")] or "").strip() or None) if has_type else None,
                }
            )
        except (ValueError, IndexError) as err:
            raise StructuralBreak(f"{label}: unreadable list row {r!r}") from err
    return rows


def _trio_rows(layout: Layout, row: ManifestRow) -> list[dict]:
    data = verified_bytes(layout, row)
    path = layout.raw_source(SOURCE) / row.stored_name
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        parsed = _read_trio_pdf(path, row.stored_name)
    elif suffix == ".xlsx":
        parsed = _read_trio_xlsx(path, row.stored_name)
    else:
        raise StructuralBreak(f"{row.stored_name}: no reader for {suffix} TRIO lists")
    (fy,) = row.fiscal_years
    program = program_of(row.program)
    sha256 = hashlib.sha256(data).hexdigest()
    out = []
    for number, rec in enumerate(parsed, start=1):
        text = re.sub(r"\s+", " ", rec["recipient_campus"]).strip()
        recipient, slash, campus = text.partition("/")
        out.append(
            {
                "list_row_id": f"{row.program}:FY{fy}:{number}",
                "program": program.name,
                "fiscal_year": fy,
                **rec,
                "recipient_campus": text,
                "ed_recipient": recipient.strip(),
                "ed_campus": (campus.strip() or None) if slash else None,
                "raw_file": row.stored_name,
                "sha256": sha256,
                "filed_date": row.pull_date,
            }
        )
    return out


# --------------------------------------------------------------------- clean


def _frame(model: type[pa.DataFrameModel], records: list[dict]) -> pl.DataFrame:
    schema = model.to_schema()
    dtypes = {name: col.dtype.type for name, col in schema.columns.items()}
    return pl.DataFrame(records, schema=dtypes).select(list(schema.columns))


def clean(config: Config, pull_date: dt.date | None = None) -> pl.DataFrame:
    """Clean every list filed in the manifest. `pull_date` is unused: lists are hand-filed.

    With no manifest at all nothing is filed, and the cleaned tables are empty.
    Returns the TRIO list rows.
    """
    layout = config.layout
    path = manifest_path(layout)
    manifest = read_manifest(path) if path.exists() else []

    trio: list[dict] = []
    coverage: list[dict] = []
    for row in manifest:
        program = program_of(row.program)
        coverage.extend(
            {
                "manifest_program": row.program,
                "program": program.name,
                "fiscal_year": fy,
                "status": row.status,
                "note": row.note,
                "raw_file": row.stored_name or None,
                "filed_date": row.pull_date,
            }
            for fy in row.fiscal_years
        )
        if row.status == FILED and program.family == "TRIO":
            trio.extend(_trio_rows(layout, row))

    trio_rows = _frame(EdTrioListRows, trio).sort("program", "fiscal_year", "fain")
    check_unique(trio_rows, ["program", "fiscal_year", "fain"], "ED TRIO grantee lists")
    trio_rows = check_schema(EdTrioListRows, trio_rows, "ED TRIO grantee lists")

    list_coverage = _frame(EdListCoverage, coverage).sort("program", "fiscal_year")
    check_unique(list_coverage, ["manifest_program", "fiscal_year"], "ED grantee-list coverage")
    list_coverage = check_schema(EdListCoverage, list_coverage, "ED grantee-list coverage")

    layout.cleaned.mkdir(parents=True, exist_ok=True)
    trio_rows.write_parquet(layout.cleaned_table(TRIO_TABLE))
    list_coverage.write_parquet(layout.cleaned_table(COVERAGE_TABLE))
    return trio_rows
