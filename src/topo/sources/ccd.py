"""CCD LEA (school district) directory via Urban's Education Data Portal bulk CSV.

Raw layout: data/raw/ccd/<Pull date>/<file name from the configured URL>.
Only `/csv/` bulk files are fetched. Urban's robots.txt disallows `/api/`, so a
configured URL under `/api/` stops the pull.

Cleaned table:
    ccd_lea_directory  one row per (LEAID, year) from `[ccd] directory_from_year`,
                       for the district agency types in `[ccd] agency_types`:
                       name, state, city, ZIP, agency type and enrollment (when the
                       file has an `enrollment` column; else null). This history is
                       what the Host linker reads for district Hosts; Local context
                       reads the latest year's agency type and enrollment.

Urban codes missing values as -1, -2 or -3; clean turns them into nulls.
Without any CCD pull, `clean` is a no-op: the linker then sees no districts and
GEAR UP partnerships come out as naming no district, still on the target list.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import pandera.polars as pa
import polars as pl

from topo import provenance, run_log
from topo.config import Config, Layout
from topo.guards import StructuralBreak, check_schema, check_unique
from topo.sources.usaspending import PulledFile

SOURCE = "ccd"
LEA_DIRECTORY_TABLE = "ccd_lea_directory"

LICENCE_CITATION = (
    "Common Core of Data (CCD) LEA directory, via Education Data Portal v. 0.27.0, Urban Institute, "
    "under ODC Attribution License "
    "(https://educationdata.urban.org/documentation/; https://opendatacommons.org/licenses/by/1-0/)"
)

URBAN_MISSING = ["-1", "-2", "-3"]

# Urban LEA directory columns read; nothing else (no phone, no officials).
LEA_KEEP = ["leaid", "year", "lea_name", "state_location", "city_location", "zip_location", "agency_type"]
LEA_OPTIONAL = ["enrollment"]  # read when present (Local context); null otherwise


class CcdLeaDirectory(pa.DataFrameModel):
    """CCD LEA directory history: one row per (LEAID, year)."""

    leaid: str
    year: int
    lea_name: str
    state_location: str = pa.Field(nullable=True)
    city_location: str = pa.Field(nullable=True)
    zip_location: str = pa.Field(nullable=True)
    agency_type: int
    enrollment: int = pa.Field(nullable=True)
    raw_file: str
    pull_date: dt.date

    class Config:
        strict = True
        unique = ["leaid", "year"]


# ---------------------------------------------------------------- pull dates


def pull_dates(layout: Layout) -> list[dt.date]:
    root = layout.raw_source(SOURCE)
    if not root.is_dir():
        return []
    found = []
    for child in root.iterdir():
        try:
            found.append(dt.date.fromisoformat(child.name))
        except ValueError:
            continue
    return sorted(found)


def _file_name(url: str) -> str:
    return Path(urlparse(url).path).name


# ---------------------------------------------------------------------- pull

Download = Callable[[str, Path], None]


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=600) as response, dest.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)


def pull(config: Config, pull_date: dt.date, *, download: Download = _download) -> list[PulledFile]:
    """Fetch the configured Urban LEA directory CSV into data/raw/ccd/<Pull date>/."""
    url = config.section(SOURCE)["lea_directory_url"]
    if "/api/" in urlparse(url).path:
        raise StructuralBreak(f"Urban's /api/ is disallowed by robots.txt; use a /csv/ bulk file: {url}")
    folder = config.layout.raw_source(SOURCE) / pull_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / _file_name(url)
    download(url, dest)
    data = dest.read_bytes()
    return [
        PulledFile(
            source=SOURCE, request=f"GET {url}", url=url, path=dest, pull_date=pull_date,
            bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), licence_citation=LICENCE_CITATION,
        )
    ]


# --------------------------------------------------------------------- clean


def clean_lea_directory(
    raw: pl.DataFrame | pl.LazyFrame,
    *,
    from_year: int,
    agency_types: list[int],
    raw_file: str,
    pull_date: dt.date,
) -> pl.DataFrame:
    """Raw Urban LEA directory rows (all strings) -> the cleaned district directory history."""
    raw = raw.lazy()
    missing = sorted(set(LEA_KEEP) - set(raw.collect_schema().names()))
    if missing:
        raise StructuralBreak(f"{raw_file} lacks columns: {', '.join(missing)}")
    header = raw.collect_schema().names()
    optional = [c if c in header else pl.lit(None, dtype=pl.String).alias(c) for c in LEA_OPTIONAL]
    columns = LEA_KEEP + LEA_OPTIONAL
    leas = (
        raw.select(*LEA_KEEP, *optional)
        .with_columns(pl.col(c).str.strip_chars().replace(["", *URBAN_MISSING], None).alias(c) for c in columns)
        .with_columns(
            pl.col("year").cast(pl.Int64), pl.col("agency_type").cast(pl.Int64),
            pl.col("enrollment").cast(pl.Float64).cast(pl.Int64),
        )
        .filter(pl.col("year") >= from_year, pl.col("agency_type").is_in(agency_types))
        .with_columns(pl.lit(raw_file).alias("raw_file"), pl.lit(pull_date).alias("pull_date"))
        .collect()
        .select(list(CcdLeaDirectory.to_schema().columns))
        .sort("leaid", "year")
    )
    check_unique(leas, ["leaid", "year"], "CCD LEA directory")
    return check_schema(CcdLeaDirectory, leas, "CCD LEA directory")


def clean(config: Config, pull_date: dt.date | None = None) -> pl.DataFrame:
    """Clean one CCD pull (default: the latest). No pull at all: no-op, empty frame."""
    layout = config.layout
    if pull_date is None:
        dates = pull_dates(layout)
        if not dates:
            return _empty()
        pull_date = dates[-1]
    settings = config.section(SOURCE)
    name = _file_name(settings["lea_directory_url"])
    path = layout.raw_source(SOURCE) / pull_date.isoformat() / name
    if not path.exists():
        raise StructuralBreak(f"CCD pull lacks {name} ({path.parent})")
    raw = pl.scan_csv(path, infer_schema=False)
    from_year = int(settings["directory_from_year"])
    agency_types = [int(t) for t in settings["agency_types"]]
    input_hash = provenance.record_raw_inputs(config, SOURCE, [path])
    leas = clean_lea_directory(raw, from_year=from_year, agency_types=agency_types, raw_file=name, pull_date=pull_date)
    # Drops are counted on the raw rows in their own pass, not from the cleaned frame.
    year = pl.col("year").str.strip_chars().cast(pl.Int64, strict=False)
    agency_type = pl.col("agency_type").str.strip_chars().cast(pl.Int64, strict=False)
    early = year.is_null() | (year < from_year)
    counts = raw.select(
        pl.len().alias("rows_in"),
        early.sum().alias("year_before_directory_from_year"),
        (~early & ~agency_type.is_in(agency_types).fill_null(False)).sum().alias("agency_type_not_a_district"),
    ).collect().row(0, named=True)
    rows_in = counts.pop("rows_in")
    run_log.record(
        config, layer="clean", source=LEA_DIRECTORY_TABLE, rows_in=rows_in, rows_out=leas.height,
        drops={reason: int(n) for reason, n in counts.items()}, pull_date=pull_date, input_hash=input_hash,
    )
    layout.cleaned.mkdir(parents=True, exist_ok=True)
    leas.write_parquet(layout.cleaned_table(LEA_DIRECTORY_TABLE))
    return leas


def _empty() -> pl.DataFrame:
    return pl.DataFrame(schema={name: col.dtype.type for name, col in CcdLeaDirectory.to_schema().columns.items()})


def read_lea_directory(config: Config) -> pl.DataFrame:
    """The cleaned district directory history; empty when CCD was never pulled and cleaned."""
    path = config.layout.cleaned_table(LEA_DIRECTORY_TABLE)
    return pl.read_parquet(path) if path.exists() else _empty()
