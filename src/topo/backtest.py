"""Pre-registered renewal-timing predictions: freeze them once and score them later (#12, #41)."""

from __future__ import annotations

from pathlib import Path

from topo import provenance
from topo.config import Config
from topo.domain.renewal_backtest import (
    RULE_VERSION,
    BacktestSettings,
    freeze_predictions,
    score_frozen_predictions,
)
from topo.domain.renewal_timing import (
    RenewalSettings,
    read_deadline_table,
)
from topo.guards import StructuralBreak
from topo.joined import (
    COHORT_STARTS,
    COHORT_TIMING,
    GRANT_COHORTS,
    RENEWAL_TIMING,
    RunContext,
    deliver,
    read_joined,
    read_run,
)
from topo.outputs.frozen_predictions import (
    read_frozen_predictions,
    write_frozen_predictions,
    write_scored_predictions,
)
from topo.sources import usaspending


def _prediction_stamp(config: Config, context: RunContext) -> dict[str, object]:
    run = provenance.current_run(config)
    return {
        "as_of": context.as_of.isoformat(), "pull_date": context.pull_date.isoformat(), "rule_version": RULE_VERSION,
        "source_commit": run.commit or "", "config_sha256": config.sha256, "run_id": run.run_id,
    }


def freeze(config: Config) -> Path:
    """Pre-register the `freeze_competition_fy` predictions from the joined layer; never overwrites (#12, #41)."""
    context, _ = read_run(config)
    settings = BacktestSettings.from_config(config)
    path = config.layout.curated / settings.frozen_predictions
    if path.exists():
        raise StructuralBreak(f"predictions already frozen in {path.name}; the frozen file is never overwritten")
    predictions = freeze_predictions(
        read_joined(config, COHORT_TIMING),
        read_joined(config, GRANT_COHORTS),
        read_joined(config, RENEWAL_TIMING),
        settings.freeze_competition_fy,
        RenewalSettings.from_config(config).cycle_months,
    )
    write_frozen_predictions(predictions, path, _prediction_stamp(config, context))
    deliver(config, context, path)
    return path


def score_predictions(config: Config) -> Path:
    """Score the frozen predictions against the current joined layer; writes a new file each As-of date."""
    context, _ = read_run(config)
    settings = BacktestSettings.from_config(config)
    frozen_path = config.layout.curated / settings.frozen_predictions
    frozen = read_frozen_predictions(frozen_path)
    renewal = RenewalSettings.from_config(config)
    scored = score_frozen_predictions(
        frozen,
        usaspending.read_cleaned(config),
        read_deadline_table(config.layout.curated / renewal.deadline_table),
        read_joined(config, COHORT_STARTS),
        read_joined(config, GRANT_COHORTS),
        settings.pass_bar,
    )
    stamp = {**_prediction_stamp(config, context), "frozen_sha256": provenance.file_sha256(frozen_path)}
    stamp = {"scored_" + k if k in ("as_of", "pull_date") else k: v for k, v in stamp.items()}
    path = write_scored_predictions(scored, frozen_path, context.as_of, stamp)
    deliver(config, context, path)
    return path
