"""The report layer: write the delivered outputs from the joined layer, each with a provenance sidecar."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from topo import curated, provenance, run_log
from topo.config import Config
from topo.domain.cause_notes import FILE_NAME as CAUSE_NOTES_FILE
from topo.domain.cause_notes import read_cause_notes
from topo.domain.funding_status import ReadWindows
from topo.domain.grant_universe import GrantUniverse
from topo.domain.host_gating import Gate
from topo.domain.renewal_backtest import BacktestSettings
from topo.domain.renewal_timing import RenewalSettings
from topo.joined import (
    CASE_LABEL_ACCURACY,
    COHORT_TIMING,
    FAC_PLAUSIBILITY,
    FUNDING_STATUS,
    GRANT_FUNDING_STATUS,
    HOST_LINK_CANDIDATES,
    HOST_LINKS,
    JOINED_TABLES,
    LOCAL_CONTEXT,
    LOOKBACK_GRANTS,
    RECONCILIATION,
    RENEWAL_BACKTEST,
    RENEWAL_BACKTEST_GRANTS,
    RENEWAL_TIMING,
    UNFUNDED_ED_LIST_EVIDENCE,
    RunContext,
    deliver,
    read_joined,
    read_run,
)
from topo.outputs.fac_plausibility import write_plausibility_csv
from topo.outputs.match_quality import (
    MatchQualityInputs,
    render_match_quality,
    write_match_quality,
)
from topo.outputs.one_pager import (
    OnePagerFiles,
    OnePagerInputs,
    OnePagerSettings,
    render_one_pager,
    write_one_pager,
)
from topo.outputs.reconciliation import write_evidence_csv, write_reconciliation_csv
from topo.outputs.review_queue import build_review_queue, write_review_queue_csv
from topo.outputs.spot_check import SpotCheckSettings, write_spot_check
from topo.outputs.target_list import (
    ReadmeFacts,
    TargetListFiles,
    TargetListSettings,
    awaited_notes,
    build_target_list,
    provisional_fiscal_years,
    write_target_list,
)
from topo.review_findings import (
    last_founder_marks,
    read_review_findings,
    spot_check_summary,
)


@dataclass(frozen=True)
class Delivered:
    target_list_csv: Path
    target_list_xlsx: Path
    review_queue_csv: Path
    match_quality: Path
    reconciliation_csv: Path
    one_pager_md: Path
    one_pager_pdf: Path
    fac_plausibility_csv: Path
    spot_check: Path


def report(config: Config) -> Delivered:
    context, universe = read_run(config)
    # Every joined table the outputs read, loaded once.
    tables = {
        name: read_joined(config, name)
        for name in (
            HOST_LINKS, HOST_LINK_CANDIDATES, CASE_LABEL_ACCURACY, GRANT_FUNDING_STATUS, FUNDING_STATUS,
            LOCAL_CONTEXT, RENEWAL_TIMING, COHORT_TIMING, RENEWAL_BACKTEST, RENEWAL_BACKTEST_GRANTS, LOOKBACK_GRANTS,
            RECONCILIATION, UNFUNDED_ED_LIST_EVIDENCE, FAC_PLAUSIBILITY,
        )
    }
    settings = TargetListSettings.from_section(config.section("target_list"))
    findings = read_review_findings(config)
    files, spot_check = _report_target_list(config, context, universe, tables, settings, findings)
    queue_path = _report_review_queue(config, context, universe, tables)
    quality_path = _report_match_quality(config, context, universe, tables, findings)
    reconciliation_csv = _report_reconciliation(config, context, tables)
    plausibility_csv = write_plausibility_csv(tables[FAC_PLAUSIBILITY], config.layout.output, context.pull_date)
    deliver(config, context, plausibility_csv)
    one_pager = _report_one_pager(config, context, universe, settings, tables)
    return Delivered(
        target_list_csv=files.csv, target_list_xlsx=files.xlsx, review_queue_csv=queue_path, match_quality=quality_path,
        reconciliation_csv=reconciliation_csv, fac_plausibility_csv=plausibility_csv,
        spot_check=spot_check, one_pager_md=one_pager.markdown, one_pager_pdf=one_pager.pdf,
    )


def _report_target_list(
    config: Config, context: RunContext, universe: GrantUniverse, tables: dict[str, pl.DataFrame],
    settings: TargetListSettings, findings: pl.DataFrame,
) -> tuple[TargetListFiles, Path]:
    """The target list (XLSX + CSV) and the founder spot-check workbook built from the same rows."""
    rows = build_target_list(
        universe, context.as_of, host_links=tables[HOST_LINKS], funding=tables[GRANT_FUNDING_STATUS],
        funding_periods=tables[FUNDING_STATUS],
        cause_notes=read_cause_notes(config.layout.curated / CAUSE_NOTES_FILE), pull_date=context.pull_date,
        settings=settings, timing=tables[RENEWAL_TIMING], local_context=tables[LOCAL_CONTEXT],
        founder_marks=last_founder_marks(findings),
    )
    run_log.record(
        config, layer="report", source="target_list", rows_in=universe.grants.height, rows_out=rows.height,
        drops={}, pull_date=context.pull_date,
        input_hash=provenance.combined_hash(
            provenance.file_sha256(config.layout.joined_table(name))
            for name in (*JOINED_TABLES, HOST_LINKS, GRANT_FUNDING_STATUS, FUNDING_STATUS, RENEWAL_TIMING, LOCAL_CONTEXT)
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
    deliver(config, context, files.xlsx, files.csv, spot_check)
    return files, spot_check


def _report_review_queue(
    config: Config, context: RunContext, universe: GrantUniverse, tables: dict[str, pl.DataFrame]
) -> Path:
    queue = build_review_queue(
        tables[HOST_LINKS], tables[HOST_LINK_CANDIDATES], universe.grants, universe.fy_obligations,
        succession_pool=pl.concat([universe.grants, tables[LOOKBACK_GRANTS]], how="diagonal_relaxed"),
    )
    path = write_review_queue_csv(queue, config.layout.output, context.pull_date)
    deliver(config, context, path)
    return path


def _report_match_quality(
    config: Config, context: RunContext, universe: GrantUniverse, tables: dict[str, pl.DataFrame],
    findings: pl.DataFrame,
) -> Path:
    answer_key = curated.read_answer_key(config)
    quality = render_match_quality(
        MatchQualityInputs(
            pull_date=context.pull_date,
            as_of=context.as_of,
            grants=universe.grants,
            fy_obligations=universe.fy_obligations,
            host_links=tables[HOST_LINKS],
            candidates=tables[HOST_LINK_CANDIDATES],
            accuracy=tables[CASE_LABEL_ACCURACY],
            gate=Gate.from_section(config.section("host_linking")),
            answer_key_rows=answer_key.height,
            answer_key=answer_key,
            tuning_set_rows=curated.read_tuning_set(config).height,
            input_hashes=_input_hashes(config),
            cohort_timing=tables[COHORT_TIMING],
            backtest=tables[RENEWAL_BACKTEST],
            backtest_grants=tables[RENEWAL_BACKTEST_GRANTS],
            backtest_bar=BacktestSettings.from_config(config).pass_bar,
            local_context=tables[LOCAL_CONTEXT],
            founder_spot_check=spot_check_summary(findings),
        )
    )
    path = write_match_quality(quality, config.layout.output, context.pull_date)
    deliver(config, context, path)
    return path


def _report_one_pager(
    config: Config, context: RunContext, universe: GrantUniverse, settings: TargetListSettings,
    tables: dict[str, pl.DataFrame],
) -> OnePagerFiles:
    windows = ReadWindows.from_config(config)
    text = render_one_pager(OnePagerInputs(
        pull_date=context.pull_date,
        as_of=context.as_of,
        window=context.window,
        grants=universe.grants,
        fy_obligations=universe.fy_obligations,
        provisional_fys=provisional_fiscal_years(context.window, context.pull_date, settings.provisional_lag_days),
        provisional_lag_days=settings.provisional_lag_days,
        awaited=awaited_notes(universe, settings),
        funding_periods=tables[FUNDING_STATUS],
        grant_funding=tables[GRANT_FUNDING_STATUS],
        disruption_window=(windows.disruption_start, windows.disruption_end),
        evidence=tables[UNFUNDED_ED_LIST_EVIDENCE],
        settings=OnePagerSettings.from_section(config.section("one_pager")),
        grant_actions=universe.grant_actions,
        timing=tables[RENEWAL_TIMING],
        new_award_months=settings.new_award_months,
        lead_months=RenewalSettings.from_config(config).lead_months,
        reconciliation=tables[RECONCILIATION],
        backtest=tables[RENEWAL_BACKTEST],
        backtest_bar=BacktestSettings.from_config(config).pass_bar,
        fac=tables[FAC_PLAUSIBILITY],
    ))
    files = write_one_pager(text, config.layout.output, context.pull_date)
    deliver(config, context, files.markdown, files.pdf)
    return files


def _input_hashes(config: Config) -> list[tuple[str, str]]:
    """(path, sha256) of the config, the curated files and every raw file behind the cleaned layer."""
    base = config.path.parent
    own = [config.path, *sorted(p for p in config.layout.curated.glob("*") if p.is_file())]
    return [
        *((p.relative_to(base).as_posix(), provenance.file_sha256(p)) for p in own),
        *((f["path"], f["sha256"]) for f in provenance.raw_inputs(config)),
    ]


def _report_reconciliation(config: Config, context: RunContext, tables: dict[str, pl.DataFrame]) -> Path:
    table = tables[RECONCILIATION]
    run_log.record(
        config, layer="report", source=RECONCILIATION, rows_in=table.height, rows_out=table.height, drops={},
        pull_date=context.pull_date, input_hash=provenance.file_sha256(config.layout.joined_table(RECONCILIATION)),
    )
    path = write_reconciliation_csv(table, config.layout.output, context.pull_date)
    evidence_path = write_evidence_csv(tables[UNFUNDED_ED_LIST_EVIDENCE], config.layout.output, context.pull_date)
    deliver(config, context, path, evidence_path)
    return path
