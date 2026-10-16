"""Seam 1: the one-pager (#44) via `topo run`: a plain-language summary in Markdown, rendered to PDF.

Fixtures put the As-of date on the Pull date, 2026-10-07, so the reporting
window is FY2021-FY2026 and FY2026 (ended 2026-09-30) is still provisional.
"""

from __future__ import annotations

import json
import re

import pdfplumber
from support.markdown import prose, sections, table
from support.curated_totals import allocation, write_curated
from support.ed_lists import file_list, pdf_bytes, trio_pdf_lines, write_manifest
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


DISRUPTED = [
    *grant("P047A220845", 2022, 5),  # continued throughout
    *grant("P047A220846", 2022, 3),  # Budget period starting 2025-09-01 unfunded
    *grant("P047A220847", 2022, 3),  # 2025-09-01 period funded late, 2026-09-01 period continued (since restored)
    action("P047A220847", 4, "2025-10-05", 100_000, ("2025-09-01", "2026-08-31")),
    action("P047A220847", 5, "2026-05-15", 100_000, ("2026-09-01", "2027-08-31")),
    *grant("P047A220848", 2022, 4),  # 2025-09-01 period funded, then reversed
    action("P047A220848", 5, "2025-11-01", -100_000, ("2025-09-01", "2026-08-31")),
]


def test_whats_changed_counts_disrupted_grants_by_funding_pattern_with_the_2024_baseline(project):
    write_actions(project.raw_usaspending, PULL, DISRUPTED)

    project.topo("run", "--as-of", PULL)

    text = one_pager(project)
    counts = {r["Funding pattern"]: r["Grants"] for r in table(text, "What's changed since 2025")}
    assert counts == {"unfunded": "1", "funded late": "1", "reversed": "1"}
    words = prose(text, "What's changed since 2025")
    assert "3 Grants" in words and "1 since restored" in words
    assert "not proof of a policy cut" in words  # ADR 0001: a funding pattern, never a cause
    assert "95 Grants" in words and "2024" in words
    assert "never a cause" in marked(words, "pattern", text)
    assert "reporting gaps" not in text  # no ED-list evidence: the trigger is not met


def test_the_reporting_gap_sentence_appears_only_when_ed_lists_fund_enough_unfunded_budget_periods(project):
    write_actions(project.raw_usaspending, PULL, DISRUPTED)
    lists = project.root / "data" / "raw" / "ed_grantee_lists"
    write_manifest(lists, [
        file_list(lists, "ub_84047A", "2025", "ub2025.pdf", pdf_bytes(trio_pdf_lines(2025, "Upward Bound", [
            ("P047A220846", "University of South Florida/ Tampa", "FL", 60, 100_000),
        ]))),
    ])

    project.topo("run", "--as-of", PULL)

    words = prose(one_pager(project), "What's changed since 2025")
    assert "Unfunded status may partly reflect USAspending reporting gaps: 1 of 1 unfunded Budget periods" in words


UB_FY2022_DEADLINE = ("Upward Bound,2022,2022-01-31,"
                      "Applications for New Awards; Upward Bound Program (86 FR 71477; Dec. 16 2021),,\n")


def test_whats_coming_up_lists_re_competing_programs_and_new_grants_from_the_last_3_months(project):
    curated = project.root / "data" / "curated"
    curated.mkdir(parents=True)
    (curated / "deadlines.csv").write_text(
        "program,competition_fy,application_deadline,citation,source_url,note\n" + UB_FY2022_DEADLINE)
    write_actions(project.raw_usaspending, PULL, [
        *grant("P047A170001", 2017, 5), *grant("P047A170002", 2017, 5),  # the prior Upward Bound Cohort
        *grant("P047A220001", 2022, 5), *grant("P047A220002", 2022, 5),  # re-competing soon: due 2027-01-31
        action("P042A260001", 1, "2026-08-15", 400_000, ("2026-09-01", "2027-08-31"), action_type="A1"),  # new
        action("P042A260002", 1, "2026-06-01", 400_000, ("2026-06-01", "2027-05-31"), action_type="A1"),  # 4 months
    ])

    project.topo("run", "--as-of", PULL)

    text = one_pager(project)
    [row] = table(text, "What's coming up")
    assert (row["Program"], row["Evidence tier"], row["Grants re-competing"]) == ("Upward Bound", "inferred", "2")
    assert row["Predicted due date"].startswith("2027-01-31 [untested")
    assert "not yet tested" in marked(row["Predicted due date"], "untested", text)
    assert "prediction" in prose(text, "What's coming up")
    new = table(text, "New Grants in the last 3 months")
    assert [(r["Program"], r["New Grants"], r["Dollars"]) for r in new] == [("Student Support Services", "1", "$400K")]


def test_with_nothing_re_competing_the_section_says_so(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A220845", 2022, 5))

    project.topo("run", "--as-of", PULL)

    text = one_pager(project)
    assert table(text, "What's coming up") == []
    assert "No Program has Grants re-competing" in prose(text, "What's coming up")
    assert "No new Grants" in prose(text, "New Grants in the last 3 months")


def test_how_far_to_trust_this_has_at_most_8_one_sentence_items_and_names_never_funded_applications(project):
    write_actions(project.raw_usaspending, PULL, DISRUPTED)

    project.topo("run", "--as-of", PULL)

    items = trust_items(one_pager(project))
    assert 1 <= len(items) <= 8
    for item in items:
        assert item.endswith(".") and not re.search(r"\.\s", item), item
    [blind_spot] = [item for item in items if "never funded" in item]
    assert "blind spot" in blind_spot.lower()


def test_every_unexplained_reconciliation_row_is_named(project):
    write_actions(project.raw_usaspending, PULL, [
        *grant("P044A210001", 2021, 6, amount=250_000), *grant("P217A210001", 2021, 6, amount=200_000),
    ])
    write_curated(project.root, [], [
        allocation("Talent Search", 2024, 5_000_000),  # $250K in USAspending: unexplained
        allocation("McNair", 2023, 9_000_000),  # $200K in USAspending: unexplained
        allocation("McNair", 2022, 1_000_000),  # within $1M: reconciled
    ])

    project.topo("run", "--as-of", PULL)

    text = one_pager(project)
    [item] = [item for item in trust_items(text) if "unexplained" in item]
    assert item.startswith("2 reconciliation rows are unexplained")
    assert "Talent Search FY2024 ed_allocation_dollars" in item
    assert "McNair FY2023 ed_allocation_dollars" in item
    assert "McNair FY2022" not in item
    assert "unexplained" in marked(prose(text, "What's out there"), "checked", text)


def test_with_no_unexplained_rows_the_trust_item_says_none_are(project):
    write_actions(project.raw_usaspending, PULL, grant("P047A220845", 2022, 5))

    project.topo("run", "--as-of", PULL)

    [item] = [item for item in trust_items(one_pager(project)) if "unexplained" in item]
    assert item.startswith("No reconciliation row is unexplained")
