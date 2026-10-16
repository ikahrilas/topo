"""The one-pager: a plain-language summary for the founder, delivered as
output/one_pager_<Pull date>.md and the same text rendered to a one-page PDF.

Sections: what's out there, what's changed since 2025, what's coming up, and
how far to trust this. Headline numbers carry a one-word marker such as
"[provisional 1]" that points to numbered item 1 of "How far to trust this"
(at most 8 one-sentence items). The Census notice sits in the footer.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from topo.domain.programs import PROGRAMS
from topo.fiscal import ReportingWindow, fy_label
from topo.outputs.delivery import delivery_paths, write_new
from topo.outputs.pdf import render_pdf
from topo.outputs.target_list import CENSUS_NOTICE

STEM = "one_pager"
MAX_TRUST_ITEMS = 8
ALL_PROGRAMS = "All Programs"

# Trust item keys
PROVISIONAL = "provisional"


@dataclass(frozen=True)
class OnePagerInputs:
    pull_date: dt.date
    as_of: dt.date
    window: ReportingWindow
    grants: pl.DataFrame  # joined grants (fain, program)
    fy_obligations: pl.DataFrame  # joined fy_obligations (fain, fiscal_year, obligation)
    provisional_fys: list[int] = field(default_factory=list)  # window FYs still inside the reporting lag
    provisional_lag_days: int = 90
    awaited: dict[str, str] = field(default_factory=dict)  # Program -> "FY2026 new awards not yet reported"


@dataclass(frozen=True)
class OnePagerFiles:
    markdown: Path
    pdf: Path


class TrustItems:
    """The numbered "How far to trust this" items; markers point to them by key."""

    def __init__(self, items: list[tuple[str, str]]):
        if len(items) > MAX_TRUST_ITEMS:
            raise ValueError(f"{len(items)} trust items; the one-pager allows {MAX_TRUST_ITEMS}")
        self.items = items
        self._number = {key: n for n, (key, _) in enumerate(items, start=1)}

    def marker(self, key: str, word: str) -> str:
        return f"[{word} {self._number[key]}]"

    def lines(self) -> list[str]:
        return [f"{n}. {sentence}" for n, (_, sentence) in enumerate(self.items, start=1)]


def money(value: float) -> str:
    """Short dollars: $250K, $1.5M, $1.14B."""
    if abs(value) >= 1e9:
        return f"${value / 1e9:,.2f}B"
    if abs(value) >= 1e6:
        return f"${value / 1e6:,.1f}M"
    return f"${value / 1e3:,.0f}K"


def _trust_items(inputs: OnePagerInputs) -> TrustItems:
    items: list[tuple[str, str]] = []
    if inputs.provisional_fys:
        years = ", ".join(fy_label(fy) for fy in inputs.provisional_fys)
        awaited = "".join(f"; {program}: {note}" for program, note in sorted(inputs.awaited.items()))
        items.append((PROVISIONAL, (
            f"{years} is provisional (as of {inputs.pull_date.isoformat()}; reporting lag): USAspending is still "
            f"catching up until {inputs.provisional_lag_days} days after the year ends{awaited}."
        )))
    return TrustItems(items)


def _whats_out_there(inputs: OnePagerInputs, trust: TrustItems) -> list[str]:
    fys = inputs.window.fiscal_years
    by_program = (
        inputs.fy_obligations.join(inputs.grants.select("fain", "program"), on="fain")
        .group_by("program", "fiscal_year")
        .agg((pl.col("obligation") > 0).sum().alias("grants"), pl.col("obligation").sum().alias("dollars"))
    )
    totals = by_program.group_by("fiscal_year").agg(pl.col("grants").sum(), pl.col("dollars").sum()).with_columns(
        pl.lit(ALL_PROGRAMS).alias("program")
    )
    cells = {
        (r["program"], r["fiscal_year"]): f"{r['grants']} / {money(r['dollars'])}" if r["grants"] else "-"
        for r in pl.concat([by_program, totals.select(by_program.columns)]).iter_rows(named=True)
    }
    header = [
        fy_label(fy) + (f" {trust.marker(PROVISIONAL, 'provisional')}" if fy in inputs.provisional_fys else "")
        for fy in fys
    ]
    names = [p.name for p in PROGRAMS] + [ALL_PROGRAMS]
    out = [
        f"Grants funded and dollars obligated per fiscal year, by Program, {fy_label(fys[0])} to {fy_label(fys[-1])} "
        "(USAspending obligations by action date; a Grant counts in a year when its net obligation that year is "
        "positive).",
        "",
    ]
    out += _table(["Program", *header], [[name, *(cells.get((name, fy), "-") for fy in fys)] for name in names])
    return out


def _table(header: list[str], rows: list[list]) -> list[str]:
    def cell(value) -> str:
        return "" if value is None else str(value).replace("|", "/")

    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return lines + ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]


def render_one_pager(inputs: OnePagerInputs) -> str:
    trust = _trust_items(inputs)
    out = [
        "# TRIO and GEAR UP Grants: one-page summary",
        "",
        f"Pull date {inputs.pull_date.isoformat()}. As-of date {inputs.as_of.isoformat()}.",
        "",
        "## What's out there",
        "",
        *_whats_out_there(inputs, trust),
        "",
        "## What's changed since 2025",
        "",
        "## What's coming up",
        "",
        "## How far to trust this",
        "",
        *trust.lines(),
        "",
        "---",
        "",
        CENSUS_NOTICE,
    ]
    return "\n".join(out) + "\n"


def write_one_pager(text: str, output_dir: Path, pull_date: dt.date) -> OnePagerFiles:
    """Write the Markdown and its PDF under one version suffix; never overwrite."""
    paths = delivery_paths(output_dir, STEM, pull_date, ("md", "pdf"))
    write_new(paths["md"], text.encode())
    write_new(paths["pdf"], render_pdf(text))
    return OnePagerFiles(markdown=paths["md"], pdf=paths["pdf"])
