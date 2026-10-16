"""The pre-registered FY2027 predictions (data/curated/<frozen_predictions>) and their later scorings.

The frozen file is written once, by `topo freeze` only, then committed and
tagged; it is never edited or overwritten. Each later scoring
(`topo score-predictions`) is a new file beside it,
`<frozen stem>_scored_<As-of date>.csv`, also never overwritten.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from topo.guards import StructuralBreak


def _write_new_csv(frame: pl.DataFrame, path: Path, what: str) -> Path:
    if path.exists():
        raise StructuralBreak(f"{what} {path.name} already exists and is never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        frame.write_csv(f)
    return path


def write_frozen_predictions(predictions: pl.DataFrame, path: Path, stamp: dict[str, object]) -> Path:
    """Write the frozen predictions with their stamp (As-of, Pull date, rule version, commit, ...) on every row."""
    if path.exists():
        raise StructuralBreak(f"predictions already frozen in {path.name}; the frozen file is never overwritten")
    frame = predictions.with_columns(pl.lit(value).alias(name) for name, value in stamp.items())
    return _write_new_csv(frame, path, "frozen predictions")


def read_frozen_predictions(path: Path) -> pl.DataFrame:
    if not path.exists():
        raise StructuralBreak(f"no frozen predictions at {path}; run `topo freeze` first")
    return pl.read_csv(path, infer_schema=False)


def scored_path(frozen: Path, as_of: dt.date) -> Path:
    return frozen.with_name(f"{frozen.stem}_scored_{as_of.isoformat()}{frozen.suffix}")


def write_scored_predictions(scored: pl.DataFrame, frozen: Path, as_of: dt.date, stamp: dict[str, object]) -> Path:
    frame = scored.with_columns(pl.lit(value).alias(name) for name, value in stamp.items())
    return _write_new_csv(frame, scored_path(frozen, as_of), "scoring")
