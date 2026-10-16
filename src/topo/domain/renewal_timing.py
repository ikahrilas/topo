"""Renewal timing: when each TRIO Program Cohort competes again, and Re-competing soon.

The **Predicted due date** is set per Program Cohort, never per Grant: the
prior Cohort's published application deadline plus 60 months, read from the
hand-curated, cited deadline table (data/curated/deadlines.csv). Evidence tiers
stay separate:

    notice published  the table holds the next competition's own deadline
    inferred          the Cohort's own deadline + 60 months

A Cohort with no deadline in the table falls back to its predicted competition
FY, marked "date unknown". A Program whose observed gap between Cohort starts
isn't 60 months is marked "timing not predicted" (its cycle is unusual, so the
rule isn't forced on it).

**Re-competing soon** is set for a TRIO Grant when its Cohort's Predicted due
date is at most `lead_months` (12, ASSUMPTION) after the As-of date, its latest
readable Funding status is continued or funded late, and no newer Cohort's
FAINs have appeared: a new award (a FAIN's first A1) on the Program, dated on
or before the As-of date, in or after the predicted competition FY. It holds
past the date itself until those FAINs appear. New awards are read from every
cleaned action, since a new Cohort's Grants may start after the reporting window.

GEAR UP competes most years, so it gets no prediction: its rows say "competes
most years; timing not predicted" and carry an "expires within 12 months" fact
from the Grant's end date (start + the expected Budget periods, or the latest
funded Budget period end when later).

Tables:
    cohort_timing               per (Program, Cohort FY): observed gap, predicted
                                competition FY, Predicted due date, evidence tier, timing
    renewal_timing              per FAIN: the Cohort's timing, Re-competing soon, end-date fact
    renewal_timing_exceptions   Grants whose Budget-period ends disagree with their Cohort
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandera.polars as pa
import polars as pl

from topo.domain.funding_status import FUNDED, add_months
from topo.domain.programs import GEAR_UP, PROGRAMS, TRIO, program_for
from topo.fiscal import fiscal_year
from topo.guards import check_schema

# Renewal timing values (the "Renewal timing" column).
PREDICTED = "predicted"
DATE_UNKNOWN = "date unknown"
NOT_PREDICTED = "timing not predicted"
NO_COHORT = "timing not predicted: no Cohort start in the pull"
GEAR_UP_TIMING = "competes most years; timing not predicted"

# Evidence tiers.
NOTICE_PUBLISHED = "notice published"
INFERRED = "inferred"

# Exception reasons.
ENDS_AFTER_COHORT = "budget_period_ends_after_cohort"
OFF_CYCLE = "budget_period_end_off_cohort_cycle"

DEADLINE_COLUMNS = ("program", "competition_fy", "application_deadline", "citation", "source_url", "note")
PROGRAM_NAMES = tuple(p.name for p in PROGRAMS)
FAMILY = {p.name: p.family for p in PROGRAMS}


@dataclass(frozen=True)
class RenewalSettings:
    """`[renewal_timing]` in config.toml."""

    lead_months: int  # Re-competing soon when the Predicted due date is this close (ASSUMPTION)
    cycle_months: int  # the competition cycle the rule assumes (TRIO: 60 months)
    deadline_table: str  # file name under data/curated

    @classmethod
    def from_section(cls, section: dict[str, Any]) -> "RenewalSettings":
        return cls(
            lead_months=int(section["lead_months"]),
            cycle_months=int(section["cycle_months"]),
            deadline_table=str(section["deadline_table"]),
        )

    @classmethod
    def from_config(cls, config) -> "RenewalSettings":
        return cls.from_section(config.section("renewal_timing"))


class Deadlines(pa.DataFrameModel):
    """The curated deadline table: one published application deadline per (Program, competition FY)."""

    program: str = pa.Field(isin=PROGRAM_NAMES)
    competition_fy: int = pa.Field(ge=2000)
    application_deadline: dt.date
    citation: str = pa.Field(str_length={"min_value": 1})  # required: the notice that published the date
    source_url: str = pa.Field(nullable=True)
    note: str = pa.Field(nullable=True)

    class Config:
        strict = True
        unique = ["program", "competition_fy"]


class CohortTiming(pa.DataFrameModel):
    program: str
    cohort_fy: int
    cohort_start: dt.date
    observed_gap_months: int = pa.Field(nullable=True)  # from the previous Cohort start
    predicted_competition_fy: int = pa.Field(nullable=True)
    predicted_due_date: dt.date = pa.Field(nullable=True)
    evidence_tier: str = pa.Field(nullable=True, isin=[NOTICE_PUBLISHED, INFERRED])
    timing: str = pa.Field(isin=[PREDICTED, DATE_UNKNOWN, NOT_PREDICTED, GEAR_UP_TIMING])

    class Config:
        strict = True
        unique = ["program", "cohort_fy"]


class RenewalTiming(pa.DataFrameModel):
    fain: str = pa.Field(unique=True)
    cohort_fy: int = pa.Field(nullable=True)
    predicted_competition_fy: int = pa.Field(nullable=True)
    predicted_due_date: dt.date = pa.Field(nullable=True)
    evidence_tier: str = pa.Field(nullable=True)
    timing: str
    re_competing_soon: bool
    end_date: dt.date = pa.Field(nullable=True)  # GEAR UP only: the Grant's expected end
    end_date_fact: str = pa.Field(nullable=True)  # GEAR UP only: "expires within 12 months (end date ...)"

    class Config:
        strict = True


class RenewalTimingExceptions(pa.DataFrameModel):
    fain: str
    program: str
    cohort_fy: int
    cohort_end: dt.date
    budget_period_end: dt.date
    reason: str = pa.Field(isin=[ENDS_AFTER_COHORT, OFF_CYCLE])

    class Config:
        strict = True
        unique = ["fain", "reason"]


def read_deadline_table(path: Path) -> pl.DataFrame:
    """The curated deadline table, schema-checked (a failure stops the run). Absent file = empty table."""
    if not path.exists():
        frame = pl.DataFrame(schema={c: pl.String for c in DEADLINE_COLUMNS})
    else:
        frame = pl.read_csv(path, infer_schema=False)
        frame = frame.with_columns(
            pl.when(pl.col(c).str.strip_chars() == "").then(None).otherwise(pl.col(c).str.strip_chars()).alias(c)
            for c in frame.columns
        )
    missing = [c for c in DEADLINE_COLUMNS if c not in frame.columns]
    if not missing:
        frame = frame.with_columns(
            pl.col("competition_fy").cast(pl.Int64, strict=False),
            pl.col("application_deadline").str.to_date("%Y-%m-%d", strict=False),
        )
    return check_schema(Deadlines, frame, f"deadline table ({path.name})")


def predict_cohort_timing(
    cohort_starts: pl.DataFrame, deadlines: pl.DataFrame, settings: RenewalSettings
) -> pl.DataFrame:
    """Per Program Cohort: the observed gap, the next competition's FY, Predicted due date and evidence tier."""
    cycle_years = settings.cycle_months // 12
    published = {(p, fy): d for p, fy, d in deadlines.select("program", "competition_fy", "application_deadline").iter_rows()}
    rows = []
    for program, cohorts in cohort_starts.sort("cohort_fy").group_by("program", maintain_order=True):
        program = program[0]
        fys = cohorts["cohort_fy"].to_list()
        gaps = [None] + [(b - a) * 12 for a, b in zip(fys, fys[1:])]
        regular = all(g == settings.cycle_months for g in gaps[1:])
        for (fy, start), gap in zip(cohorts.select("cohort_fy", "cohort_start").iter_rows(), gaps):
            row = dict(program=program, cohort_fy=fy, cohort_start=start, observed_gap_months=gap,
                       predicted_competition_fy=None, predicted_due_date=None, evidence_tier=None)
            if FAMILY.get(program) == GEAR_UP:
                row["timing"] = GEAR_UP_TIMING
            elif not regular:
                row["timing"] = NOT_PREDICTED
            else:
                notices = sorted((cfy, d) for (p, cfy), d in published.items() if p == program and cfy > fy)
                if notices:
                    cfy, due = notices[0]
                    row.update(predicted_competition_fy=cfy, predicted_due_date=due,
                               evidence_tier=NOTICE_PUBLISHED, timing=PREDICTED)
                elif (program, fy) in published:
                    row.update(predicted_competition_fy=fy + cycle_years,
                               predicted_due_date=add_months(published[(program, fy)], settings.cycle_months),
                               evidence_tier=INFERRED, timing=PREDICTED)
                else:
                    row.update(predicted_competition_fy=fy + cycle_years, timing=DATE_UNKNOWN)
            rows.append(row)
    frame = pl.DataFrame(
        rows,
        schema={"program": pl.String, "cohort_fy": pl.Int64, "cohort_start": pl.Date,
                "observed_gap_months": pl.Int64, "predicted_competition_fy": pl.Int64,
                "predicted_due_date": pl.Date, "evidence_tier": pl.String, "timing": pl.String},
        orient="row",
    )
    return check_schema(CohortTiming, frame.sort("program", "cohort_fy"), "Cohort timing")


