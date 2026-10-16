"""Layer orchestration behind the CLI: clean -> join -> report.

`join` builds the domain tables under one As-of date and records that date in
data/joined/run_context.json; `report` writes the outputs from the joined
layer under the same date, so the two can't disagree.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from topo import curated
from topo.config import LATEST_USASPENDING_PULL, Config, parse_date
from topo.domain.ed_lists import join_ed_lists
from topo.domain.funding_status import ReadWindows, read_grants_funding_status
from topo.domain.grant_universe import GrantUniverse, build_grant_universe
from topo.domain.host_gating import Gate, check_separate, gate_and_override
from topo.domain.host_linking import UNITID, HostLookups, build_host_links
from topo.fiscal import ReportingWindow
from topo.guards import StructuralBreak
from topo.outputs.funding_status_history import append_funding_status_history
from topo.outputs.match_quality import MatchQualityInputs, render_match_quality, write_match_quality
from topo.outputs.review_queue import build_review_queue, write_review_queue_csv
from topo.outputs.target_list import build_target_list, write_target_list_csv
from topo.sources import SOURCES, ed_grantee_lists, ipeds, usaspending

RUN_CONTEXT = "run_context.json"
JOINED_TABLES = ("grants", "grant_actions", "fy_obligations", "grant_universe_exceptions")
HOST_LINKS_BY_RULE = "host_links_by_rule"  # the rule cascade's own decision per FAIN
HOST_LINKS = "host_links"  # one row per FAIN after gating and overrides: what the outputs show
CASE_LABEL_ACCURACY = "case_label_accuracy"  # per Case label: answer-key checks, accuracy, gating
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
    window = ReportingWindow.ending_before(config.reporting_window_start_fy, as_of)
    universe = build_grant_universe(actions, window)
    pull_dates = actions["pull_date"].unique().to_list()
    pull_date = max(pull_dates) if pull_dates else usaspending.latest_pull_date(config.layout)
    context = RunContext(as_of=as_of, pull_date=pull_date, window=window)

    joined = config.layout.joined
    joined.mkdir(parents=True, exist_ok=True)
    universe.grants.write_parquet(config.layout.joined_table("grants"))
    universe.grant_actions.write_parquet(config.layout.joined_table("grant_actions"))
    universe.fy_obligations.write_parquet(config.layout.joined_table("fy_obligations"))
    universe.exceptions.write_parquet(config.layout.joined_table("grant_universe_exceptions"))
    _join_host_links(config, universe, actions)
    _join_funding_status(config, universe, context)
    _join_ed_lists(config, universe, actions)
    (joined / RUN_CONTEXT).write_text(context.to_json())
    return context, universe


def _join_host_links(config: Config, universe: GrantUniverse, actions: pl.DataFrame) -> None:
    """Rule cascade, then answer-key gating, then overrides (ADR 0002)."""
    lookups = HostLookups.from_directory(ipeds.read_directory(config))
    rule_links, candidates = build_host_links(universe.grants, actions, lookups)
    answer_key = curated.read_answer_key(config)
    check_separate(answer_key, curated.read_tuning_set(config))
    host_names = {(UNITID, uid): unit.name for uid, unit in lookups.units.items()}
    links, accuracy = gate_and_override(
        rule_links, answer_key, curated.read_overrides(config), Gate.from_section(config.section("host_linking")),
        host_names,
    )
    rule_links.write_parquet(config.layout.joined_table(HOST_LINKS_BY_RULE))
    links.write_parquet(config.layout.joined_table(HOST_LINKS))
    candidates.write_parquet(config.layout.joined_table(HOST_LINK_CANDIDATES))
    accuracy.write_parquet(config.layout.joined_table(CASE_LABEL_ACCURACY))


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
    review_queue_csv: Path
    match_quality: Path


def report(config: Config) -> Delivered:
    context, universe = read_joined(config)
    host_links = pl.read_parquet(config.layout.joined_table(HOST_LINKS))
    funding = pl.read_parquet(config.layout.joined_table(GRANT_FUNDING_STATUS))
    rows = build_target_list(universe, context.as_of, host_links=host_links, funding=funding)
    path = write_target_list_csv(rows, config.layout.output, context.pull_date)
    candidates = pl.read_parquet(config.layout.joined_table(HOST_LINK_CANDIDATES))
    queue = build_review_queue(host_links, candidates, universe.grants, universe.fy_obligations)
    queue_path = write_review_queue_csv(queue, config.layout.output, context.pull_date)
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
    return Delivered(target_list_csv=path, review_queue_csv=queue_path, match_quality=quality_path)


def _input_hashes(config: Config) -> list[tuple[str, str]]:
    """sha256 of the config, the curated files and every raw file of each source's latest pull."""
    base = config.path.parent
    paths = [config.path, *sorted(p for p in config.layout.curated.glob("*") if p.is_file())]
    if config.layout.raw.exists():
        for source_dir in sorted(p for p in config.layout.raw.iterdir() if p.is_dir()):
            pulls = sorted(p for p in source_dir.iterdir() if p.is_dir() and _is_date(p.name))
            if pulls:
                paths += sorted(p for p in pulls[-1].rglob("*") if p.is_file())
    return [(str(p.relative_to(base)), hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]


def _is_date(name: str) -> bool:
    try:
        dt.date.fromisoformat(name)
    except ValueError:
        return False
    return True


def run(config: Config, as_of: dt.date | None = None) -> Delivered:
    """Clean every source, join, and report under one As-of date."""
    for source in SOURCES:
        clean(config, source)
    join(config, as_of)
    return report(config)
