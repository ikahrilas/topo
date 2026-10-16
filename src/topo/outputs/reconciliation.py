"""The delivered reconciliation table: output/reconciliation_<Pull date>.csv (one row per check, Program, FY).

Values are written with two decimals; a blank cell is a value that does not apply
(e.g. no unallocated remainder on an overage), never a missing figure: those
rows read `not_published` or `no_ed_list`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from topo.outputs.delivery import delivery_path, write_new

STEM = "reconciliation"
EVIDENCE_STEM = "unfunded_ed_list_evidence"

_MONEY = {
    "reference_value": "Reference value",
    "compared_value": "Compared value",
    "gap": "Gap",
    "tolerance": "Tolerance",
    "budget_period_value": "Budget-period value",
    "budget_period_gap": "Budget-period gap",
    "unallocated_remainder": "Unallocated remainder",
}


def _amount(column: str) -> pl.Expr:
    return pl.col(column).round(2).map_elements(lambda v: f"{v:.2f}", return_dtype=pl.String)


def reconciliation_display(table: pl.DataFrame) -> pl.DataFrame:
    return table.select(
        pl.col("check").alias("Check"),
        pl.col("program").alias("Program"),
        pl.when(pl.col("span_start_fy").is_not_null())
        .then(pl.format("FY{}-FY{}", pl.col("span_start_fy"), pl.col("fiscal_year")))
        .otherwise(pl.format("FY{}", pl.col("fiscal_year"))).alias("FY"),
        pl.col("reference_source").alias("Reference source"),
        _amount("reference_value").alias(_MONEY["reference_value"]),
        pl.col("compared_source").alias("Compared source"),
        *(_amount(column).alias(label) for column, label in _MONEY.items() if column != "reference_value"),
        pl.col("reconciliation_status").alias("Reconciliation status"),
        pl.col("gap_reason_code").alias("Gap reason code"),
        pl.col("note").alias("Note"),
    ).select(
        "Check", "Program", "FY", "Reference source", "Reference value", "Compared source", "Compared value",
        "Gap", "Tolerance", "Budget-period value", "Budget-period gap", "Unallocated remainder",
        "Reconciliation status", "Gap reason code", "Note",
    )


def write_reconciliation_csv(table: pl.DataFrame, output_dir: Path, pull_date: dt.date) -> Path:
    path = delivery_path(output_dir, STEM, pull_date, "csv")
    write_new(path, reconciliation_display(table).write_csv().encode())
    return path


def evidence_display(evidence: pl.DataFrame) -> pl.DataFrame:
    return evidence.select(
        pl.col("program").alias("Program"),
        pl.when(pl.col("fiscal_year").is_null()).then(pl.lit("")).otherwise(pl.format("FY{}", pl.col("fiscal_year")))
        .alias("FY"),
        pl.col("unfunded_budget_periods").alias("Unfunded Budget periods"),
        pl.col("with_ed_list_evidence").alias("With ED-list evidence"),
        pl.col("share").map_elements(lambda v: f"{v:.4f}", return_dtype=pl.String).alias("Share"),
        pl.when(pl.col("large")).then(pl.lit("yes")).otherwise(pl.lit("no")).alias("Large"),
    )


def write_evidence_csv(evidence: pl.DataFrame, output_dir: Path, pull_date: dt.date) -> Path:
    path = delivery_path(output_dir, EVIDENCE_STEM, pull_date, "csv")
    write_new(path, evidence_display(evidence).write_csv().encode())
    return path
