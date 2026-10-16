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

from topo import curated_totals, provenance, run_log
from topo.config import LATEST_USASPENDING_PULL, Config, parse_date
from topo.domain.ed_lists import NOT_IN_USASPENDING, join_ed_lists
from topo.domain.funding_status import ReadWindows, read_grants_funding_status
from topo.domain.grant_universe import EXCEPTION_UNKNOWN_FAIN_PREFIX, GrantUniverse, build_grant_universe
from topo.domain.host_linking import HostLookups, build_host_links
from topo.domain.reconciliation import (
    RECONCILED,
    ReconciliationInputs,
    Tolerances,
    build_reconciliation,
)
from topo.fiscal import ReportingWindow
from topo.guards import StructuralBreak, check_layer_handoff, warn
from topo.outputs.funding_status_history import append_funding_status_history
from topo.outputs.reconciliation import write_reconciliation_csv
from topo.outputs.target_list import build_target_list, write_target_list_csv
from topo.sources import SOURCES, ed_grantee_lists, ipeds, usaspending

RUN_CONTEXT = "run_context.json"
DROP_OUTSIDE_WINDOW = "grant_outside_reporting_window"
DROP_ED_ROW_NOT_A_GRANT_YEAR = "ed_list_row_not_a_grant_year"  # FAIN in USAspending, but no Grant-year in the window
JOINED_TABLES = ("grants", "grant_actions", "fy_obligations", "grant_universe_exceptions")
HOST_LINKS = "host_links"  # one row per FAIN: outcome, Case label, Host, Host confidence
HOST_LINK_CANDIDATES = "host_link_candidates"  # (FAIN, candidate) with its signals
FUNDING_STATUS = "funding_status"  # one row per (FAIN, Budget period)
GRANT_FUNDING_STATUS = "grant_funding_status"  # one row per FAIN
RECONCILIATION = "reconciliation"  # one row per (check, Program, FY)
ED_LIST_FAIN_DIFFERENCES = "ed_list_fain_differences"  # TRIO ED-list rows that disagree with USAspending, by FAIN


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
    _join_ed_lists(config, universe, actions, pull_date)
    _join_reconciliation(config, universe, context)
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
    run_log.record(
        config, layer="join", source=GRANT_FUNDING_STATUS, rows_in=universe.grants.height,
        rows_out=per_grant.height, drops={}, pull_date=context.pull_date,
        input_hash=provenance.combined_hash(
            provenance.file_sha256(config.layout.joined_table(name)) for name in ("grants", "grant_actions")
        ),
    )
    periods.write_parquet(config.layout.joined_table(FUNDING_STATUS))
    per_grant.write_parquet(config.layout.joined_table(GRANT_FUNDING_STATUS))
    append_funding_status_history(periods, config.layout.output, context.as_of, context.pull_date)


def _join_ed_lists(config: Config, universe: GrantUniverse, actions: pl.DataFrame, pull_date: dt.date) -> None:
    """Grant-year ED-list attributes and ED-list-only FAIN exceptions (joined layer)."""
    trio = ed_grantee_lists.read_cleaned(config, ed_grantee_lists.TRIO_TABLE)
    check_layer_handoff(
        "join", trio.height, "clean",
        run_log.last_rows_out(config, "clean", ed_grantee_lists.TRIO_TABLE), ed_grantee_lists.TRIO_TABLE,
    )
    ed = join_ed_lists(
        universe.grants,
        actions["fain"].unique(),
        trio,
        ed_grantee_lists.read_cleaned(config, ed_grantee_lists.COVERAGE_TABLE),
        universe.window,
    )
    if trio.height:
        _log_ed_lists(config, trio, actions, ed.grant_year_attributes, ed.exceptions.height, pull_date)
    ed.grant_year_attributes.write_parquet(config.layout.joined_table("grant_year_ed_attributes"))
    ed.exceptions.write_parquet(config.layout.joined_table("ed_list_exceptions"))


