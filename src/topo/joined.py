"""The joined layer: its table names, the run context `join` records, and reading it back.

`join` writes data/joined/*.parquet and data/joined/run_context.json; `report` and the
backtest commands read them under the same As-of date, so the layers cannot disagree.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from topo import provenance
from topo.config import Config, parse_date
from topo.domain.grant_universe import GrantUniverse
from topo.fiscal import ReportingWindow
from topo.guards import StructuralBreak

RUN_CONTEXT = "run_context.json"
JOINED_TABLES = ("grants", "grant_actions", "fy_obligations", "grant_universe_exceptions")
HOST_LINKS_BY_RULE = "host_links_by_rule"  # the rule cascade's own decision per FAIN
HOST_LINKS = "host_links"  # one row per FAIN after gating and overrides: what the outputs show
CASE_LABEL_ACCURACY = "case_label_accuracy"  # per Case label: answer-key checks, accuracy, gating
HOST_LINK_CANDIDATES = "host_link_candidates"  # (FAIN, candidate) with its signals
FUNDING_STATUS = "funding_status"  # one row per (FAIN, Budget period)
GRANT_FUNDING_STATUS = "grant_funding_status"  # one row per FAIN
RECONCILIATION = "reconciliation"  # one row per (check, Program, FY)
ED_LIST_FAIN_DIFFERENCES = "ed_list_fain_differences"  # TRIO ED-list rows that disagree with USAspending, by FAIN
UNFUNDED_ED_LIST_EVIDENCE = "unfunded_ed_list_evidence"  # per (Program, FY) plus an overall row
FAC_PLAUSIBILITY = "fac_plausibility"  # per (Recipient UEI, listing): plausibility, not reconciliation
# Succession and lookback (#39). Lookback Grants feed only these tables, never amounts or reconciliation.
LOOKBACK_GRANTS = "lookback_grants"  # Grants that ended before the window, back to the lookback horizon
LOOKBACK_HOST_LINKS = "lookback_host_links"
COHORT_STARTS = "cohort_starts"  # (Program, competition FY): Cohort start date, new Grants
GRANT_COHORTS = "grant_cohorts"  # one row per in-window or lookback FAIN
SUCCESSIONS = "successions"  # fain -> successor_fain: same Recipient, Program and Host institution
HAND_OFFS = "hand_offs"  # full negative matched by a same-day same-amount A1 on another FAIN of the Program
# Local context (#38).
CAMPUS_DISTRICTS = "campus_districts"  # (UNITID, LEAID): every district a college Host's campus lies in
LOCAL_CONTEXT = "local_context"  # one row per FAIN: context via the Host, each field with its data year
# Renewal timing (#40).
COHORT_TIMING = "cohort_timing"  # (Program, Cohort FY): observed gap, Predicted due date, evidence tier
RENEWAL_TIMING = "renewal_timing"  # one row per FAIN: Cohort timing, Re-competing soon, GEAR UP end-date fact
RENEWAL_TIMING_EXCEPTIONS = "renewal_timing_exceptions"  # Budget-period ends that disagree with the Cohort
DEADLINES = "deadlines"  # the curated deadline table, recorded as an input for provenance sidecars
# Renewal-timing backtest (#41).
RENEWAL_BACKTEST = "renewal_backtest"  # per TRIO Program: backtest As-of, prediction, actual deadline, scores
RENEWAL_BACKTEST_GRANTS = "renewal_backtest_grants"  # per prior-Cohort Grant: flagged, re-competed


@dataclass(frozen=True)
class RunContext:
    """What a run reads the data as of; written by `join`, read by `report`."""

    as_of: dt.date
    pull_date: dt.date  # the USAspending Pull date the joined layer was built from
    window: ReportingWindow

    def to_json(self) -> str:
        return json.dumps(
            {
                "as_of": self.as_of.isoformat(),
                "pull_date": self.pull_date.isoformat(),
                "reporting_window": {"start_fy": self.window.start_fy, "end_fy": self.window.end_fy},
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "RunContext":
        data = json.loads(text)
        window = ReportingWindow(**data["reporting_window"])
        return cls(parse_date(data["as_of"]), parse_date(data["pull_date"]), window)


def read_joined(config: Config, name: str) -> pl.DataFrame:
    """One joined table by name (the constants above)."""
    return pl.read_parquet(config.layout.joined_table(name))


def read_run(config: Config) -> tuple[RunContext, GrantUniverse]:
    """The run context `join` recorded and the Grant universe it built."""
    joined = config.layout.joined
    context_path = joined / RUN_CONTEXT
    if not context_path.exists():
        raise StructuralBreak(f"joined layer missing; run `topo join` first ({context_path})")
    context = RunContext.from_json(context_path.read_text())
    tables = {name: read_joined(config, name) for name in JOINED_TABLES}
    universe = GrantUniverse(
        grants=tables["grants"],
        grant_actions=tables["grant_actions"],
        fy_obligations=tables["fy_obligations"],
        exceptions=tables["grant_universe_exceptions"],
        window=context.window,
    )
    return context, universe


def deliver(config: Config, context: RunContext, *paths: Path) -> None:
    """A provenance sidecar for each delivered file, under the run's As-of and Pull dates."""
    for path in paths:
        provenance.write_sidecar(config, path, as_of=context.as_of, pull_date=context.pull_date)
