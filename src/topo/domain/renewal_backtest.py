"""The FY2022 TRIO renewal-timing backtest, and the pre-registered FY2027 predictions.

Backtest (#12): for each TRIO Program, the renewal-timing rule is rerun under a
per-Program **As-of date** `lead_months` (12) before that Program's actual
competition deadline (from the cited deadline table). Only actions dated on or
before it, and only deadlines that had passed by then, are visible. The rule's
Predicted due date for the prior Cohort is scored against the actual deadline
(timing error in calendar months), and its Re-competing soon flag over the prior
Cohort's Grants is scored for recall and precision against the pass bar
(`[renewal_backtest] pass_bar`, 95%, ASSUMPTION).

Truth: a prior-Cohort Grant **re-competed** when no Budget period starting on
or after the new Cohort's start was funded on it (read from every action in the
pull), whether or not a Succession exists. The Succession rate is descriptive
only: USAspending can't see losers or non-applicants.

Pre-registration (#12 rule 10): `freeze_predictions` returns per Program the
Cohort due to compete in `freeze_competition_fy` (2027) with its Predicted due
date, evidence tier and flagged FAINs. `score_frozen_predictions` scores such a
file later, the same way the backtest scores; the caller writes each to a new
file and never edits the frozen one.

Tables:
    renewal_backtest         per Program: As-of, prediction, actual deadline, scores, result
    renewal_backtest_grants  per prior-Cohort Grant: flagged, re-competed
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import polars as pl

from topo.domain.funding_status import ReadWindows, add_months, read_grants_funding_status
from topo.domain.grant_universe import build_grant_universe
from topo.domain.programs import PROGRAMS, TRIO
from topo.domain.renewal_timing import (
    RenewalSettings,
    new_award_fys,
    predict_cohort_timing,
    read_renewal_timing,
)
from topo.domain.succession import LookbackSettings, derive_cohorts
from topo.fiscal import ReportingWindow, fiscal_year

PASS = "pass"
MISS = "miss"
NO_DEADLINE = "not scored: no deadline for the competition in the deadline table"
NO_PRIOR_COHORT = "not scored: no prior Cohort visible on the As-of date"
NO_NEW_COHORT = "not scored: the competition's Cohort is not in the pull yet"

# What the rule is, recorded in the frozen predictions so a later reader knows what was pre-registered.
RULE_VERSION = "v1: prior Cohort deadline + cycle_months; Re-competing soon within lead_months (#12, #40)"

TRIO_PROGRAMS = tuple(p.name for p in PROGRAMS if p.family == TRIO)

BACKTEST_SCHEMA = {
    "program": pl.String, "competition_fy": pl.Int64, "as_of": pl.Date, "prior_cohort_fy": pl.Int64,
    "predicted_due_date": pl.Date, "evidence_tier": pl.String, "timing": pl.String,
    "actual_deadline": pl.Date, "timing_error_months": pl.Int64, "grants": pl.Int64, "re_competed": pl.Int64,
    "flagged": pl.Int64, "flagged_and_re_competed": pl.Int64, "recall": pl.Float64, "precision": pl.Float64,
    "result": pl.String, "with_succession": pl.Int64,
}
BACKTEST_GRANTS_SCHEMA = {
    "program": pl.String, "fain": pl.String, "latest_readable_status": pl.String, "flagged": pl.Boolean,
    "re_competed": pl.Boolean,
}


@dataclass(frozen=True)
class BacktestSettings:
    """`[renewal_backtest]` in config.toml."""

    competition_fy: int  # the competition the backtest replays (FY2022)
    pass_bar: float  # recall and precision must both reach this (ASSUMPTION: 0.95)
    freeze_competition_fy: int  # the competition whose predictions are pre-registered (FY2027)
    frozen_predictions: str  # file name under data/curated

    @classmethod
    def from_section(cls, section: dict[str, Any]) -> "BacktestSettings":
        return cls(
            competition_fy=int(section["competition_fy"]),
            pass_bar=float(section["pass_bar"]),
            freeze_competition_fy=int(section["freeze_competition_fy"]),
            frozen_predictions=str(section["frozen_predictions"]),
        )

    @classmethod
    def from_config(cls, config) -> "BacktestSettings":
        return cls.from_section(config.section("renewal_backtest"))


def months_between(earlier: dt.date, later: dt.date) -> int:
    """Signed calendar months from `earlier` to `later` (day of month ignored)."""
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def re_competed_fains(actions: pl.DataFrame, fains: list[str], new_cohort_start: dt.date) -> set[str]:
    """Of `fains`, those with no Budget period starting on or after the new Cohort's start funded on them."""
    funded_after = set(
        actions.filter(
            pl.col("fain").is_in(fains)
            & (pl.col("obligation") > 0)
            & (pl.coalesce("budget_period_start", "action_date") >= new_cohort_start)
        )["fain"].to_list()
    )
    return set(fains) - funded_after


