"""Hand-built ED grantee-list fixtures, shaped like the real hand-filed files.

TRIO lists come as PDF (FY2024-25) or XLSX (FY2021-23); GEAR UP lists come as
one saved HTML page per Program with one table per FY. `file_list` writes a file
into data/raw/ed_grantee_lists/ and returns its manifest row (with the real
bytes and SHA-256); `write_manifest` writes those rows as the one raw manifest,
data/raw/manifest.csv (source "ed_grantee_lists"), in the committed column order.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import openpyxl

from topo.manifest import COLUMNS as MANIFEST_COLUMNS

ED_SOURCE = {
    "source": "ed_grantee_lists",
    "licence_citation": "U.S. Department of Education, https://www.ed.gov (U.S. Government work, public domain)",
}
FILED = "2026-10-15"

# One TRIO list row: (FAIN, "Recipient/ campus" text, state, participants, amount[, project type])
TrioRow = tuple


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_bytes(lines: list[str]) -> bytes:
    """A minimal one-page PDF (Helvetica) with one text line per entry, top to bottom."""
    stream = "\n".join(
        f"BT /F1 8 Tf 20 {780 - 12 * i} Td ({_pdf_escape(line)}) Tj ET" for i, line in enumerate(lines)
    ).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def trio_pdf_lines(fy: int, title: str, rows: list[TrioRow], *, total_projects: int | None = None) -> list[str]:
    """The text lines of a FY2024/2025-style TRIO list PDF, totals line included."""
    lines = [
        f"PR Award Number of FY {fy} Funding",
        f"{title} Grantees State",
        f"Number Participants ({fy}-{str(fy + 1)[2:]} Project Yr)",
    ]
    for fain, name, state, participants, amount, *ptype in rows:
        tail = f" {ptype[0]}" if ptype else ""
        lines.append(f"{fain} {name} {state} {participants:,} $ {amount:,}{tail}".replace("  ", " "))
    count = len(rows) if total_projects is None else total_projects
    lines.append(
        f"Total No. of Projects: {count} {sum(r[3] for r in rows):,} $ {sum(r[4] for r in rows):,}"
    )
    lines.append(f"Data as of January {fy + 1}")
    return lines


def trio_xlsx_bytes(fy: int, title: str, rows: list[TrioRow], tmp: Path) -> bytes:
    """A FY2021-2023-style TRIO list workbook."""
    book = openpyxl.Workbook()
    sheet = book.active
    header = ["PR Award Number", f"{title} Grantees", "State", "Number of Participants",
              f"FY {fy} Funding ({fy}-{str(fy + 1)[2:]} Project Yr)"]
    if any(len(r) > 5 for r in rows):
        header.append("Project Type")
    sheet.append(header)
    for row in rows:
        sheet.append(list(row))
    sheet.append([None, f"Data as of January {fy + 1}", None, None, None])
    path = tmp / "book.xlsx"
    book.save(path)
    return path.read_bytes()


def gearup_html_bytes(tables: dict[int, list[tuple[str, str, str, str]]]) -> bytes:
    """A saved GEAR UP "Grant Awards" page: one accordion section and table per FY."""
    sections = []
    for fy, rows in tables.items():
        body = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in rows)
        sections.append(
            f'<div class="paragraph" id="fy-{fy}"><h2>FY {fy} Awards</h2>'
            "<table><thead><tr><th>New Grantees</th><th>State</th><th>Year 1 Proposed Students Served</th>"
            f"<th>Year 1 Budget</th></tr></thead><tbody>{body}</tbody></table></div>"
        )
    return f"<html><body><h2>Grant Awards</h2>{''.join(sections)}</body></html>".encode()


def file_list(raw_dir: Path, program: str, fy: str, original_name: str, data: bytes) -> dict[str, str]:
    """Write one hand-filed list and return its manifest row."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{program}__FY{fy}__{original_name}"
    (raw_dir / stored).write_bytes(data)
    return {
        **ED_SOURCE, "request": "hand-downloaded from source_page_url",
        "program": program, "fy": fy, "status": "ok",
        "source_page_url": f"https://www.ed.gov/{program}", "file_url": f"https://www.ed.gov/media/document/{original_name}",
        "pull_date": FILED, "bytes": str(len(data)), "sha256": hashlib.sha256(data).hexdigest(),
        "original_name": original_name, "stored_path": f"data/raw/ed_grantee_lists/{stored}", "note": "",
    }


def known_gap(program: str, fy: str, note: str) -> dict[str, str]:
    return {
        **ED_SOURCE, "request": "",
        "program": program, "fy": fy, "status": "missing", "source_page_url": "", "file_url": "",
        "pull_date": FILED, "bytes": "", "sha256": "", "original_name": "", "stored_path": "", "note": note,
    }


def write_manifest(raw_dir: Path, rows: list[dict[str, str]]) -> Path:
    """Write `rows` as data/raw/manifest.csv; `raw_dir` is the lists folder data/raw/ed_grantee_lists/."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir.parent / "manifest.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
    return path