def new_award_fys(actions: pl.DataFrame, as_of: dt.date) -> dict[str, set[int]]:
    """Program -> the FYs of its new awards (each FAIN's first A1) dated on or before the As-of date.

    `actions` are cleaned USAspending actions (any FAIN, in the window or not).
    """
    first = (
        actions.filter(pl.col("action_type") == "A1")
        .sort("action_date")
        .group_by("fain", maintain_order=True)
        .agg(pl.col("listing").first(), pl.col("action_date").first())
        .filter(pl.col("action_date") <= as_of)
    )
    fys: dict[str, set[int]] = {}
    for fain, listing, date in first.iter_rows():
        program = program_for(listing, fain)
        if program is not None:
            fys.setdefault(program.name, set()).add(fiscal_year(date))
    return fys


def read_renewal_timing(
    grants: pl.DataFrame,
    grant_actions: pl.DataFrame,
    grant_cohorts: pl.DataFrame,
    cohort_timing: pl.DataFrame,
    funding: pl.DataFrame,
    new_awards: dict[str, set[int]],
    as_of: dt.date,
    settings: RenewalSettings,
    expected_budget_periods: dict[str, int],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Per in-window Grant: its Cohort's timing and Re-competing soon; plus the Cohort-disagreement exceptions.

    `grant_cohorts` covers in-window and lookback FAINs (topo.domain.succession);
    `funding` is the joined grant_funding_status table; `grant_actions` are the
    in-window Grants' actions; `new_awards` comes from `new_award_fys`.
    """
    cohorts = dict(grant_cohorts.select("fain", "cohort_fy").iter_rows())
    timing = {(r["program"], r["cohort_fy"]): r for r in cohort_timing.iter_rows(named=True)}
    readable = dict(funding.select("fain", "latest_readable_status").iter_rows())
    horizon = add_months(as_of, settings.lead_months)

    rows = []
    for g in grants.select("fain", "program", "program_family", "project_start", "project_end").iter_rows(named=True):
        fy = cohorts.get(g["fain"])
        row = dict(fain=g["fain"], cohort_fy=fy, predicted_competition_fy=None, predicted_due_date=None,
                   evidence_tier=None, re_competing_soon=False, end_date=None, end_date_fact=None)
        if g["program_family"] == GEAR_UP:
            planned = add_months(g["project_start"], 12 * expected_budget_periods.get(GEAR_UP, 1)) - dt.timedelta(1)
            end = max(planned, g["project_end"])
            row.update(timing=GEAR_UP_TIMING, end_date=end)
            if as_of < end <= horizon:
                row["end_date_fact"] = f"expires within {settings.lead_months} months (end date {end.isoformat()})"
        elif fy is None or (g["program"], fy) not in timing:
            row["timing"] = NO_COHORT
        else:
            cohort = timing[(g["program"], fy)]
            row.update(predicted_competition_fy=cohort["predicted_competition_fy"],
                       predicted_due_date=cohort["predicted_due_date"],
                       evidence_tier=cohort["evidence_tier"], timing=cohort["timing"])
            due = cohort["predicted_due_date"]
            next_fy = cohort["predicted_competition_fy"]
            newer = next_fy is not None and any(f >= next_fy for f in new_awards.get(g["program"], ()))
            row["re_competing_soon"] = bool(
                due is not None and due <= horizon and readable.get(g["fain"]) in FUNDED and not newer
            )
        rows.append(row)
    frame = pl.DataFrame(
        rows,
        schema={"fain": pl.String, "cohort_fy": pl.Int64, "predicted_competition_fy": pl.Int64,
                "predicted_due_date": pl.Date, "evidence_tier": pl.String, "timing": pl.String,
                "re_competing_soon": pl.Boolean, "end_date": pl.Date, "end_date_fact": pl.String},
        orient="row",
    ).select(list(RenewalTiming.to_schema().columns)).sort("fain")
    exceptions = _cohort_exceptions(grants, grant_actions, cohorts, cohort_timing, settings)
    return (
        check_schema(RenewalTiming, frame, "Renewal timing"),
        check_schema(RenewalTimingExceptions, exceptions, "Renewal timing exceptions"),
    )


def _cohort_exceptions(
    grants: pl.DataFrame, grant_actions: pl.DataFrame, cohorts: dict[str, int | None],
    cohort_timing: pl.DataFrame, settings: RenewalSettings,
) -> pl.DataFrame:
    """TRIO Grants whose Budget-period ends run past their Cohort's end or fall off its anniversaries.

    A Cohort starting S runs S .. S + 60 months - 1 day, with Budget periods ending
    on S + 12k months - 1 day. Extensions and off-cycle Grants show up here.
    """
    starts = {(p, fy): s for p, fy, s in cohort_timing.select("program", "cohort_fy", "cohort_start").iter_rows()}
    ends = (
        grant_actions.filter(pl.col("budget_period_end").is_not_null())
        .group_by("fain").agg(pl.col("budget_period_end").unique().sort())
    )
    program_of = dict(grants.select("fain", "program").iter_rows())
    rows = []
    for fain, period_ends in ends.sort("fain").iter_rows():
        program = program_of.get(fain)
        fy = cohorts.get(fain)
        if program is None or FAMILY.get(program) != TRIO or (program, fy) not in starts:
            continue
        start = starts[(program, fy)]
        cohort_end = add_months(start, settings.cycle_months) - dt.timedelta(1)
        anniversaries = {
            add_months(start, 12 * k) - dt.timedelta(1) for k in range(1, settings.cycle_months // 12 + 1)
        }
        late = [e for e in period_ends if e > cohort_end]
        if late:
            rows.append((fain, program, fy, cohort_end, max(late), ENDS_AFTER_COHORT))
        off = [e for e in period_ends if e <= cohort_end and e not in anniversaries]
        if off:
            rows.append((fain, program, fy, cohort_end, max(off), OFF_CYCLE))
    return pl.DataFrame(
        rows,
        schema={"fain": pl.String, "program": pl.String, "cohort_fy": pl.Int64, "cohort_end": pl.Date,
                "budget_period_end": pl.Date, "reason": pl.String},
        orient="row",
    )
