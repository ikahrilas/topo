"""Grant universe: which funding actions are TRIO/GEAR UP Grants, one row per FAIN.

Input is the cleaned USAspending actions table. Selection is by assistance
listing number plus FAIN prefix (topo.domain.programs), never by awarding
agency. A Grant is in the universe when its project period overlaps the
reporting window, so Grants awarded before the window start stay in.

Outputs (all carry the FAIN; actions also carry the transaction key):
    grants          one row per FAIN: Program, Recipient, project period
    grant_actions   every action of every Grant (lookback and current FY too),
                    each with the Budget period it funds and its action-date FY
    fy_obligations  obligations summed by FAIN and action-date federal FY,
                    reporting-window fiscal years only
    exceptions      actions on a TRIO/GEAR UP listing whose FAIN prefix names
                    no Program; kept visible, never silently dropped
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandera.polars as pa
import polars as pl

from topo.domain.programs import DOL_AGENCY_CODE, ED_FAIN_PATTERN, PROGRAMS, SOLE_PROGRAM_OF_LISTING
from topo.fiscal import ReportingWindow, fy_start
from topo.guards import check_schema, check_unique


class Grants(pa.DataFrameModel):
    """The Grant table: one row per FAIN."""

    fain: str = pa.Field(unique=True)
    award_key: str
    program: str
    program_family: str
    listing: str
    recipient_name: str = pa.Field(nullable=True)
    recipient_uei: str = pa.Field(nullable=True)
    recipient_state: str = pa.Field(nullable=True)
    project_start: dt.date
    project_end: dt.date
    awarding_agency_code: str = pa.Field(nullable=True)
    pull_date: dt.date

    class Config:
        strict = True


class GrantActions(pa.DataFrameModel):
    """Each funding action of a Grant with the Budget period it funds."""

    transaction_key: str = pa.Field(unique=True)
    fain: str
    award_key: str
    program: str
    modification_number: str = pa.Field(nullable=True)
    action_date: dt.date
    action_fy: int
    action_type: str = pa.Field(nullable=True)
    obligation: float
    budget_period_start: dt.date = pa.Field(nullable=True)
    budget_period_end: dt.date = pa.Field(nullable=True)

    class Config:
        strict = True


class FyObligations(pa.DataFrameModel):
    """Obligations by FAIN and action-date federal FY (reporting window only)."""

    fain: str
    fiscal_year: int
    obligation: float

    class Config:
        strict = True
        unique = ["fain", "fiscal_year"]


EXCEPTION_UNKNOWN_FAIN_PREFIX = "fain_prefix_names_no_program"


@dataclass(frozen=True)
class GrantUniverse:
    grants: pl.DataFrame
    grant_actions: pl.DataFrame
    fy_obligations: pl.DataFrame
    exceptions: pl.DataFrame
    window: ReportingWindow


_PROGRAM_TABLE = pl.DataFrame(
    {
        "listing": [p.listing for p in PROGRAMS],
        "fain_prefix": [p.fain_prefix for p in PROGRAMS],
        "program": [p.name for p in PROGRAMS],
        "program_family": [p.family for p in PROGRAMS],
    }
)


_SOLE_PROGRAM_TABLE = pl.DataFrame(
    {
        "listing": list(SOLE_PROGRAM_OF_LISTING),
        "sole_program": [p.name for p in SOLE_PROGRAM_OF_LISTING.values()],
        "sole_program_family": [p.family for p in SOLE_PROGRAM_OF_LISTING.values()],
    }
)


def _label(actions: pl.DataFrame) -> pl.DataFrame:
    """Every action with its Program (null when listing and FAIN name none).

    ED FAINs: listing plus FAIN prefix. DOL-style FAINs (DOL awarding, no ED FAIN
    format): the listing's Program when the listing names only one (programs.py).
    """
    dol_style = (pl.col("awarding_agency_code") == DOL_AGENCY_CODE) & ~pl.col("fain").str.to_uppercase().str.contains(
        ED_FAIN_PATTERN
    )
    return (
        actions.with_columns(pl.col("fain").str.slice(0, 5).str.to_uppercase().alias("fain_prefix"))
        .join(_PROGRAM_TABLE, on=["listing", "fain_prefix"], how="left")
        .join(_SOLE_PROGRAM_TABLE, on="listing", how="left")
        .with_columns(
            pl.when(pl.col("program").is_null() & dol_style.fill_null(False))
            .then(pl.col("sole_program")).otherwise(pl.col("program")).alias("program"),
            pl.when(pl.col("program").is_null() & dol_style.fill_null(False))
            .then(pl.col("sole_program_family")).otherwise(pl.col("program_family")).alias("program_family"),
        )
        .drop("sole_program", "sole_program_family")
    )


def _per_award(selected: pl.DataFrame) -> pl.DataFrame:
    """One row per award: Program, Recipient (from the latest action) and project period."""
    # The latest action names the Recipient (name drift over a project period is common).
    latest_first = selected.sort(
        "action_date", pl.col("modification_number").cast(pl.Int64, strict=False), descending=True,
        nulls_last=True,
    )
    return (
        latest_first.group_by("award_key", "fain", "program", "program_family", "listing", maintain_order=True)
        .agg(
            pl.col("recipient_name").drop_nulls().first(),
            pl.col("recipient_uei").drop_nulls().first(),
            pl.col("recipient_state").drop_nulls().first(),
            pl.col("awarding_agency_code").first(),
            pl.coalesce("budget_period_start", "action_date").min().alias("project_start"),
            pl.coalesce("budget_period_end", "action_date").max().alias("project_end"),
            pl.col("pull_date").max(),
        )
    )


def build_grant_universe(actions: pl.DataFrame, window: ReportingWindow) -> GrantUniverse:
    """Select, label and roll up TRIO/GEAR UP funding actions into Grants."""
    labelled = _label(actions)
    exceptions = labelled.filter(pl.col("program").is_null()).select(
        "transaction_key", "fain", "listing", "awarding_agency_code", "action_date", "obligation",
        pl.lit(EXCEPTION_UNKNOWN_FAIN_PREFIX).alias("reason"),
    )
    selected = labelled.filter(pl.col("program").is_not_null())
    per_award = _per_award(selected)
    in_window = per_award.filter(
        (pl.col("project_start") <= window.end) & (pl.col("project_end") >= window.start)
    )
    # One award key and one Program per FAIN; anything else is a structural break.
    check_unique(in_window, "fain", "Grant table")
    grants = check_schema(
        Grants, in_window.select(list(Grants.to_schema().columns)).sort("fain"), "Grant table"
    )

    grant_actions = check_schema(
        GrantActions,
        selected.join(grants.select("fain"), on="fain", how="semi")
        .select(list(GrantActions.to_schema().columns))
        .sort("fain", "action_date", "transaction_key"),
        "Grant actions",
    )

    fy_obligations = check_schema(
        FyObligations,
        grant_actions.filter(pl.col("action_fy").is_between(window.start_fy, window.end_fy))
        .group_by("fain", pl.col("action_fy").alias("fiscal_year"))
        .agg(pl.col("obligation").sum())
        .sort("fain", "fiscal_year"),
        "FY obligations",
    )
    return GrantUniverse(grants, grant_actions, fy_obligations, exceptions, window)


@dataclass(frozen=True)
class Lookback:
    """Grants whose project period ended before the reporting window but not before the lookback horizon.

    Read only for Succession links and Cohort starts: they get no amount
    columns, no target-list row and no reconciliation row.
    """

    grants: pl.DataFrame  # Grants schema
    grant_actions: pl.DataFrame  # GrantActions schema


def build_lookback(
    actions: pl.DataFrame, window: ReportingWindow, from_fy_by_family: dict[str, int]
) -> Lookback:
    """Lookback Grants: project period inside [lookback horizon of its Program family, window start)."""
    selected = _label(actions).filter(pl.col("program").is_not_null())
    horizon = pl.col("program_family").replace_strict(
        {family: fy_start(fy) for family, fy in from_fy_by_family.items()}, return_dtype=pl.Date
    )
    lookback = _per_award(selected).filter(
        (pl.col("project_end") < window.start) & (pl.col("project_end") >= horizon)
    )
    check_unique(lookback, "fain", "Lookback Grant table")
    grants = check_schema(
        Grants, lookback.select(list(Grants.to_schema().columns)).sort("fain"), "Lookback Grant table"
    )
    grant_actions = check_schema(
        GrantActions,
        selected.join(grants.select("fain"), on="fain", how="semi")
        .select(list(GrantActions.to_schema().columns))
        .sort("fain", "action_date", "transaction_key"),
        "Lookback Grant actions",
    )
    return Lookback(grants, grant_actions)
