"""Run guards. Only structural breaks stop a run; everything else warns.

Structural breaks (spec #28): a row-count mismatch between layers, a duplicate
FAIN in the Grant table, a duplicate reconciliation key, and a schema failure
at the end of `clean` or `join`.
"""

from __future__ import annotations

import polars as pl
import pandera.errors
import pandera.polars as pa


class StructuralBreak(Exception):
    """A break that stops the run. The CLI prints it and exits with code 2."""


def check_schema(schema: type[pa.DataFrameModel], frame: pl.DataFrame, table: str) -> pl.DataFrame:
    """Validate a frame against its Pandera schema; a failure is a structural break."""
    try:
        return schema.validate(frame)
    except (pandera.errors.SchemaError, pandera.errors.SchemaErrors) as err:
        raise StructuralBreak(f"{table} failed its schema check: {err}") from err


def check_unique(frame: pl.DataFrame, key: str | list[str], table: str) -> None:
    """Stop the run when a key repeats, naming the repeated values."""
    keys = [key] if isinstance(key, str) else key
    dupes = frame.group_by(keys).len().filter(pl.col("len") > 1).sort(keys)
    if dupes.height:
        shown = ", ".join("/".join(str(v) for v in row) for row in dupes.select(keys).head(10).iter_rows())
        raise StructuralBreak(f"duplicate {'/'.join(keys)} in the {table}: {shown}")
