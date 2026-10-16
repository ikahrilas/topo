"""The Funding status history: an append-only snapshot of every run's reading (ADR 0003).

One row per (FAIN, Budget period, As-of date). Each run appends the rows whose
key isn't there yet; existing rows are never changed, so a rerun under the same
As-of date adds nothing and any published reading can be reproduced.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from topo.guards import check_unique

FILENAME = "funding_status_history.parquet"
KEY = ["fain", "budget_period_start", "as_of_date"]


def history_path(output_dir: Path) -> Path:
    return output_dir / FILENAME


def append_funding_status_history(
    periods: pl.DataFrame, output_dir: Path, as_of: dt.date, pull_date: dt.date
) -> pl.DataFrame:
    """Append this run's (FAIN, Budget period) readings under its As-of date; returns the rows added."""
    snapshot = periods.select(
        "fain",
        "budget_period_start",
        "budget_period_end",
        pl.lit(as_of).alias("as_of_date"),
        "funding_status",
        "readable_from",
        "disrupted",
        pl.lit(pull_date).alias("pull_date"),
    )
    path = history_path(output_dir)
    existing = pl.read_parquet(path) if path.exists() else snapshot.clear()
    added = snapshot.join(existing.select(KEY), on=KEY, how="anti")
    combined = pl.concat([existing, added], how="vertical")
    check_unique(combined, KEY, "Funding status history")
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    combined.write_parquet(tmp)
    tmp.replace(path)
    return added
