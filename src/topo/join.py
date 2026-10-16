"""The join layer: build every domain table under one As-of date (topo.joined names them)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import polars as pl

from topo import curated, curated_totals, provenance, run_log
from topo.config import LATEST_USASPENDING_PULL, Config, parse_date
from topo.domain.ed_lists import NOT_IN_USASPENDING, join_ed_lists
from topo.domain.fac_plausibility import (
    PlausibilitySettings,
    Span,
    build_fac_plausibility,
)
from topo.domain.funding_status import ReadWindows, read_grants_funding_status
from topo.domain.grant_universe import (
    EXCEPTION_UNKNOWN_FAIN_PREFIX,
    GrantUniverse,
    build_grant_universe,
    build_lookback,
)
from topo.domain.host_gating import (
    Gate,
    apply_overrides,
    check_separate,
    gate_and_override,
    gate_host_links,
)
from topo.domain.host_linking import LEAID, UNITID, HostLookups, build_host_links
from topo.domain.local_context import build_local_context, locate_campus_districts
from topo.domain.reconciliation import (
    NOT_COMPARABLE_CODES,
    RECONCILED,
    ReconciliationInputs,
    Tolerances,
    build_reconciliation,
)
from topo.domain.renewal_backtest import (
    BacktestSettings,
    run_backtest,
)
from topo.domain.renewal_timing import (
    RenewalSettings,
    new_award_fys,
    predict_cohort_timing,
    read_deadline_table,
    read_renewal_timing,
)
from topo.domain.succession import (
    LookbackSettings,
    build_successions,
    derive_cohorts,
    detect_hand_offs,
    successor_fains,
)
from topo.fiscal import ReportingWindow
from topo.guards import check_layer_handoff, warn
from topo.joined import (
    CAMPUS_DISTRICTS,
    CASE_LABEL_ACCURACY,
    COHORT_STARTS,
    COHORT_TIMING,
    DEADLINES,
    ED_LIST_FAIN_DIFFERENCES,
    FAC_PLAUSIBILITY,
    FUNDING_STATUS,
    GRANT_COHORTS,
    GRANT_FUNDING_STATUS,
    HAND_OFFS,
    HOST_LINK_CANDIDATES,
    HOST_LINKS,
    HOST_LINKS_BY_RULE,
    LOCAL_CONTEXT,
    LOOKBACK_GRANTS,
    LOOKBACK_HOST_LINKS,
    RECONCILIATION,
    RENEWAL_BACKTEST,
    RENEWAL_BACKTEST_GRANTS,
    RENEWAL_TIMING,
    RENEWAL_TIMING_EXCEPTIONS,
    RUN_CONTEXT,
    SUCCESSIONS,
    UNFUNDED_ED_LIST_EVIDENCE,
    RunContext,
    read_joined,
)
from topo.outputs.funding_status_history import (
    DROP_ALREADY_IN_HISTORY,
    append_funding_status_history,
)
from topo.outputs.funding_status_history import SOURCE as HISTORY_SOURCE
from topo.outputs.target_list import (
    TargetListSettings,
    awaited_cohort_notes,
)
from topo.sources import (
    ccd,
    census_geocoder,
    ed_grantee_lists,
    edge,
    fac,
    ipeds,
    saipe,
    usaspending,
)

DROP_OUTSIDE_WINDOW = "grant_outside_reporting_window"
DROP_ED_ROW_NOT_A_GRANT_YEAR = "ed_list_row_not_a_grant_year"  # FAIN in USAspending, but no Grant-year in the window


def resolve_as_of(config: Config, explicit: dt.date | None) -> dt.date:
    """The As-of date: explicit, else the config default (latest USAspending Pull date). Never the clock."""
    if explicit is not None:
        return explicit
    default = config.as_of_default
    if default == LATEST_USASPENDING_PULL:
        return usaspending.latest_pull_date(config.layout)
    return parse_date(default)


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
    lookups = HostLookups.from_directory(
        ipeds.read_directory(config), ccd.read_lea_directory(config), fac.read_audits(config)
    )
    host_links, after_rules = _join_host_links(config, universe, actions, lookups)
    successors = _join_succession(config, universe, actions, host_links, lookups, after_rules)
    _join_local_context(config, host_links, pull_date)
    _join_funding_status(config, universe, context, successors)
    _join_renewal_timing(config, universe, actions, context)
    _join_renewal_backtest(config, actions)
    _join_ed_lists(config, universe, actions, pull_date)
    _join_fac_plausibility(config, universe, context)
    _join_reconciliation(config, universe, context)
    (joined / RUN_CONTEXT).write_text(context.to_json())
    return context, universe


def _join_local_context(config: Config, host_links: pl.DataFrame, pull_date: dt.date) -> None:
    """Campus districts of college Hosts and one Local context row per Grant, via its final Host link only."""
    colleges = host_links.filter(pl.col("host_kind") == UNITID)["host_id"].unique()
    points = edge.read_geocodes(config).filter(pl.col("unitid").is_in(colleges.implode()))
    polygons = config.layout.cleaned_table(edge.DISTRICTS_TABLE)
    campus_districts = locate_campus_districts(
        points, polygons if polygons.exists() else None, census_geocoder.read_campus_districts(config)
    )
    context = build_local_context(
        host_links,
        ipeds_directory=ipeds.read_directory(config),
        ipeds_enrollment=ipeds.read_enrollment(config),
        lea_directory=ccd.read_lea_directory(config),
        campus_districts=campus_districts,
        saipe=saipe.read_school_districts(config),
    )
    inputs = [
        config.layout.cleaned_table(name)
        for name in (
            ipeds.DIRECTORY_TABLE, ipeds.ENROLLMENT_TABLE, ccd.LEA_DIRECTORY_TABLE, edge.GEOCODES_TABLE,
            edge.DISTRICTS_TABLE, saipe.TABLE, census_geocoder.TABLE,
        )
    ]
    run_log.record(
        config, layer="join", source=LOCAL_CONTEXT, rows_in=host_links.height, rows_out=context.height,
        drops={}, pull_date=pull_date,
        input_hash=provenance.combined_hash(
            f"{p.name} {provenance.file_sha256(p)}" for p in [config.layout.joined_table(HOST_LINKS), *inputs]
            if p.exists()
        ),
    )
    campus_districts.write_parquet(config.layout.joined_table(CAMPUS_DISTRICTS))
    context.write_parquet(config.layout.joined_table(LOCAL_CONTEXT))


def _join_host_links(
    config: Config, universe: GrantUniverse, actions: pl.DataFrame, lookups: HostLookups
) -> tuple[pl.DataFrame, Callable[[pl.DataFrame], pl.DataFrame]]:
    """Rule cascade, then answer-key gating, then overrides (ADR 0002).

    Returns the final Host links and the same after-the-rules step, for Host links
    built elsewhere (lookback Grants) to be gated and overridden alike.
    """
    rule_links, candidates = build_host_links(universe.grants, actions, lookups, _ed_trio_rows(config))
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


def _ed_trio_rows(config: Config) -> pl.DataFrame:
    """The cleaned ED TRIO list rows: the Host linker reads their "Recipient/ campus" text by exact FAIN."""
    return ed_grantee_lists.read_cleaned(config, ed_grantee_lists.TRIO_TABLE)


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
    lookback_host_links = after_rules(build_host_links(lookback.grants, actions, lookups, _ed_trio_rows(config))[0])
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
    history = append_funding_status_history(periods, config.layout.output, context.as_of, context.pull_date)
    run_log.record(
        config, layer="join", source=HISTORY_SOURCE, rows_in=periods.height, rows_out=history.added.height,
        drops={DROP_ALREADY_IN_HISTORY: history.already_in_history}, pull_date=context.pull_date,
        input_hash=provenance.file_sha256(config.layout.joined_table(FUNDING_STATUS)),
    )
    provenance.write_sidecar(
        config, history.path, as_of=context.as_of, pull_date=context.pull_date, appended=True
    )


def _join_renewal_timing(
    config: Config, universe: GrantUniverse, actions: pl.DataFrame, context: RunContext
) -> None:
    """Predicted due dates per Program Cohort and Re-competing soon per Grant (joined layer)."""
    settings = RenewalSettings.from_config(config)
    path = config.layout.curated / settings.deadline_table
    deadline_hash = provenance.record_raw_inputs(config, DEADLINES, [path] if path.exists() else [])
    cohort_timing = predict_cohort_timing(
        read_joined(config, COHORT_STARTS), read_deadline_table(path), settings
    )
    windows = ReadWindows.from_config(config)
    timing, exceptions = read_renewal_timing(
        universe.grants, universe.grant_actions, read_joined(config, GRANT_COHORTS),
        cohort_timing, read_joined(config, GRANT_FUNDING_STATUS),
        new_award_fys(actions, context.as_of), context.as_of,
        settings, dict(windows.budget_periods),
    )
    run_log.record(
        config, layer="join", source=RENEWAL_TIMING, rows_in=universe.grants.height, rows_out=timing.height,
        drops={}, pull_date=context.pull_date,
        input_hash=provenance.combined_hash([
            deadline_hash,
            *(provenance.file_sha256(config.layout.joined_table(name))
              for name in (COHORT_STARTS, GRANT_COHORTS, GRANT_FUNDING_STATUS)),
        ]),
    )
    if exceptions.height:
        warn(f"{exceptions.height} Grants have Budget-period ends that disagree with their Cohort "
             f"({RENEWAL_TIMING_EXCEPTIONS})")
    cohort_timing.write_parquet(config.layout.joined_table(COHORT_TIMING))
    timing.write_parquet(config.layout.joined_table(RENEWAL_TIMING))
    exceptions.write_parquet(config.layout.joined_table(RENEWAL_TIMING_EXCEPTIONS))


def _join_renewal_backtest(config: Config, actions: pl.DataFrame) -> None:
    """Replay the renewal-timing rule on the backtest competition under per-Program As-of dates (joined layer)."""
    renewal = RenewalSettings.from_config(config)
    deadlines = read_deadline_table(config.layout.curated / renewal.deadline_table)
    scores, grants = run_backtest(
        actions, deadlines, read_joined(config, COHORT_STARTS),
        read_joined(config, SUCCESSIONS),
        settings=BacktestSettings.from_config(config), renewal=renewal, windows=ReadWindows.from_config(config),
        lookback=LookbackSettings.from_config(config),
    )
    # Not run-logged: a diagnostic replay that keeps or drops no rows of the pipeline's own tables.
    scores.write_parquet(config.layout.joined_table(RENEWAL_BACKTEST))
    grants.write_parquet(config.layout.joined_table(RENEWAL_BACKTEST_GRANTS))


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
        funding_status=read_joined(config, FUNDING_STATUS),
        fac_plausibility=read_joined(config, FAC_PLAUSIBILITY),
        fac_span=_fac_span(config, universe),
        awaited=awaited_cohort_notes(universe, TargetListSettings.from_section(config.section("target_list"))),
    )
    result = build_reconciliation(inputs, Tolerances.from_config(config))
    table = result.table
    misses = table.filter(pl.col("reconciliation_status") != RECONCILED).filter(
        ~pl.col("gap_reason_code").is_in(list(NOT_COMPARABLE_CODES))
    )
    if misses.height:
        named = "; ".join(
            f"{code} {n}" for code, n in misses.group_by("gap_reason_code").len().sort("gap_reason_code").iter_rows()
        )
        warn(f"{misses.height} reconciliation rows do not reconcile ({named})")
    table.write_parquet(config.layout.joined_table(RECONCILIATION))
    result.ed_list_fain_differences.write_parquet(config.layout.joined_table(ED_LIST_FAIN_DIFFERENCES))
    result.unfunded_ed_list_evidence.write_parquet(config.layout.joined_table(UNFUNDED_ED_LIST_EVIDENCE))
    if result.evidence_is_large:
        overall = result.unfunded_ed_list_evidence.filter(pl.col("fiscal_year").is_null()).row(0, named=True)
        warn(
            f"{overall['with_ed_list_evidence']} of {overall['unfunded_budget_periods']} unfunded Budget periods "
            "are funded on an ED grantee list: unfunded status partly reflects USAspending reporting gaps"
        )


def _fac_span(config: Config, universe: GrantUniverse) -> tuple[int, int]:
    span = Span.of(universe.window, PlausibilitySettings.from_section(config.section("fac")))
    return span.start_fy, span.end_fy


def _join_fac_plausibility(config: Config, universe: GrantUniverse, context: RunContext) -> None:
    """Compare FAC direct lines with USAspending per (UEI, listing); flags only, never pass/fail."""
    lines = fac.read_award_lines(config)
    check_layer_handoff(
        "join", lines.height, "clean", run_log.last_rows_out(config, "clean", fac.AWARD_LINES_TABLE),
        fac.AWARD_LINES_TABLE,
    )
    settings = PlausibilitySettings.from_section(config.section("fac"))
    result = build_fac_plausibility(
        universe.grants, universe.fy_obligations, lines, fac.read_audits(config),
        Span.of(universe.window, settings), settings,
    )
    if lines.height:
        run_log.record(
            config, layer="join", source=FAC_PLAUSIBILITY, rows_in=result.lines_in, rows_out=result.lines_compared,
            drops=result.drops, pull_date=context.pull_date,
            input_hash=provenance.file_sha256(config.layout.cleaned_table(fac.AWARD_LINES_TABLE)),
        )
    result.table.write_parquet(config.layout.joined_table(FAC_PLAUSIBILITY))
