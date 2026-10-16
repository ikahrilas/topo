"""Layer orchestration behind the CLI: clean -> join -> report.

`join` builds the domain tables under one As-of date and records that date in
data/joined/run_context.json; `report` writes the outputs from the joined
layer under the same date, so the two can't disagree.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from topo import curated, provenance, run_log
from topo.config import LATEST_USASPENDING_PULL, Config, parse_date
from topo.domain.ed_lists import NOT_IN_USASPENDING, join_ed_lists
from topo.domain.funding_status import ReadWindows, read_grants_funding_status
from topo.domain.grant_universe import (
    EXCEPTION_UNKNOWN_FAIN_PREFIX,
    GrantUniverse,
    build_grant_universe,
    build_lookback,
)
from topo.domain.host_gating import Gate, apply_overrides, check_separate, gate_and_override, gate_host_links
from topo.domain.host_linking import LEAID, UNITID, HostLookups, build_host_links
from topo.domain.succession import (
    LookbackSettings,
    build_successions,
    derive_cohorts,
    detect_hand_offs,
    successor_fains,
)
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
from topo.outputs.match_quality import MatchQualityInputs, render_match_quality, write_match_quality
from topo.outputs.review_queue import build_review_queue, write_review_queue_csv
from topo.outputs.spot_check import SpotCheckSettings, write_spot_check
from topo.sources import SOURCES, ccd, ed_grantee_lists, ipeds, usaspending

RUN_CONTEXT = "run_context.json"
DROP_OUTSIDE_WINDOW = "grant_outside_reporting_window"
DROP_ED_ROW_NOT_A_GRANT_YEAR = "ed_list_row_not_a_grant_year"  # FAIN in USAspending, but no Grant-year in the window
JOINED_TABLES = ("grants", "grant_actions", "fy_obligations", "grant_universe_exceptions")
HOST_LINKS_BY_RULE = "host_links_by_rule"  # the rule cascade's own decision per FAIN
HOST_LINKS = "host_links"  # one row per FAIN after gating and overrides: what the outputs show
CASE_LABEL_ACCURACY = "case_label_accuracy"  # per Case label: answer-key checks, accuracy, gating
HOST_LINK_CANDIDATES = "host_link_candidates"  # (FAIN, candidate) with its signals
FUNDING_STATUS = "funding_status"  # one row per (FAIN, Budget period)
GRANT_FUNDING_STATUS = "grant_funding_status"  # one row per FAIN
# Succession and lookback (#39). Lookback Grants feed only these tables, never amounts or reconciliation.
LOOKBACK_GRANTS = "lookback_grants"  # Grants that ended before the window, back to the lookback horizon
LOOKBACK_HOST_LINKS = "lookback_host_links"
COHORT_STARTS = "cohort_starts"  # (Program, competition FY): Cohort start date, new Grants
GRANT_COHORTS = "grant_cohorts"  # one row per in-window or lookback FAIN
SUCCESSIONS = "successions"  # fain -> successor_fain: same Recipient, Program and Host institution
HAND_OFFS = "hand_offs"  # full negative matched by a same-day same-amount A1 on another FAIN of the Program


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
    lookups = HostLookups.from_directory(ipeds.read_directory(config), ccd.read_lea_directory(config))
    host_links, after_rules = _join_host_links(config, universe, actions, lookups)
    successors = _join_succession(config, universe, actions, host_links, lookups, after_rules)
    _join_funding_status(config, universe, context, successors)
    _join_ed_lists(config, universe, actions, pull_date)
    (joined / RUN_CONTEXT).write_text(context.to_json())
    return context, universe


def _join_host_links(
    config: Config, universe: GrantUniverse, actions: pl.DataFrame, lookups: HostLookups
) -> tuple[pl.DataFrame, Callable[[pl.DataFrame], pl.DataFrame]]:
    """Rule cascade, then answer-key gating, then overrides (ADR 0002).

    Returns the final Host links and the same after-the-rules step, for Host links
    built elsewhere (lookback Grants) to be gated and overridden alike.
    """
    rule_links, candidates = build_host_links(universe.grants, actions, lookups)
    answer_key = curated.read_answer_key(config)
    check_separate(answer_key, curated.read_tuning_set(config))
    overrides = curated.read_overrides(config)
    host_names = {
        **{(UNITID, uid): unit.name for uid, unit in lookups.units.items()},
        **{(LEAID, leaid): district.name for leaid, district in lookups.districts.items()},
    }
    links, accuracy = gate_and_override(
        rule_links, answer_key, overrides, Gate.from_section(config.section("host_linking")), host_names
    )
    rule_links.write_parquet(config.layout.joined_table(HOST_LINKS_BY_RULE))
    links.write_parquet(config.layout.joined_table(HOST_LINKS))
    candidates.write_parquet(config.layout.joined_table(HOST_LINK_CANDIDATES))
    accuracy.write_parquet(config.layout.joined_table(CASE_LABEL_ACCURACY))

    def after_rules(other_rule_links: pl.DataFrame) -> pl.DataFrame:
        return apply_overrides(gate_host_links(other_rule_links, accuracy), overrides, host_names)

    return links, after_rules


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


def _join_succession(
    config: Config, universe: GrantUniverse, actions: pl.DataFrame, host_links: pl.DataFrame, lookups: HostLookups,
    after_rules: Callable[[pl.DataFrame], pl.DataFrame],
) -> dict[str, set[str]]:
    """Lookback Grants, Cohort starts, Succession links and hand-offs; returns FAIN -> successor FAINs."""
    settings = LookbackSettings.from_config(config)
    lookback = build_lookback(actions, universe.window, settings.from_fy_by_family)
    lookback_host_links = after_rules(build_host_links(lookback.grants, actions, lookups)[0])
    grants = pl.concat([universe.grants, lookback.grants])
    grant_actions = pl.concat([universe.grant_actions, lookback.grant_actions])
    cohort_starts, grant_cohorts = derive_cohorts(grants, grant_actions, settings.cohort_min_share)
    successions = build_successions(grants, pl.concat([host_links, lookback_host_links]), grant_cohorts)
    hand_offs = detect_hand_offs(grant_actions)
    tables = {
        LOOKBACK_GRANTS: lookback.grants, LOOKBACK_HOST_LINKS: lookback_host_links, COHORT_STARTS: cohort_starts,
        GRANT_COHORTS: grant_cohorts, SUCCESSIONS: successions, HAND_OFFS: hand_offs,
    }
    for name, frame in tables.items():
        frame.write_parquet(config.layout.joined_table(name))
    return successor_fains(successions, hand_offs)


def _join_funding_status(
    config: Config, universe: GrantUniverse, context: RunContext, successors: dict[str, set[str]]
) -> None:
    """Read Funding status under the As-of date, write it to the joined layer, append the history."""
    periods, per_grant = read_grants_funding_status(
        universe.grants, universe.grant_actions, ReadWindows.from_config(config), context.as_of,
        successor_fains=successors,
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
    review_queue_csv: Path
    match_quality: Path
    spot_check: Path


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
            for name in (*JOINED_TABLES, HOST_LINKS, GRANT_FUNDING_STATUS, FUNDING_STATUS)
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
    spot_check = write_spot_check(
        rows, readme, SpotCheckSettings.from_section(config.section("spot_check")), config.layout.output
    )
    for path in (files.xlsx, files.csv, spot_check):
        provenance.write_sidecar(config, path, as_of=context.as_of, pull_date=context.pull_date)
    candidates = pl.read_parquet(config.layout.joined_table(HOST_LINK_CANDIDATES))
    lookback_grants = pl.read_parquet(config.layout.joined_table(LOOKBACK_GRANTS))
    queue = build_review_queue(
        host_links, candidates, universe.grants, universe.fy_obligations,
        succession_pool=pl.concat([universe.grants, lookback_grants], how="diagonal_relaxed"),
    )
    queue_path = write_review_queue_csv(queue, config.layout.output, context.pull_date)
    provenance.write_sidecar(config, queue_path, as_of=context.as_of, pull_date=context.pull_date)
    quality = render_match_quality(
        MatchQualityInputs(
            pull_date=context.pull_date,
            as_of=context.as_of,
            grants=universe.grants,
            fy_obligations=universe.fy_obligations,
            host_links=host_links,
            candidates=candidates,
            accuracy=pl.read_parquet(config.layout.joined_table(CASE_LABEL_ACCURACY)),
            gate=Gate.from_section(config.section("host_linking")),
            answer_key_rows=curated.read_answer_key(config).height,
            tuning_set_rows=curated.read_tuning_set(config).height,
            input_hashes=_input_hashes(config),
        )
    )
    quality_path = write_match_quality(quality, config.layout.output, context.pull_date)
    provenance.write_sidecar(config, quality_path, as_of=context.as_of, pull_date=context.pull_date)
    return Delivered(
        target_list_csv=files.csv, target_list_xlsx=files.xlsx, review_queue_csv=queue_path, match_quality=quality_path,
        spot_check=spot_check,
    )


def _input_hashes(config: Config) -> list[tuple[str, str]]:
    """(path, sha256) of the config, the curated files and every raw file behind the cleaned layer."""
    base = config.path.parent
    own = [config.path, *sorted(p for p in config.layout.curated.glob("*") if p.is_file())]
    return [
        *((p.relative_to(base).as_posix(), provenance.file_sha256(p)) for p in own),
        *((f["path"], f["sha256"]) for f in provenance.raw_inputs(config)),
    ]


def run(config: Config, as_of: dt.date | None = None) -> Delivered:
    """Clean every source, join, and report under one As-of date."""
    for source in SOURCES:
        clean(config, source)
    join(config, as_of)
    return report(config)
