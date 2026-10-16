"""The run log: append-only `output/run_log.parquet` (ADR 0003), one row per layer per run.

Columns: run_id, layer (clean / join / report), source (the source or table the
layer built), rows_in, rows_out, drops (list of {reason, rows}: every row that
went in and didn't come out, by named reason; zero counts are left out), pull_date, input_hash.

`record` checks the row balance first (rows_in == rows_out + drops); a row lost
without a named reason is a structural break, and nothing is logged.
"""

from __future__ import annotations

import datetime as dt
import os

import polars as pl

from topo import provenance
from topo.config import Config
from topo.guards import check_row_balance

RUN_LOG = "run_log.parquet"

SCHEMA = pl.Schema(
    {
        "run_id": pl.String,
        "layer": pl.String,
        "source": pl.String,
        "rows_in": pl.Int64,
        "rows_out": pl.Int64,
        "drops": pl.List(pl.Struct({"reason": pl.String, "rows": pl.Int64})),
        "pull_date": pl.Date,
        "input_hash": pl.String,
    }
)


def run_log_path(config: Config):
    return config.layout.output / RUN_LOG


def read_run_log(config: Config) -> pl.DataFrame:
    path = run_log_path(config)
    return pl.read_parquet(path) if path.exists() else pl.DataFrame(schema=SCHEMA)


def record(
    config: Config,
    *,
    layer: str,
    source: str,
    rows_in: int,
    rows_out: int,
    drops: dict[str, int],
    pull_date: dt.date | None,
    input_hash: str,
) -> None:
    """Check one layer's row balance, then append its row to the run log."""
    check_row_balance(layer, source, rows_in, rows_out, drops)
    row = pl.DataFrame(
        [
            {
                "run_id": provenance.current_run(config).run_id,
                "layer": layer,
                "source": source,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "drops": [{"reason": r, "rows": n} for r, n in sorted(drops.items()) if n],
                "pull_date": pull_date,
                "input_hash": input_hash,
            }
        ],
        schema=SCHEMA,
    )
    path = run_log_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    log = pl.concat([read_run_log(config), row])
    tmp = path.with_name(path.name + ".tmp")
    log.write_parquet(tmp)
    os.replace(tmp, path)


def last_rows_out(config: Config, layer: str, source: str) -> int | None:
    """rows_out of the latest logged `layer` for `source`, or None if never logged."""
    log = read_run_log(config).filter((pl.col("layer") == layer) & (pl.col("source") == source))
    return int(log["rows_out"][-1]) if log.height else None
