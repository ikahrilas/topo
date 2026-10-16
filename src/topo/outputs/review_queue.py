"""Review queue: every Grant whose Host link is still `review`, with its candidates and their signals.

One row per (FAIN, candidate); a review Grant with no candidate (a demoted
"no single Host" label, say) still gets one row with the candidate cells blank.
Grants are ordered by dollars (cumulative obligation over the reporting
window), then by Succession impact, then FAIN, and numbered by that order in
`Priority`.

Succession impact (ASSUMPTION): the number of other Grants, in the window or
the lookback, with the same Recipient (UEI, else name) and Program. A Succession
(#39) needs the same Host on both Grants and a review Grant's Host is unsettled, so
these are the Succession links this one decision can make or break.

Reviewers record decisions in data/curated/host_overrides.csv; an overridden
Grant leaves the queue on the next run. Unreviewed Grants stay `review`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from topo.domain.host_linking import REVIEW
from topo.outputs.delivery import delivery_path, write_new

STEM = "review_queue"


def grant_dollars(grants: pl.DataFrame, fy_obligations: pl.DataFrame) -> pl.DataFrame:
    """fain -> dollars: obligations over the reporting-window fiscal years (0 when none)."""
    sums = fy_obligations.group_by("fain").agg(pl.col("obligation").sum().alias("dollars"))
    return grants.select("fain").join(sums, on="fain", how="left").with_columns(pl.col("dollars").fill_null(0.0))


def succession_impact(pool: pl.DataFrame) -> pl.DataFrame:
    """fain -> other Grants in the pool sharing its Recipient (UEI, else name) and Program."""
    recipient = pl.coalesce(pl.col("recipient_uei"), pl.col("recipient_name"))
    return pool.select(
        "fain",
        (pl.len().over(recipient, "program") - 1).cast(pl.Int64).alias("succession_impact"),
    )


def build_review_queue(
    host_links: pl.DataFrame,
    candidates: pl.DataFrame,
    grants: pl.DataFrame,
    fy_obligations: pl.DataFrame,
    *,
    succession_pool: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Review Grants with their candidates, in priority order.

    `succession_pool` is every Grant a Succession could link (in-window plus
    lookback); it defaults to `grants`.
    """
    pool = grants if succession_pool is None else succession_pool
    queue = (
        host_links.filter(pl.col("outcome") == REVIEW)
        .select("fain", "case_label", "gating")
        .join(grants.select("fain", "recipient_name", "recipient_uei", "recipient_state", "program"), on="fain")
        .join(grant_dollars(grants, fy_obligations), on="fain")
        .join(succession_impact(pool), on="fain")
        .sort(["dollars", "succession_impact", "fain"], descending=[True, True, False])
        .with_row_index("priority", offset=1)
    )
    return (
        queue.join(candidates, on="fain", how="left")
        .sort("priority", "host_kind", "host_id", nulls_last=True)
        .select(
            pl.col("priority").cast(pl.Int64).alias("Priority"),
            pl.col("fain").alias("FAIN"),
            pl.col("recipient_name").alias("Recipient"),
            pl.col("recipient_uei").alias("Recipient UEI"),
            pl.col("recipient_state").alias("State"),
            pl.col("program").alias("Program"),
            pl.col("case_label").alias("Case label"),
            pl.col("gating").alias("Gating"),
            pl.col("dollars").alias("Dollars"),
            pl.col("succession_impact").alias("Succession impact"),
            pl.concat_str("host_kind", pl.lit(" "), "host_id").alias("Candidate host ID"),
            pl.col("host_name").alias("Candidate host"),
            pl.col("signals").alias("Signals"),
        )
    )


def write_review_queue_csv(rows: pl.DataFrame, output_dir: Path, pull_date: dt.date) -> Path:
    path = delivery_path(output_dir, STEM, pull_date, "csv")
    write_new(path, rows.write_csv().encode())
    return path
