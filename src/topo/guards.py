"""Run guards. Only structural breaks stop a run; everything else warns.

Structural breaks (spec #28): a row-count mismatch within or between layers, a duplicate
FAIN in the Grant table, a duplicate reconciliation key, and a schema failure
at the end of `clean` or `join`. A dirty git tree also stops a run unless
`--allow-dirty` is passed (topo.provenance).
"""

from __future__ import annotations

import warnings

import polars as pl
import pandera.errors
import pandera.polars as pa


class StructuralBreak(Exception):
    """A break that stops the run. The CLI prints it and exits with code 2."""


class RunWarning(UserWarning):
    """A problem that does not stop the run. The CLI prints it as "Warning: ..."."""


def warn(message: str) -> None:
    """Report a non-structural problem; the run carries on."""
    warnings.warn(RunWarning(message), stacklevel=2)


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


def check_row_balance(layer: str, source: str, rows_in: int, rows_out: int, drops: dict[str, int]) -> None:
    """Every row a layer read either comes out or is dropped for a named reason."""
    dropped = sum(drops.values())
    if rows_in != rows_out + dropped:
        named = ", ".join(f"{reason} {n}" for reason, n in sorted(drops.items())) or "none"
        raise StructuralBreak(
            f"row-count mismatch in {layer} {source}: {rows_in} rows in, {rows_out} out, "
            f"{dropped} dropped by named reason ({named})"
        )


def check_layer_handoff(layer: str, read: int, upstream: str, wrote: int | None, source: str) -> None:
    """A layer reads exactly the rows the layer before it wrote (when that write was logged)."""
    if wrote is not None and read != wrote:
        raise StructuralBreak(
            f"row-count mismatch: {layer} read {read} {source} rows but {upstream} wrote {wrote}"
        )