def score_flags(flagged: set[str], re_competed: set[str], bar: float) -> dict[str, Any]:
    """Recall and precision of the Grant flag, and pass/miss against the bar (no flags or no truth = miss)."""
    hits = len(flagged & re_competed)
    recall = hits / len(re_competed) if re_competed else None
    precision = hits / len(flagged) if flagged else None
    passed = recall is not None and precision is not None and recall >= bar and precision >= bar
    return dict(re_competed=len(re_competed), flagged=len(flagged), flagged_and_re_competed=hits,
                recall=recall, precision=precision, result=PASS if passed else MISS)


@dataclass(frozen=True)
class RuleReading:
    """The renewal-timing rule read under one As-of date for one Program."""

    cohort_timing: pl.DataFrame  # CohortTiming, every Program
    grant_cohorts: pl.DataFrame  # GrantCohorts
    renewal_timing: pl.DataFrame  # RenewalTiming, the Program's Grants
    funding: pl.DataFrame  # GrantFundingStatus, the Program's Grants


def read_rule_as_of(
    actions: pl.DataFrame,
    deadlines: pl.DataFrame,
    program: str,
    as_of: dt.date,
    *,
    renewal: RenewalSettings,
    windows: ReadWindows,
    lookback: LookbackSettings,
) -> RuleReading:
    """Rerun the rule as if on `as_of`: only actions dated and deadlines passed on or before it are visible."""
    visible = actions.filter(pl.col("action_date") <= as_of)
    universe = build_grant_universe(visible, ReportingWindow(lookback.trio_from_fy, fiscal_year(as_of)))
    cohort_starts, grant_cohorts = derive_cohorts(universe.grants, universe.grant_actions, lookback.cohort_min_share)
    cohort_timing = predict_cohort_timing(
        cohort_starts, deadlines.filter(pl.col("application_deadline") <= as_of), renewal
    )
    grants = universe.grants.filter(pl.col("program") == program)
    grant_actions = universe.grant_actions.filter(pl.col("program") == program)
    _, funding = read_grants_funding_status(grants, grant_actions, windows, as_of)
    timing, _ = read_renewal_timing(
        grants, grant_actions, grant_cohorts, cohort_timing, funding, new_award_fys(visible, as_of), as_of,
        renewal, dict(windows.budget_periods),
    )
    return RuleReading(cohort_timing, grant_cohorts, timing, funding)


