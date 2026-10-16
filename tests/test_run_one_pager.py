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


MARKER = re.compile(r"\[([a-z]+) (\d)\]")


def trust_items(text: str) -> list[str]:
    """The numbered items of "How far to trust this", in order."""
    items = [line for line in sections(text)["How far to trust this"] if re.match(r"\d+\. ", line)]
    assert [int(line.split(".")[0]) for line in items] == list(range(1, len(items) + 1))
    return [line.split(". ", 1)[1] for line in items]


def marked(cell: str, word: str, text: str) -> str:
    """The trust item a one-word marker in `cell` points to."""
    found = {w: int(n) for w, n in MARKER.findall(cell)}
    assert word in found, (word, cell)
    return trust_items(text)[found[word] - 1]


def test_whats_out_there_shows_grants_and_dollars_by_program_fy2021_to_the_last_ended_fy_with_fy2026_provisional(
    project,
):
    write_actions(project.raw_usaspending, PULL, [
        *grant("P047A220845", 2022, 5),  # Upward Bound, FY2022-FY2026
        *grant("P044A210001", 2021, 6, amount=250_000),  # Talent Search, FY2021-FY2026
        *grant("P042A200001", 2020, 2, amount=1_500_000),  # Student Support Services, FY2020 (before the window), FY2021
    ])

    project.topo("run", "--as-of", PULL)

    text = one_pager(project)
    rows = {r["Program"]: r for r in table(text, "What's out there")}
    header = list(next(iter(rows.values())))
    assert header[1:6] == ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025"]
    fy2026 = header[6]
    assert fy2026.startswith("FY2026 [provisional")
    assert "provisional" in marked(fy2026, "provisional", text)
    assert "2026-10-07" in marked(fy2026, "provisional", text)
    assert [rows["Upward Bound"][fy] for fy in ("FY2021", "FY2022", fy2026)] == ["-", "1 / $100K", "1 / $100K"]
    assert [rows["Talent Search"][fy] for fy in ("FY2021", "FY2025")] == ["1 / $250K", "1 / $250K"]
    assert [rows["Student Support Services"][fy] for fy in ("FY2021", "FY2022")] == ["1 / $1.5M", "-"]
    assert rows["McNair"]["FY2024"] == "-"  # every Program is listed, funded or not
    assert [rows["All Programs"][fy] for fy in ("FY2021", "FY2022")] == ["2 / $1.8M", "2 / $350K"]


def test_once_fy2026_is_90_days_past_its_end_it_is_no_longer_provisional(project):
    write_actions(project.raw_usaspending, "2026-12-29", grant("P047A220845", 2022, 5))

    project.topo("run", "--as-of", "2026-12-29")

    text = one_pager(project, "one_pager_2026-12-29.md")
    header = list(table(text, "What's out there")[0])
    assert header[-1] == "FY2026"
    assert "provisional" not in prose(text, "How far to trust this")
