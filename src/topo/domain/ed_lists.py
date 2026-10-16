"""ED TRIO grantee lists joined to the Grant universe by exact FAIN.

The record stays USAspending: an ED list never creates a Grant. A list's
"Recipient/ campus" text and participant counts become Grant-year attributes,
blank (never zero) in years with no list or where the Grant isn't on the list.
Its amounts stay in the cleaned table for reconciliation (#42) and are not
carried here, so they can't reach the target list. A FAIN on a list that is
never in USAspending is an exception, kept out of the Grant table.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandera.polars as pa
import polars as pl

from topo.fiscal import ReportingWindow
from topo.guards import check_schema, check_unique

NOT_IN_USASPENDING = "ed_list_fain_not_in_usaspending"


class GrantYearEdAttributes(pa.DataFrameModel):
    """One row per (Grant, reporting-window FY): what the ED TRIO list says, if anything."""

    fain: str
    fiscal_year: int
    ed_list_filed: bool  # a FAIN-level ED list is filed for the Grant's Program and this FY
    ed_list_row_id: str = pa.Field(nullable=True)
    ed_recipient_campus: str = pa.Field(nullable=True)  # ED's "Recipient/ campus" text
    ed_campus: str = pa.Field(nullable=True)
    ed_participants: int = pa.Field(nullable=True, ge=0)

    class Config:
        strict = True


class EdListExceptions(pa.DataFrameModel):
    """ED list rows whose FAIN is never in USAspending; kept out of the Grant table."""

    list_row_id: str = pa.Field(unique=True)
    fain: str
    program: str
    fiscal_year: int
    ed_recipient_campus: str
    state: str
    reason: str = pa.Field(isin=[NOT_IN_USASPENDING])

    class Config:
        strict = True


@dataclass(frozen=True)
class EdListJoin:
    grant_year_attributes: pl.DataFrame
    exceptions: pl.DataFrame


def join_ed_lists(
    grants: pl.DataFrame,
    usaspending_fains: pl.Series,
    trio_list_rows: pl.DataFrame,
    coverage: pl.DataFrame,
    window: ReportingWindow,
) -> EdListJoin:
    """Grant-year ED attributes over the reporting window, and the ED-list-only FAIN exceptions."""
    years = pl.DataFrame({"fiscal_year": list(window.fiscal_years)}, schema={"fiscal_year": pl.Int64})
    filed = (
        coverage.filter(pl.col("status") == "ok")
        .select("program", "fiscal_year")
        .unique()
        .with_columns(pl.lit(True).alias("ed_list_filed"))
    )
    on_list = trio_list_rows.select(
        "fain",
        "fiscal_year",
        pl.col("list_row_id").alias("ed_list_row_id"),
        pl.col("recipient_campus").alias("ed_recipient_campus"),
        "ed_campus",
        pl.col("participants").alias("ed_participants"),
    )
    attributes = (
        grants.select("fain", "program")
        .join(years, how="cross")
        .join(filed, on=["program", "fiscal_year"], how="left")
        .join(on_list, on=["fain", "fiscal_year"], how="left")
        .with_columns(pl.col("ed_list_filed").fill_null(False))
        .select(list(GrantYearEdAttributes.to_schema().columns))
        .sort("fain", "fiscal_year")
    )
    check_unique(attributes, ["fain", "fiscal_year"], "Grant-year ED attributes")
    attributes = check_schema(GrantYearEdAttributes, attributes, "Grant-year ED attributes")

    exceptions = (
        trio_list_rows.filter(~pl.col("fain").is_in(usaspending_fains.implode()))
        .select(
            "list_row_id",
            "fain",
            "program",
            "fiscal_year",
            pl.col("recipient_campus").alias("ed_recipient_campus"),
            "state",
            pl.lit(NOT_IN_USASPENDING).alias("reason"),
        )
        .sort("program", "fiscal_year", "fain")
    )
    exceptions = check_schema(EdListExceptions, exceptions, "ED list exceptions")
    return EdListJoin(grant_year_attributes=attributes, exceptions=exceptions)
