"""Layer orchestration behind the CLI: clean -> join -> report.

Thin on purpose: `topo.join` builds the joined layer under one As-of date and
records it in data/joined/run_context.json (`topo.joined`); `topo.report` writes
the outputs from the joined layer under the same date, so the two can't
disagree; `topo.backtest` freezes and scores the pre-registered predictions.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from topo.backtest import freeze, score_predictions
from topo.config import Config
from topo.guards import StructuralBreak
from topo.join import join, resolve_as_of
from topo.joined import RunContext, read_joined, read_run
from topo.report import Delivered, report
from topo.sources import SOURCES

__all__ = [
    "Delivered", "RunContext", "clean", "freeze", "join", "read_joined", "read_run", "report", "resolve_as_of",
    "run", "score_predictions",
]


def clean(config: Config, source: str, pull_date: dt.date | None = None) -> pl.DataFrame:
    if source not in SOURCES:
        raise StructuralBreak(f"unknown source {source!r}; known: {', '.join(sorted(SOURCES))}")
    return SOURCES[source].clean(config, pull_date)


def run(config: Config, as_of: dt.date | None = None) -> Delivered:
    """Clean every source, join, and report under one As-of date."""
    for source in SOURCES:
        clean(config, source)
    join(config, as_of)
    return report(config)
