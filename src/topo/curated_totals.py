"""Hand-curated outside totals for reconciliation (#42): appropriations and ED per-program allocations.

Both files are committed under data/curated/ and filed by hand from cited ED
budget tables and program pages (docs/research/trio-gearup-funding-and-cycles.md).
They may be empty or absent: every check that needs a figure then reads
`not_published`. A figure ED did not publish is a blank cell, never zero.

    appropriations.csv          program_family (TRIO / GEAR UP), fiscal_year, amount_usd, citation, note
    ed_program_allocations.csv  program, fiscal_year, allocation_usd (blank = not published),
                                award_count (blank = not published), citation, note

Duplicates are not refused here: they surface as a duplicate reconciliation key,
which stops the run.
"""

from __future__ import annotations

from pathlib import Path

import pandera.polars as pa
import polars as pl

from topo import provenance
from topo.config import Config
from topo.domain.programs import GEAR_UP, PROGRAMS, TRIO
from topo.guards import StructuralBreak, check_schema

SOURCE = "curated_totals"
APPROPRIATIONS_FILE = "appropriations.csv"
ALLOCATIONS_FILE = "ed_program_allocations.csv"


class Appropriations(pa.DataFrameModel):
    """Enacted appropriation for one Program family and FY (whole dollars)."""

    program_family: str = pa.Field(isin=[TRIO, GEAR_UP])
    fiscal_year: int = pa.Field(ge=2000)
    amount_usd: float = pa.Field(ge=0)
    citation: str
    note: str = pa.Field(nullable=True)

    class Config:
        strict = True


class ProgramAllocations(pa.DataFrameModel):
    """ED's published funding allocation and number of awards for one Program and FY."""

    program: str = pa.Field(isin=[p.name for p in PROGRAMS])
    fiscal_year: int = pa.Field(ge=2000)
    allocation_usd: float = pa.Field(nullable=True, ge=0)
    award_count: int = pa.Field(nullable=True, ge=0)
    citation: str
    note: str = pa.Field(nullable=True)

    class Config:
        strict = True


def _read(path: Path, model: type[pa.DataFrameModel], table: str) -> pl.DataFrame:
    columns = model.to_schema().columns
    dtypes = {name: col.dtype.type for name, col in columns.items()}
    if not path.exists():
        return pl.DataFrame(schema=dtypes)
    raw = pl.read_csv(path, infer_schema=False)
    missing = sorted(set(columns) - set(raw.columns))
    if missing:
        raise StructuralBreak(f"{table} ({path.name}) lacks columns: {', '.join(missing)}")
    frame = raw.select(
        pl.when(pl.col(name).str.strip_chars() == "").then(None).otherwise(pl.col(name).str.strip_chars())
        .cast(dtypes[name], strict=False).alias(name)
        if dtypes[name] != pl.String
        else pl.when(pl.col(name).str.strip_chars() == "").then(None).otherwise(pl.col(name)).alias(name)
        for name in columns
    )
    unparsed = raw.select(
        (pl.col(name).str.strip_chars().fill_null("") != "").sum().alias(name) for name in columns
    ).row(0)
    parsed = frame.select(pl.col(name).is_not_null().sum().alias(name) for name in columns).row(0)
    bad = [name for name, a, b in zip(columns, unparsed, parsed) if a != b]
    if bad:
        raise StructuralBreak(f"{table} ({path.name}) has values that don't parse in: {', '.join(bad)}")
    return check_schema(model, frame, table)


def paths(config: Config) -> list[Path]:
    curated = config.layout.curated
    return [curated / APPROPRIATIONS_FILE, curated / ALLOCATIONS_FILE]


def read_appropriations(config: Config) -> pl.DataFrame:
    return _read(config.layout.curated / APPROPRIATIONS_FILE, Appropriations, "curated appropriations")


def read_allocations(config: Config) -> pl.DataFrame:
    return _read(config.layout.curated / ALLOCATIONS_FILE, ProgramAllocations, "curated ED program allocations")


def record_inputs(config: Config) -> str:
    """Record the curated files read, so they appear in every output's provenance sidecar."""
    return provenance.record_raw_inputs(config, SOURCE, [p for p in paths(config) if p.exists()])
