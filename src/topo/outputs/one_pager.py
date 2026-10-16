"""The one-pager: a plain-language summary for the founder, delivered as
output/one_pager_<Pull date>.md and the same text rendered to a one-page PDF.

Sections: what's out there, what's changed since 2025, what's coming up, and
how far to trust this. The Census notice sits in the footer.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from topo.outputs.delivery import delivery_paths, write_new
from topo.outputs.pdf import render_pdf
from topo.outputs.target_list import CENSUS_NOTICE

STEM = "one_pager"


@dataclass(frozen=True)
class OnePagerInputs:
    pull_date: dt.date
    as_of: dt.date


@dataclass(frozen=True)
class OnePagerFiles:
    markdown: Path
    pdf: Path


def render_one_pager(inputs: OnePagerInputs) -> str:
    out = [
        "# TRIO and GEAR UP Grants: one-page summary",
        "",
        f"Pull date {inputs.pull_date.isoformat()}. As-of date {inputs.as_of.isoformat()}.",
        "",
        "## What's out there",
        "",
        "## What's changed since 2025",
        "",
        "## What's coming up",
        "",
        "## How far to trust this",
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
