"""Layer orchestration behind the CLI: clean -> join -> report.

`join` builds the domain tables under one As-of date and records that date in
data/joined/run_context.json; `report` writes the outputs from the joined
layer under the same date, so the two can't disagree.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from topo import provenance, run_log
from topo.config import LATEST_USASPENDING_PULL, Config, parse_date
from topo.domain.ed_lists import join_ed_lists
from topo.domain.funding_status import ReadWindows, read_grants_funding_status
from topo.domain.grant_universe import EXCEPTION_UNKNOWN_FAIN_PREFIX, GrantUniverse, build_grant_universe
from topo.domain.host_linking import HostLookups, build_host_links
from topo.fiscal import ReportingWindow
from topo.guards import StructuralBreak, check_layer_handoff, warn
from topo.outputs.funding_status_history import append_funding_status_history
from topo.domain.cause_notes import FILE_NAME as CAUSE_NOTES_FILE
from topo.domain.cause_notes import read_cause_notes
from topo.outputs.target_list import (
    ReadmeFacts,
    TargetListSettings,
    awaited_notes,
    build_target_list,
    provisional_fiscal_years,
    write_target_list,
)
from topo.sources import SOURCES, ed_grantee_lists, ipeds, usaspending

RUN_CONTEXT = "run_context.json"
DROP_OUTSIDE_WINDOW = "grant_outside_reporting_window"
JOINED_TABLES = ("grants", "grant_actions", "fy_obligations", "grant_universe_exceptions")
HOST_LINKS = "host_links"  # one row per FAIN: outcome, Case label, Host, Host confidence
HOST_LINK_CANDIDATES = "host_link_candidates"  # (FAIN, candidate) with its signals
FUNDING_STATUS = "funding_status"  # one row per (FAIN, Budget period)
GRANT_FUNDING_STATUS = "grant_funding_status"  # one row per FAIN


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


def resolve_as_of(config: Config, explicit: dt.date | None) -> dt.date:
    """The As-of date: explicit, else the config default (latest USAspending Pull date). Never the clock."""
    if explicit is not None:
        return explicit
    default = config.as_of_default
    if default == LATEST_USASPENDING_PULL:
        return usaspending.latest_pull_date(config.layout)
    return parse_date(default)


def clean(config: Config, source: str, pull_date: dt.date | None = None) -> pl.DataFrame:
    if source not in SOURCES:
        raise StructuralBreak(f"unknown source {source!r}; known: {', '.join(sorted(SOURCES))}")
    return SOURCES[source].clean(config, pull_date)


def join(config: Config, as_of: dt.date | None = None) -> tuple[RunContext, GrantUniverse]:
    as_of = resolve_as_of(config, as_of)
    actions = usaspending.read_cleaned(config)
    check_layer_handoff(
        "join", actions.height, "clean", run_log.last_rows_out(config, "clean", usaspending.SOURCE),
        usaspending.SOURCE,
    )
    window = ReportingWindow.ending_before(config.reporting_window_start_fy, as_of)
    universe = build_grant_universe(actions, window)
    pull_dates = actions["pull_date"].unique().to_list()
    pull_date = max(pull_dates) if pull_dates else usaspending.latest_pull_date(config.layout)
    context = RunContext(as_of=as_of, pull_date=pull_date, window=window)
    _log_join(config, actions, universe, pull_date)

    joined = config.layout.joined
    joined.mkdir(parents=True, exist_ok=True)
    universe.grants.write_parquet(config.layout.joined_table("grants"))
    universe.grant_actions.write_parquet(config.layout.joined_table("grant_actions"))
    universe.fy_obligations.write_parquet(config.layout.joined_table("fy_obligations"))
    universe.exceptions.write_parquet(config.layout.joined_table("grant_universe_exceptions"))
    host_links, host_link_candidates = build_host_links(
        universe.grants, actions, HostLookups.from_directory(ipeds.read_directory(config))
    )
    host_links.write_parquet(config.layout.joined_table(HOST_LINKS))
    host_link_candidates.write_parquet(config.layout.joined_table(HOST_LINK_CANDIDATES))
    _join_funding_status(config, universe, context)
    _join_ed_lists(config, universe, actions)
    (joined / RUN_CONTEXT).write_text(context.to_json())
    return context, universe


def _log_join(config: Config, actions: pl.DataFrame, universe: GrantUniverse, pull_date: dt.date) -> None:
    """Run-log the join: every cleaned action is a Grant action, an exception, or outside the window."""
    exceptions = universe.exceptions.height
    outside = actions.filter(
        ~pl.col("fain").is_in(universe.grants["fain"].implode())
        & ~pl.col("transaction_key").is_in(universe.exceptions["transaction_key"].implode())
    ).height
    if exceptions:
        warn(f"{exceptions} actions in grant_universe_exceptions ({EXCEPTION_UNKNOWN_FAIN_PREFIX})")
    run_log.record(
        config, layer="join", source="grant_universe", rows_in=actions.height,
        rows_out=universe.grant_actions.height,
        drops={EXCEPTION_UNKNOWN_FAIN_PREFIX: exceptions, DROP_OUTSIDE_WINDOW: outside},
        pull_date=pull_date,
        input_hash=provenance.file_sha256(config.layout.cleaned_table(usaspending.CLEANED_TABLE)),
    )


def _join_funding_status(config: Config, universe: GrantUniverse, context: RunContext) -> None:
    """Read Funding status under the As-of date, write it to the joined layer, append the history."""
    periods, per_grant = read_grants_funding_status(
        universe.grants, universe.grant_actions, ReadWindows.from_config(config), context.as_of
    )
    periods.write_parquet(config.layout.joined_table(FUNDING_STATUS))
    per_grant.write_parquet(config.layout.joined_table(GRANT_FUNDING_STATUS))
    append_funding_status_history(periods, config.layout.output, context.as_of, context.pull_date)


def _join_ed_lists(config: Config, universe: GrantUniverse, actions: pl.DataFrame) -> None:
    """Grant-year ED-list attributes and ED-list-only FAIN exceptions (joined layer)."""
    ed = join_ed_lists(
        universe.grants,
        actions["fain"].unique(),
        ed_grantee_lists.read_cleaned(config, ed_grantee_lists.TRIO_TABLE),
        ed_grantee_lists.read_cleaned(config, ed_grantee_lists.COVERAGE_TABLE),
        universe.window,
    )
    ed.grant_year_attributes.write_parquet(config.layout.joined_table("grant_year_ed_attributes"))
    ed.exceptions.write_parquet(config.layout.joined_table("ed_list_exceptions"))


def read_joined(config: Config) -> tuple[RunContext, GrantUniverse]:
    joined = config.layout.joined
    context_path = joined / RUN_CONTEXT
    if not context_path.exists():
        raise StructuralBreak(f"joined layer missing; run `topo join` first ({context_path})")
    context = RunContext.from_json(context_path.read_text())
    tables = {name: pl.read_parquet(config.layout.joined_table(name)) for name in JOINED_TABLES}
    universe = GrantUniverse(
        grants=tables["grants"],
        grant_actions=tables["grant_actions"],
        fy_obligations=tables["fy_obligations"],
        exceptions=tables["grant_universe_exceptions"],
        window=context.window,
    )
    return context, universe


@dataclass(frozen=True)
class Delivered:
    target_list_csv: Path
    target_list_xlsx: Path


def report(config: Config) -> Delivered:
    context, universe = read_joined(config)
    host_links = pl.read_parquet(config.layout.joined_table(HOST_LINKS))
    funding = pl.read_parquet(config.layout.joined_table(GRANT_FUNDING_STATUS))
    funding_periods = pl.read_parquet(config.layout.joined_table(FUNDING_STATUS))
    cause_notes = read_cause_notes(config.layout.curated / CAUSE_NOTES_FILE)
    settings = TargetListSettings.from_section(config.section("target_list"))
    rows = build_target_list(
        universe, context.as_of, host_links=host_links, funding=funding, funding_periods=funding_periods,
        cause_notes=cause_notes, pull_date=context.pull_date, settings=settings,
    )
    run_log.record(
        config, layer="report", source="target_list", rows_in=universe.grants.height, rows_out=rows.height,
        drops={}, pull_date=context.pull_date,
        input_hash=provenance.combined_hash(
            provenance.file_sha256(config.layout.joined_table(name))
            for name in (*JOINED_TABLES, HOST_LINKS, GRANT_FUNDING_STATUS)
        ),
    )
    readme = ReadmeFacts(
        pull_date=context.pull_date,
        as_of=context.as_of,
        window=context.window,
        settings=settings,
        provisional=provisional_fiscal_years(context.window, context.pull_date, settings.provisional_lag_days),
        awaited=awaited_notes(universe, settings),
    )
    files = write_target_list(rows, readme, config.layout.output)
    for path in (files.xlsx, files.csv):
        provenance.write_sidecar(config, path, as_of=context.as_of, pull_date=context.pull_date)
    return Delivered(target_list_csv=files.csv, target_list_xlsx=files.xlsx)


def run(config: Config, as_of: dt.date | None = None) -> Delivered:
    """Clean every source, join, and report under one As-of date."""
    for source in SOURCES:
        clean(config, source)
    join(config, as_of)
    return report(config)
