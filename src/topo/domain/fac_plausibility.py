"""FAC plausibility check (#43): a third source compared without pass/fail.

FAC's audited amount expended and USAspending's obligations measure different
things on different calendars (docs/research/federal-audit-clearinghouse.md §7),
so they are never reconciled. Over a span of fiscal years they should be of the
same size, which is all this check asks.

One row per (Recipient UEI, listing) for UEIs present in both sources over the span:
    - USAspending: the window's action-date FY obligations of in-universe Grants,
      grouped by the Grant's Recipient UEI and listing.
    - FAC: direct SEFA lines only (`is_direct = Y`; pass-through money is not a
      prime award), grouped by auditee UEI and listing, audit year N read as FY N.
A UEI is in both sources when it has obligations in the span and direct lines in
the span. Ratio = FAC amount expended / USAspending obligation. A ratio outside
[low, high], or no positive obligation to divide by, is flagged `review`; nothing
passes or fails, and no row carries a Reconciliation status.

Span: `plausibility_years` fiscal years ending `audit_lag_years` before the last
ended FY of the reporting window (the latest audit year is still being filed),
clipped to the window.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandera.polars as pa
import polars as pl

from topo.domain.programs import PROGRAMS
from topo.fiscal import ReportingWindow, fy_label
from topo.guards import check_schema

CHECK = "fac_plausibility"
BASIS = "plausibility, not reconciliation"
REVIEW = "review"
NOT_FLAGGED = "not flagged"
DROP_NOT_DIRECT = "not_direct"
DROP_OUTSIDE_SPAN = "outside_span"
DROP_UEI_NOT_IN_BOTH = "uei_not_in_both_sources"


@dataclass(frozen=True)
class PlausibilitySettings:
    years: int = 5
    audit_lag_years: int = 1
    ratio_low: float = 0.5
    ratio_high: float = 1.5

    @classmethod
    def from_section(cls, section: dict) -> "PlausibilitySettings":
        return cls(
            years=int(section["plausibility_years"]),
            audit_lag_years=int(section["audit_lag_years"]),
            ratio_low=float(section["plausibility_ratio_low"]),
            ratio_high=float(section["plausibility_ratio_high"]),
        )


@dataclass(frozen=True)
class Span:
    start_fy: int
    end_fy: int

    @classmethod
    def of(cls, window: ReportingWindow, settings: PlausibilitySettings) -> "Span":
        end = window.end_fy - settings.audit_lag_years
        return cls(max(end - settings.years + 1, window.start_fy), end)

    @property
    def label(self) -> str:
        return f"{fy_label(self.start_fy)}-{fy_label(self.end_fy)}"

    def holds(self, column: str) -> pl.Expr:
        return pl.col(column).is_between(self.start_fy, self.end_fy)


class FacPlausibility(pa.DataFrameModel):
    """One row per (Recipient UEI, listing) present in both sources over the span."""

    check: str = pa.Field(isin=[CHECK])
    basis: str = pa.Field(isin=[BASIS])
    recipient_uei: str
    recipient_name: str = pa.Field(nullable=True)
    fac_auditee_name: str = pa.Field(nullable=True)
    listing: str
    programs: str
    span_start_fy: int
    span_end_fy: int
    usaspending_obligation: float
    fac_amount_expended: float
    fac_audit_years: int
    ratio: float = pa.Field(nullable=True)
    flag: str = pa.Field(isin=[REVIEW, NOT_FLAGGED])
    note: str

    class Config:
        strict = True
        unique = ["recipient_uei", "listing"]


@dataclass(frozen=True)
class PlausibilityResult:
    table: pl.DataFrame
    lines_in: int
    lines_compared: int
    drops: dict[str, int]


def _listing_programs() -> pl.DataFrame:
    by_listing: dict[str, list[str]] = {}
    for program in PROGRAMS:
        by_listing.setdefault(program.listing, []).append(program.name)
    return pl.DataFrame({"listing": list(by_listing), "listing_programs": ["; ".join(v) for v in by_listing.values()]})


def build_fac_plausibility(
    grants: pl.DataFrame,
    fy_obligations: pl.DataFrame,
    fac_lines: pl.DataFrame,
    fac_audits: pl.DataFrame,
    span: Span,
    settings: PlausibilitySettings,
) -> PlausibilityResult:
    obligated = (
        fy_obligations.filter(span.holds("fiscal_year"))
        .join(grants.select("fain", "recipient_uei", "recipient_name", "listing", "program", "project_start"), on="fain")
        .filter(pl.col("recipient_uei").is_not_null())
    )
    usaspending = obligated.group_by("recipient_uei", "listing").agg(
        pl.col("obligation").sum().alias("usaspending_obligation"),
        pl.col("program").unique().sort().str.join("; ").alias("grant_programs"),
    )
    names = (
        obligated.sort("project_start", "fain", descending=True)
        .group_by("recipient_uei", maintain_order=True).first()
        .select("recipient_uei", "recipient_name")
    )

    direct = pl.col("is_direct")
    in_span = span.holds("audit_year")
    candidates = fac_lines.filter(direct & in_span & pl.col("auditee_uei").is_not_null())
    shared = (
        set(usaspending["recipient_uei"].to_list()) & set(candidates["auditee_uei"].to_list())
    )
    compared = candidates.filter(pl.col("auditee_uei").is_in(sorted(shared)))
    # Drops are counted on the cleaned lines in their own pass, not from `compared`.
    drops = {
        DROP_NOT_DIRECT: fac_lines.filter(~direct).height,
        DROP_OUTSIDE_SPAN: fac_lines.filter(direct & ~in_span).height,
        DROP_UEI_NOT_IN_BOTH: fac_lines.filter(
            direct & in_span & ~pl.col("auditee_uei").is_in(sorted(shared)).fill_null(False)
        ).height,
    }
    fac = compared.rename({"auditee_uei": "recipient_uei"}).group_by("recipient_uei", "listing").agg(
        pl.col("amount_expended").sum().cast(pl.Float64).alias("fac_amount_expended"),
        pl.col("audit_year").n_unique().cast(pl.Int64).alias("fac_audit_years"),
    )
    auditees = (
        fac_audits.filter(span.holds("audit_year") & pl.col("auditee_uei").is_in(sorted(shared)))
        .sort("audit_year", "report_id", descending=True)
        .group_by("auditee_uei", maintain_order=True).first()
        .select(pl.col("auditee_uei").alias("recipient_uei"), pl.col("auditee_name").alias("fac_auditee_name"))
    )

    low, high = settings.ratio_low, settings.ratio_high
    obligation, expended = pl.col("usaspending_obligation"), pl.col("fac_amount_expended")
    ratio = pl.when(obligation > 0).then(expended / obligation)
    table = (
        usaspending.filter(pl.col("recipient_uei").is_in(sorted(shared)))
        .join(fac, on=["recipient_uei", "listing"], how="full", coalesce=True)
        .join(names, on="recipient_uei", how="left")
        .join(auditees, on="recipient_uei", how="left")
        .join(_listing_programs(), on="listing", how="left")
        .with_columns(
            pl.lit(CHECK).alias("check"),
            pl.lit(BASIS).alias("basis"),
            pl.coalesce("grant_programs", "listing_programs").alias("programs"),
            pl.lit(span.start_fy).cast(pl.Int64).alias("span_start_fy"),
            pl.lit(span.end_fy).cast(pl.Int64).alias("span_end_fy"),
            obligation.fill_null(0.0),
            expended.fill_null(0.0),
            pl.col("fac_audit_years").fill_null(0),
        )
        .with_columns(ratio.alias("ratio"))
        .with_columns(
            pl.when(pl.col("ratio").is_null() | (pl.col("ratio") < low) | (pl.col("ratio") > high))
            .then(pl.lit(REVIEW)).otherwise(pl.lit(NOT_FLAGGED)).alias("flag"),
            pl.when(pl.col("ratio").is_null())
            .then(pl.lit(f"no positive USAspending obligation over {span.label} to compare with; "))
            .when(pl.col("ratio") < low).then(pl.format("ratio {} is under {}; ", pl.col("ratio").round(2), pl.lit(low)))
            .when(pl.col("ratio") > high).then(pl.format("ratio {} is over {}; ", pl.col("ratio").round(2), pl.lit(high)))
            .otherwise(pl.lit(f"ratio within {low}-{high}; "))
            .add(pl.lit(
                f"FAC direct-line amount expended (audit years {span.start_fy}-{span.end_fy}, read as federal FYs) "
                f"over USAspending action-date obligations ({span.label}); different measures and calendars, "
                "so plausibility only, never pass/fail"
            )).alias("note"),
        )
        .select(list(FacPlausibility.to_schema().columns))
        .sort("recipient_uei", "listing")
    )
    table = check_schema(FacPlausibility, table, "FAC plausibility")
    return PlausibilityResult(table=table, lines_in=fac_lines.height, lines_compared=compared.height, drops=drops)