def run_backtest(
    actions: pl.DataFrame,
    deadlines: pl.DataFrame,
    cohort_starts: pl.DataFrame,
    successions: pl.DataFrame,
    *,
    settings: BacktestSettings,
    renewal: RenewalSettings,
    windows: ReadWindows,
    lookback: LookbackSettings,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Score the rule on the `competition_fy` competition of every TRIO Program that has it in the data or table.

    `actions` are every cleaned USAspending action; `cohort_starts` and
    `successions` are the joined tables (read over the whole pull), which give
    the new Cohort's start and the descriptive Succession rate.
    """
    fy = settings.competition_fy
    actual = {p: d for p, cfy, d in deadlines.select("program", "competition_fy", "application_deadline").iter_rows()
              if cfy == fy}
    new_starts = {p: s for p, cfy, s in cohort_starts.select("program", "cohort_fy", "cohort_start").iter_rows()
                  if cfy == fy}
    succeeded = set(successions["fain"].to_list())
    rows, grant_rows = [], []
    for program in TRIO_PROGRAMS:
        if program not in actual and program not in new_starts:
            continue
        row = {c: None for c in BACKTEST_SCHEMA} | dict(program=program, competition_fy=fy)
        rows.append(row)
        if program not in actual:
            row["result"] = NO_DEADLINE
            continue
        as_of = add_months(actual[program], -renewal.lead_months)
        row.update(as_of=as_of, actual_deadline=actual[program])
        reading = read_rule_as_of(actions, deadlines, program, as_of, renewal=renewal, windows=windows,
                                  lookback=lookback)
        prior = reading.cohort_timing.filter((pl.col("program") == program) & (pl.col("cohort_fy") < fy))
        if prior.is_empty():
            row["result"] = NO_PRIOR_COHORT
            continue
        cohort = prior.sort("cohort_fy").row(-1, named=True)
        row.update(prior_cohort_fy=cohort["cohort_fy"], predicted_due_date=cohort["predicted_due_date"],
                   evidence_tier=cohort["evidence_tier"], timing=cohort["timing"])
        if cohort["predicted_due_date"] is not None:
            row["timing_error_months"] = months_between(actual[program], cohort["predicted_due_date"])
        members = reading.grant_cohorts.filter(
            (pl.col("program") == program) & (pl.col("cohort_fy") == cohort["cohort_fy"])
        )["fain"].sort().to_list()
        row["grants"] = len(members)
        if program not in new_starts:
            row["result"] = NO_NEW_COHORT
            continue
        truth = re_competed_fains(actions, members, new_starts[program])
        flags = dict(reading.renewal_timing.select("fain", "re_competing_soon").iter_rows())
        status = dict(reading.funding.select("fain", "latest_readable_status").iter_rows())
        flagged = {f for f in members if flags.get(f)}
        row.update(score_flags(flagged, truth, settings.pass_bar))
        row["with_succession"] = len(truth & succeeded)
        grant_rows += [(program, f, status.get(f), f in flagged, f in truth) for f in members]
    return (
        pl.DataFrame(rows, schema=BACKTEST_SCHEMA),
        pl.DataFrame(grant_rows, schema=BACKTEST_GRANTS_SCHEMA, orient="row"),
    )


FROZEN_SCHEMA = {
    "program": pl.String, "competition_fy": pl.Int64, "cohort_fy": pl.Int64, "predicted_due_date": pl.Date,
    "evidence_tier": pl.String, "timing": pl.String, "cohort_grants": pl.Int64, "flagged_grants": pl.Int64,
    "flagged_fains": pl.String,
}
FAIN_SEPARATOR = ";"


def freeze_predictions(
    cohort_timing: pl.DataFrame,
    grant_cohorts: pl.DataFrame,
    renewal_timing: pl.DataFrame,
    competition_fy: int,
    cycle_months: int,
) -> pl.DataFrame:
    """Per TRIO Program, the Cohort due to compete in `competition_fy`: its prediction and flagged FAINs.

    The Cohort is the one whose FY + the cycle is `competition_fy`; it is kept
    even when its timing is "date unknown" or "timing not predicted", so what was
    (not) predicted is pre-registered too. `renewal_timing` is the joined table
    under the run's As-of date.
    """
    flagged = set(renewal_timing.filter(pl.col("re_competing_soon"))["fain"].to_list())
    rows = []
    for r in cohort_timing.filter(pl.col("program").is_in(TRIO_PROGRAMS)).sort("program").iter_rows(named=True):
        if r["cohort_fy"] + cycle_months // 12 != competition_fy:
            continue
        members = grant_cohorts.filter(
            (pl.col("program") == r["program"]) & (pl.col("cohort_fy") == r["cohort_fy"])
        )["fain"].sort().to_list()
        hits = [f for f in members if f in flagged]
        rows.append(dict(program=r["program"], competition_fy=competition_fy, cohort_fy=r["cohort_fy"],
                         predicted_due_date=r["predicted_due_date"], evidence_tier=r["evidence_tier"],
                         timing=r["timing"], cohort_grants=len(members), flagged_grants=len(hits),
                         flagged_fains=FAIN_SEPARATOR.join(hits)))
    return pl.DataFrame(rows, schema=FROZEN_SCHEMA)


SCORED_SCHEMA = {
    "program": pl.String, "competition_fy": pl.Int64, "cohort_fy": pl.Int64, "predicted_due_date": pl.Date,
    "evidence_tier": pl.String, "actual_deadline": pl.Date, "timing_error_months": pl.Int64, "grants": pl.Int64,
    "re_competed": pl.Int64, "flagged": pl.Int64, "flagged_and_re_competed": pl.Int64, "recall": pl.Float64,
    "precision": pl.Float64, "result": pl.String,
}


def score_frozen_predictions(
    frozen: pl.DataFrame,
    actions: pl.DataFrame,
    deadlines: pl.DataFrame,
    cohort_starts: pl.DataFrame,
    grant_cohorts: pl.DataFrame,
    bar: float,
) -> pl.DataFrame:
    """Score frozen predictions against the actual deadline and the new Cohort, as the backtest scores.

    `frozen` is the frozen file as read (dates as ISO strings); the other tables
    come from the current pull. A Program whose actual deadline or new Cohort
    isn't known yet is "not scored". A slip (e.g. a DOL-driven delay) is a miss,
    reported as one.
    """
    rows = []
    for r in frozen.iter_rows(named=True):
        program, fy = r["program"], int(r["competition_fy"])
        predicted = dt.date.fromisoformat(r["predicted_due_date"]) if r["predicted_due_date"] else None
        row = {c: None for c in SCORED_SCHEMA} | dict(
            program=program, competition_fy=fy, cohort_fy=int(r["cohort_fy"]), predicted_due_date=predicted,
            evidence_tier=r["evidence_tier"] or None,
        )
        rows.append(row)
        actual = deadlines.filter((pl.col("program") == program) & (pl.col("competition_fy") == fy))
        new_start = cohort_starts.filter((pl.col("program") == program) & (pl.col("cohort_fy") == fy))
        if actual.is_empty():
            row["result"] = NO_DEADLINE
            continue
        row["actual_deadline"] = actual["application_deadline"][0]
        if predicted is not None:
            row["timing_error_months"] = months_between(row["actual_deadline"], predicted)
        members = grant_cohorts.filter(
            (pl.col("program") == program) & (pl.col("cohort_fy") == row["cohort_fy"])
        )["fain"].sort().to_list()
        row["grants"] = len(members)
        if new_start.is_empty():
            row["result"] = NO_NEW_COHORT
            continue
        flagged = {f for f in (r["flagged_fains"] or "").split(FAIN_SEPARATOR) if f}
        row.update(score_flags(flagged, re_competed_fains(actions, members, new_start["cohort_start"][0]), bar))
    return pl.DataFrame(rows, schema=SCORED_SCHEMA)
