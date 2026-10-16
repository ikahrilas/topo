"""Succession builder: renewal history read across the lookback.

A **Succession** links a Grant to the Grant that renewed it: same Recipient,
same Program, same Host institution, in a later competition. Lookback Grants
(project period ended before the reporting window, back to FY2010 for TRIO and
FY2015 for GEAR UP) take part here and in Cohort starts only.

Tables (all keyed by FAIN):
    successions     fain -> successor_fain (one predecessor and one successor at most)
    cohort_starts   per Program: competition FY, the Cohort's start date, new Grants
    grant_cohorts   each Grant's Cohort (the latest Cohort start FY at or before its A1's FY)
    hand_offs       a full negative on one FAIN matched to the cent by a same-day A1
                    on another FAIN of the same Program (the old FAIN handed its
                    project to a new one, often to a different Recipient)

The Funding status reader's Succession exclusion is fed the A1s of each FAIN's
linked successors (Succession links plus hand-offs), via `successor_fains`.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import pandera.polars as pa
import polars as pl

from topo.domain.host_linking import name_key
from topo.domain.programs import GEAR_UP, TRIO
from topo.fiscal import fiscal_year
from topo.guards import check_schema


@dataclass(frozen=True)
class LookbackSettings:
    """`[lookback]` in config.toml."""

    trio_from_fy: int
    gear_up_from_fy: int
    cohort_min_share: float

    @classmethod
    def from_section(cls, section: dict[str, Any]) -> "LookbackSettings":
        return cls(
            trio_from_fy=int(section["trio_from_fy"]),
            gear_up_from_fy=int(section["gear_up_from_fy"]),
            cohort_min_share=float(section["cohort_min_share"]),
        )

    @classmethod
    def from_config(cls, config) -> "LookbackSettings":
        return cls.from_section(config.section("lookback"))

    @property
    def from_fy_by_family(self) -> dict[str, int]:
        return {TRIO: self.trio_from_fy, GEAR_UP: self.gear_up_from_fy}


class Successions(pa.DataFrameModel):
    fain: str = pa.Field(unique=True)
    successor_fain: str = pa.Field(unique=True)
    program: str
    host_kind: str
    host_id: str

    class Config:
        strict = True


class CohortStarts(pa.DataFrameModel):
    program: str
    cohort_fy: int
    cohort_start: dt.date
    new_grants: int

    class Config:
        strict = True
        unique = ["program", "cohort_fy"]


class GrantCohorts(pa.DataFrameModel):
    fain: str = pa.Field(unique=True)
    program: str
    a1_fy: int = pa.Field(nullable=True)
    cohort_fy: int = pa.Field(nullable=True)

    class Config:
        strict = True


class HandOffs(pa.DataFrameModel):
    fain: str
    successor_fain: str
    program: str
    action_date: dt.date
    amount: float

    class Config:
        strict = True
        unique = ["fain", "successor_fain", "action_date"]


def derive_cohorts(
    grants: pl.DataFrame, grant_actions: pl.DataFrame, min_share: float
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Cohort starts per Program, and each Grant's Cohort.

    A Grant's new award is its earliest A1; the competition FY is that A1's
    action-date FY. An FY is a Cohort start for a Program when its count of new
    awards is at least `min_share` of the Program's largest yearly count (TRIO
    competes its whole Cohort at once; later awards from the unfunded-application
    list are few and join the Cohort before them). The Cohort's start date is the
    most common Budget period start of those A1s (earliest on a tie). A Grant with
    no A1 in the pulled data started before the lookback and has no Cohort.
    """
    a1s = (
        grant_actions.filter(pl.col("action_type") == "A1")
        .sort("action_date")
        .group_by("fain", maintain_order=True)
        .agg(pl.col("action_fy").first().alias("a1_fy"),
             pl.coalesce("budget_period_start", "action_date").first().alias("start"))
    )
    new_awards = grants.select("fain", "program").join(a1s, on="fain", how="inner")
    per_fy = new_awards.group_by("program", "a1_fy").agg(
        pl.len().alias("new_grants"),
        pl.col("start").mode().min().alias("cohort_start"),
    )
    cohort_starts = (
        per_fy.filter(pl.col("new_grants") >= pl.col("new_grants").max().over("program") * min_share)
        .select("program", pl.col("a1_fy").alias("cohort_fy"), "cohort_start",
                pl.col("new_grants").cast(pl.Int64))
        .sort("program", "cohort_fy")
    )
    grant_cohorts = (
        grants.select("fain", "program")
        .join(a1s.select("fain", "a1_fy"), on="fain", how="left")
        .sort("a1_fy", nulls_last=True)
        .join_asof(
            cohort_starts.select("program", pl.col("cohort_fy"), pl.col("cohort_fy").alias("_on")).sort("_on"),
            left_on="a1_fy", right_on="_on", by="program", strategy="backward",
        )
        .select("fain", "program", pl.col("a1_fy").cast(pl.Int64), pl.col("cohort_fy").cast(pl.Int64))
        .sort("fain")
    )
    return (
        check_schema(CohortStarts, cohort_starts, "Cohort starts"),
        check_schema(GrantCohorts, grant_cohorts, "Grant Cohorts"),
    )


