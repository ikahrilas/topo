"""Target list: one row per Grant (FAIN) in the reporting window.

This ticket (#29) writes the CSV only. Amount columns are USAspending
obligations by action-date federal fiscal year, labelled "FY2025", never by
academic year. Later tickets add columns (Funding status, Host institution,
label, Priority tier, Local context) and the XLSX workbook.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from topo.domain.grant_universe import GrantUniverse
from topo.fiscal import fy_label
from topo.outputs.delivery import delivery_path, write_new

STEM = "target_list"


def build_target_list(universe: GrantUniverse, as_of: dt.date) -> pl.DataFrame:
    """The target-list rows, in display column order."""
    window = universe.window
    labels = [fy_label(fy) for fy in window.fiscal_years]
    amounts = universe.fy_obligations.with_columns(
        pl.col("fiscal_year").map_elements(fy_label, return_dtype=pl.String).alias("fy")
    )
    wide = (
        amounts.pivot(on="fy", index="fain", values="obligation")
        if amounts.height
        else pl.DataFrame(schema={"fain": pl.String})
    )
    for label in labels:
        if label not in wide.columns:
            wide = wide.with_columns(pl.lit(None, dtype=pl.Float64).alias(label))
    latest = (
        amounts.sort("fiscal_year")
        .group_by("fain")
        .agg(
            pl.col("fy").last().alias("Latest FY"),
            pl.col("obligation").last().alias("Latest FY obligation"),
            pl.col("obligation").sum().alias("Cumulative obligation"),
        )
    )
    grants = universe.grants
    return (
        grants.join(latest, on="fain", how="left")
        .join(wide.select("fain", *labels), on="fain", how="left")
        .with_columns(pl.col(labels).fill_null(0.0), pl.col("Cumulative obligation").fill_null(0.0))
        .sort("recipient_state", "program", "fain", nulls_last=True)
        .select(
            pl.col("recipient_name").alias("Recipient"),
            pl.col("recipient_uei").alias("Recipient UEI"),
            pl.col("recipient_state").alias("State"),
            pl.col("program").alias("Program"),
            pl.col("fain").alias("FAIN"),
            pl.col("project_start").alias("Project start"),
            pl.col("project_end").alias("Project end"),
            "Latest FY",
            "Latest FY obligation",
            "Cumulative obligation",
            *labels,
            pl.col("pull_date").alias("Pull date"),
            pl.lit(as_of).alias("As-of date"),
        )
    )


def write_target_list_csv(rows: pl.DataFrame, output_dir: Path, pull_date: dt.date) -> Path:
    path = delivery_path(output_dir, STEM, pull_date, "csv")
    write_new(path, rows.write_csv().encode())
    return path
