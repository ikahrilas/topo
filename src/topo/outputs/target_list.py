"""Target list: one row per Grant (FAIN) in the reporting window.

This ticket (#29) writes the CSV only. Amount columns are USAspending
obligations by action-date federal fiscal year, labelled "FY2025", never by
academic year. Funding status, Latest readable status, Readable from,
Lifecycle stage and the 2025–26 disruption marker come from the Funding status
reader (#31). Host institution, Host ID, Host confidence and Case label come
from Host linking (#32). Later tickets add columns (Priority tier, Local
context) and the XLSX workbook.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from topo.domain.grant_universe import GrantUniverse
from topo.fiscal import fy_label
from topo.guards import StructuralBreak
from topo.outputs.delivery import delivery_path, write_new

STEM = "target_list"


FUNDING_COLUMNS = {  # joined grant_funding_status column -> display column
    "funding_status": "Funding status",
    "latest_readable_status": "Latest readable status",
    "readable_from": "Readable from",
    "lifecycle_stage": "Lifecycle stage",
    "disruption": "2025–26 disruption",
}

TIMING_COLUMNS = {  # joined renewal_timing column -> display column (#40)
    "re_competing_soon": "Re-competing soon",
    "predicted_due_date": "Predicted due date",
    "evidence_tier": "Evidence tier",
    "predicted_competition_fy": "Predicted competition FY",
    "timing": "Renewal timing",
    "end_date_fact": "End date",
}


def build_target_list(
    universe: GrantUniverse,
    as_of: dt.date,
    *,
    host_links: pl.DataFrame,
    funding: pl.DataFrame | None = None,
    timing: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """The target-list rows, in display column order.

    `host_links` is the joined Host-links table (topo.domain.host_linking.HostLinks),
    one row per FAIN; the Host sits next to the Recipient name and UEI.
    `funding` is the joined grant_funding_status table (one row per FAIN).
    `timing` is the joined renewal_timing table (one row per FAIN).
    """
    if funding is None:
        funding = pl.DataFrame(schema={"fain": pl.String, **{c: pl.String for c in FUNDING_COLUMNS}})
    if timing is None:
        timing = pl.DataFrame(schema={"fain": pl.String, "re_competing_soon": pl.Boolean,
                                      "predicted_due_date": pl.Date, "evidence_tier": pl.String,
                                      "predicted_competition_fy": pl.Int64, "timing": pl.String,
                                      "end_date_fact": pl.String})
    timing = timing.select(
        "fain",
        pl.when(pl.col("re_competing_soon")).then(pl.lit("yes")).otherwise(pl.lit("no")).alias("re_competing_soon"),
        "predicted_due_date",
        "evidence_tier",
        pl.concat_str(pl.lit("FY"), pl.col("predicted_competition_fy").cast(pl.String)).alias("predicted_competition_fy"),
        "timing",
        "end_date_fact",
    )
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
    # Every Grant keeps its row whatever its Host outcome (review and unmatched included).
    missing = grants.join(host_links, on="fain", how="anti")
    if missing.height:
        raise StructuralBreak(f"{missing.height} Grants have no Host link: {', '.join(missing['fain'].head(10))}")
    hosts = host_links.select(
        "fain",
        pl.col("host_name").alias("Host institution"),
        pl.concat_str("host_kind", pl.lit(" "), "host_id").alias("Host ID"),
        pl.col("host_confidence").alias("Host confidence"),
        pl.col("case_label").alias("Case label"),
    )
    return (
        grants.join(hosts, on="fain", how="left")
        .join(latest, on="fain", how="left")
        .join(wide.select("fain", *labels), on="fain", how="left")
        .join(funding.select("fain", *FUNDING_COLUMNS), on="fain", how="left")
        .join(timing, on="fain", how="left")
        .with_columns(pl.col(labels).fill_null(0.0), pl.col("Cumulative obligation").fill_null(0.0))
        .sort("recipient_state", "program", "fain", nulls_last=True)
        .select(
            pl.col("recipient_name").alias("Recipient"),
            pl.col("recipient_uei").alias("Recipient UEI"),
            "Host institution",
            "Host ID",
            "Host confidence",
            "Case label",
            pl.col("recipient_state").alias("State"),
            pl.col("program").alias("Program"),
            pl.col("fain").alias("FAIN"),
            pl.col("project_start").alias("Project start"),
            pl.col("project_end").alias("Project end"),
            "Latest FY",
            "Latest FY obligation",
            "Cumulative obligation",
            *labels,
            *(pl.col(src).alias(shown) for src, shown in FUNDING_COLUMNS.items()),
            *(pl.col(src).alias(shown) for src, shown in TIMING_COLUMNS.items()),
            pl.col("pull_date").alias("Pull date"),
            pl.lit(as_of).alias("As-of date"),
        )
    )


def write_target_list_csv(rows: pl.DataFrame, output_dir: Path, pull_date: dt.date) -> Path:
    path = delivery_path(output_dir, STEM, pull_date, "csv")
    write_new(path, rows.write_csv().encode())
    return path