def _log_ed_lists(
    config: Config, trio: pl.DataFrame, actions: pl.DataFrame, attributes: pl.DataFrame, exceptions: int,
    pull_date: dt.date,
) -> None:
    """Run-log the ED TRIO list rows: each attaches to a Grant-year, is an exception, or matches no Grant-year."""
    in_usaspending = pl.col("fain").is_in(actions["fain"].unique().implode())
    not_a_grant_year = trio.filter(in_usaspending).join(
        attributes.select("fain", "fiscal_year"), on=["fain", "fiscal_year"], how="anti"
    ).height
    attached = attributes.filter(pl.col("ed_list_row_id").is_not_null()).height
    run_log.record(
        config, layer="join", source="grant_year_ed_attributes", rows_in=trio.height, rows_out=attached,
        drops={NOT_IN_USASPENDING: exceptions, DROP_ED_ROW_NOT_A_GRANT_YEAR: not_a_grant_year},
        pull_date=pull_date,
        input_hash=provenance.file_sha256(config.layout.cleaned_table(ed_grantee_lists.TRIO_TABLE)),
    )


def _join_reconciliation(config: Config, universe: GrantUniverse, context: RunContext) -> None:
    """Compare with outside totals; a duplicate key stops the run, misses only warn."""
    curated_totals.record_inputs(config)
    inputs = ReconciliationInputs(
        window=universe.window,
        pull_date=context.pull_date,
        appropriations=curated_totals.read_appropriations(config),
        allocations=curated_totals.read_allocations(config),
        grants=universe.grants,
        grant_actions=universe.grant_actions,
        ed_trio_list_rows=ed_grantee_lists.read_cleaned(config, ed_grantee_lists.TRIO_TABLE),
        ed_gearup_list_rows=ed_grantee_lists.read_cleaned(config, ed_grantee_lists.GEARUP_TABLE),
        ed_list_coverage=ed_grantee_lists.read_cleaned(config, ed_grantee_lists.COVERAGE_TABLE),
    )
    result = build_reconciliation(inputs, Tolerances.from_config(config))
    table = result.table
    misses = table.filter(pl.col("reconciliation_status") != RECONCILED).filter(
        ~pl.col("gap_reason_code").is_in(["not_published", "no_ed_list"])
    )
    if misses.height:
        named = "; ".join(
            f"{code} {n}" for code, n in misses.group_by("gap_reason_code").len().sort("gap_reason_code").iter_rows()
        )
        warn(f"{misses.height} reconciliation rows do not reconcile ({named})")
    table.write_parquet(config.layout.joined_table(RECONCILIATION))
    result.ed_list_fain_differences.write_parquet(config.layout.joined_table(ED_LIST_FAIN_DIFFERENCES))


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
    reconciliation_csv: Path


def report(config: Config) -> Delivered:
    context, universe = read_joined(config)
    host_links = pl.read_parquet(config.layout.joined_table(HOST_LINKS))
    funding = pl.read_parquet(config.layout.joined_table(GRANT_FUNDING_STATUS))
    rows = build_target_list(universe, context.as_of, host_links=host_links, funding=funding)
    run_log.record(
        config, layer="report", source="target_list", rows_in=universe.grants.height, rows_out=rows.height,
        drops={}, pull_date=context.pull_date,
        input_hash=provenance.combined_hash(
            provenance.file_sha256(config.layout.joined_table(name))
            for name in (*JOINED_TABLES, HOST_LINKS, GRANT_FUNDING_STATUS)
        ),
    )
    path = write_target_list_csv(rows, config.layout.output, context.pull_date)
    provenance.write_sidecar(config, path, as_of=context.as_of, pull_date=context.pull_date)
    reconciliation_csv = _report_reconciliation(config, context)
    return Delivered(target_list_csv=path, reconciliation_csv=reconciliation_csv)


def _report_reconciliation(config: Config, context: RunContext) -> Path:
    source = config.layout.joined_table(RECONCILIATION)
    table = pl.read_parquet(source)
    run_log.record(
        config, layer="report", source=RECONCILIATION, rows_in=table.height, rows_out=table.height, drops={},
        pull_date=context.pull_date, input_hash=provenance.file_sha256(source),
    )
    path = write_reconciliation_csv(table, config.layout.output, context.pull_date)
    provenance.write_sidecar(config, path, as_of=context.as_of, pull_date=context.pull_date)
    return path


def run(config: Config, as_of: dt.date | None = None) -> Delivered:
    """Clean every source, join, and report under one As-of date."""
    for source in SOURCES:
        clean(config, source)
    join(config, as_of)
    return report(config)
