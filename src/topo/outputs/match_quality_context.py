"""The match-quality report's Local context section: Grants per context reason code.

Written as its own delivered CSV (`match_quality_context_<Pull date>.csv`) until
the match-quality report (#37) can carry it as a section; the rows come from
`topo.domain.local_context.context_reason_counts`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from topo.domain.local_context import context_reason_counts
from topo.outputs.delivery import delivery_path, write_new

STEM = "match_quality_context"


def build_context_section(local_context: pl.DataFrame) -> pl.DataFrame:
    return context_reason_counts(local_context).select(
        pl.col("context_reason").alias("Context reason"), pl.col("grants").alias("Grants")
    )


def write_context_section_csv(rows: pl.DataFrame, output_dir: Path, pull_date: dt.date) -> Path:
    path = delivery_path(output_dir, STEM, pull_date, "csv")
    write_new(path, rows.write_csv().encode())
    return path
