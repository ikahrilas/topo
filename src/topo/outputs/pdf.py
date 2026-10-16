"""Render the one-pager's Markdown to a one-page PDF (fpdf2, core fonts).

Only the Markdown the pipeline writes is understood: `#`/`##` headings, plain
paragraphs (with **bold**), `###` subheadings, numbered items, pipe tables, and
a `---` rule after which every line is the page footer. The font shrinks in
steps until the page fits; text is encoded as Windows-1252 (core fonts).
"""

from __future__ import annotations

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

FONT = "helvetica"
SIZES = (8.5, 8.0, 7.5, 7.0, 6.5, 6.0, 5.5)  # base font sizes tried, largest first
MARGIN = 12  # mm


class _Page(FPDF):
    def __init__(self, footer_lines: list[str], size: float):
        super().__init__(orientation="portrait", unit="mm", format="Letter")
        self.core_fonts_encoding = "windows-1252"
        self.footer_lines = footer_lines
        self.base = size
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(True, margin=MARGIN + 4 * len(footer_lines))

    def footer(self) -> None:
        if not self.footer_lines:
            return
        self.set_y(-(MARGIN + 3.5 * len(self.footer_lines)))
        self.set_font(FONT, "I", self.base - 1.5)
        for line in self.footer_lines:
            self.multi_cell(0, 3.5, _plain(line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _plain(text: str) -> str:
    return text.encode("windows-1252", errors="replace").decode("windows-1252")


def _split(text: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines()
    if "---" in lines:
        cut = lines.index("---")
        return lines[:cut], [line for line in lines[cut + 1:] if line.strip()]
    return lines, []


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _draw(pdf: _Page, body: list[str]) -> None:
    size = pdf.base
    line_h = size * 0.48
    i = 0
    while i < len(body):
        line = body[i]
        if line.startswith("|"):
            block = []
            while i < len(body) and body[i].startswith("|"):
                block.append(body[i])
                i += 1
            rows = [_cells(row) for row in block if not set(row.replace("|", "").strip()) <= set("-: ")]
            pdf.set_font(FONT, "", size - 1)
            columns = len(rows[0])
            with pdf.table(
                first_row_as_headings=True, line_height=line_h, padding=0.6, text_align="LEFT",
                col_widths=(2.2, *(1,) * (columns - 1)), align="LEFT",
                width=pdf.epw if columns > 3 else min(pdf.epw, 40 * (columns + 1.2)),
                headings_style=FontFace(emphasis="BOLD"),
            ) as grid:
                for row in rows:
                    cells = grid.row()
                    for cell in row:
                        cells.cell(_plain(cell))
            pdf.ln(1)
            continue
        if line.startswith("# "):
            pdf.set_font(FONT, "B", size + 4)
            pdf.multi_cell(0, line_h * 1.6, _plain(line[2:]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif line.startswith("## "):
            pdf.ln(1)
            pdf.set_font(FONT, "B", size + 1.5)
            pdf.multi_cell(0, line_h * 1.3, _plain(line[3:]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif line.startswith("### "):
            pdf.set_font(FONT, "B", size)
            pdf.multi_cell(0, line_h * 1.2, _plain(line[4:]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif line.strip():
            pdf.set_font(FONT, "", size)
            pdf.multi_cell(0, line_h, _plain(line), markdown=True, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.ln(line_h * 0.4)
        i += 1


def render_pdf(text: str) -> bytes:
    """The text on one Letter page, at the largest font size that fits (else the smallest)."""
    body, footer = _split(text)
    for size in SIZES:
        pdf = _Page(footer, size)
        pdf.add_page()
        _draw(pdf, body)
        if pdf.pages_count == 1 or size == SIZES[-1]:
            return bytes(pdf.output())
    raise AssertionError("unreachable")