def _same_recipient(a: dict, b: dict) -> bool:
    """Same UEI when both have one; else the same name in the same state (pre-UEI lookback Grants)."""
    if a["recipient_uei"] and b["recipient_uei"]:
        return a["recipient_uei"] == b["recipient_uei"]
    return (
        a["recipient_state"] == b["recipient_state"]
        and bool(name_key(a["recipient_name"]))
        and name_key(a["recipient_name"]) == name_key(b["recipient_name"])
    )


def build_successions(
    grants: pl.DataFrame, host_links: pl.DataFrame, grant_cohorts: pl.DataFrame
) -> pl.DataFrame:
    """Link each Grant to the Grant that renewed it (same Recipient, Program and Host institution).

    `grants`, `host_links` and `grant_cohorts` cover in-window and lookback Grants.
    Only Grants with a Host (UNITID or LEAID) take part: no single Host, review
    and unmatched Grants have no Host to compare. Grants are ordered by Cohort
    (or, with no Cohort, by the FY of their project start); the successor is the
    same-Recipient Grant in the next later Cohort. When a Recipient holds more
    than one Grant at that Host in either Cohort, which one renewed which can't
    be told, and no link is made.
    """
    rows = (
        grants.join(host_links.select("fain", "host_kind", "host_id"), on="fain", how="inner")
        .filter(pl.col("host_id").is_not_null())
        .join(grant_cohorts.select("fain", "cohort_fy"), on="fain", how="left")
        .sort("fain")
        .to_dicts()
    )
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        row["order"] = row["cohort_fy"] if row["cohort_fy"] is not None else fiscal_year(row["project_start"])
        groups[(row["program"], row["host_kind"], row["host_id"])].append(row)

    links = []
    for (program, host_kind, host_id), members in groups.items():
        for grant in members:
            same = [m for m in members if _same_recipient(grant, m)]
            later = [m for m in same if m["order"] > grant["order"]]
            if not later:
                continue
            next_order = min(m["order"] for m in later)
            successors = [m for m in later if m["order"] == next_order]
            peers = [m for m in same if m["order"] == grant["order"]]
            if len(successors) == 1 and len(peers) == 1:
                links.append((grant["fain"], successors[0]["fain"], program, host_kind, host_id))
    frame = pl.DataFrame(
        links,
        schema={"fain": pl.String, "successor_fain": pl.String, "program": pl.String,
                "host_kind": pl.String, "host_id": pl.String},
        orient="row",
    ).sort("fain")
    return check_schema(Successions, frame, "Successions")


def detect_hand_offs(grant_actions: pl.DataFrame) -> pl.DataFrame:
    """Full negatives matched to the cent by a same-day A1 on another FAIN of the same Program."""
    cents = (pl.col("obligation") * 100).round().cast(pl.Int64)
    negatives = grant_actions.filter(pl.col("obligation") < 0).select(
        "fain", "program", "action_date", (-cents).alias("cents"), pl.col("obligation").abs().alias("amount")
    )
    a1s = grant_actions.filter((pl.col("action_type") == "A1") & (pl.col("obligation") > 0)).select(
        pl.col("fain").alias("successor_fain"), "program", "action_date", cents.alias("cents")
    )
    frame = (
        negatives.join(a1s, on=["program", "action_date", "cents"], how="inner")
        .filter(pl.col("fain") != pl.col("successor_fain"))
        .select("fain", "successor_fain", "program", "action_date", "amount")
        .unique(["fain", "successor_fain", "action_date"])
        .sort("fain", "action_date", "successor_fain")
    )
    return check_schema(HandOffs, frame, "Hand-offs")


def successor_fains(successions: pl.DataFrame, hand_offs: pl.DataFrame) -> dict[str, set[str]]:
    """FAIN -> the FAINs that took over from it (Succession links and hand-offs)."""
    linked: dict[str, set[str]] = defaultdict(set)
    for frame in (successions, hand_offs):
        for fain, successor in frame.select("fain", "successor_fain").iter_rows():
            linked[fain].add(successor)
    return dict(linked)
