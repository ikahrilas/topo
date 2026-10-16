"""Seam 1: the one-pager (#44) via `topo run`: a plain-language summary in Markdown, rendered to PDF.

Fixtures put the As-of date on the Pull date, 2026-10-07, so the reporting
window is FY2021-FY2026 and FY2026 (ended 2026-09-30) is still provisional.
"""

from __future__ import annotations

import json
import re

import pdfplumber
from support.markdown import prose, sections, table
from support.usaspending import action, write_actions

PULL = "2026-10-07"
MD = f"one_pager_{PULL}.md"
PDF = f"one_pager_{PULL}.pdf"
CENSUS_NOTICE = "This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau."
HEADINGS = ["What's out there", "What's changed since 2025", "What's coming up", "How far to trust this"]


def grant(fain: str, start_year: int, years: int, amount: float = 100_000, **who) -> list[dict]:
    """A1 in May of start_year; Sept-Aug Budget periods, each funded in May before it starts."""
    return [
        action(fain, i + 1, f"{start_year + i}-05-15", amount, (f"{start_year + i}-09-01", f"{start_year + i + 1}-08-31"),
               action_type="A1" if i == 0 else "B1", **who)
        for i in range(years)
    ]


def one_pager(project, name: str = MD) -> str:
    return (project.output / name).read_text()


def test_run_delivers_the_one_pager_as_markdown_and_a_one_page_pdf_with_the_census_notice_in_the_footer(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A220845", 2022, 5))

    project.topo("run", "--as-of", PULL)

    text = one_pager(project)
    assert [h for h in sections(text) if h in HEADINGS] == HEADINGS
    assert text.rstrip().endswith(CENSUS_NOTICE)
    with pdfplumber.open(project.output / PDF) as pdf:
        assert len(pdf.pages) == 1
        page = pdf.pages[0].extract_text()
    for heading in HEADINGS:
        assert heading in page
    assert CENSUS_NOTICE in " ".join(page.split())
    for name in (MD, PDF):
        sidecar = json.loads((project.output / f"{name}.provenance.json").read_text())
        assert (sidecar["output"].endswith(name), sidecar["pull_date"], sidecar["as_of"]) == (True, PULL, PULL)
