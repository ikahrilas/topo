"""The delivered FAC plausibility table: output/fac_plausibility_<Pull date>.csv.

One row per (Recipient UEI, listing) in both sources, labelled "plausibility, not
reconciliation". It has a Flag (`review` / `not flagged`), never a Reconciliation status.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from topo.outputs.delivery import delivery_path, write_new

STEM = "fac_plausibility"


def _fixed(column: str, decimals: int) -> pl.Expr:
    return pl.col(column).map_elements(lambda v: f"{v:.{decimals}f}", return_dtype=pl.String)


def plausibility_display(table: pl.DataFrame) -> pl.DataFrame:
    return table.select(
        pl.col("check").alias("Check"),
        pl.col("basis").alias("Basis"),
        pl.col("recipient_uei").alias("Recipient UEI"),
        pl.col("recipient_name").alias("Recipient"),
        pl.col("fac_auditee_name").alias("FAC auditee"),
        pl.col("listing").alias("Listing"),
        pl.col("programs").alias("Programs"),
        pl.format("FY{}-FY{}", "span_start_fy", "span_end_fy").alias("Span"),
        _fixed("usaspending_obligation", 2).alias("USAspending obligation"),
        _fixed("fac_amount_expended", 2).alias("FAC amount expended"),
        pl.col("fac_audit_years").alias("FAC audit years"),
        _fixed("ratio", 2).alias("Ratio"),
        pl.col("flag").alias("Flag"),
        pl.col("note").alias("Note"),
    )


def write_plausibility_csv(table: pl.DataFrame, output_dir: Path, pull_date: dt.date) -> Path:
    path = delivery_path(output_dir, STEM, pull_date, "csv")
    write_new(path, plausibility_display(table).write_csv().encode())
    return path
