"""IPEDS via Urban's Education Data Portal bulk CSVs: directory and fall enrollment.

Raw layout: data/raw/ipeds/<Pull date>/<file name from the configured URL>.
Only `/csv/` bulk files are fetched. Urban's robots.txt disallows `/api/`, so a
configured URL under `/api/` stops the pull.

Cleaned tables:
    ipeds_directory    one row per (UNITID, year) from `[ipeds] directory_from_year`:
                       names, aliases, UEIs (`|`-separated), state, sector, merge link
                       (`newid`). This history is what the Host linker reads.
    ipeds_enrollment   one row per (UNITID, year): total fall enrollment
                       (rows where every breakdown column is 99 = total).

Urban codes missing values as -1, -2 or -3; clean turns them into nulls.
Without any IPEDS pull, `clean` is a no-op: the linker then sees an empty
directory and colleges come out `unmatched`, still visible on the target list.
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

SOURCE = "ipeds"
DIRECTORY_TABLE = "ipeds_directory"
ENROLLMENT_TABLE = "ipeds_enrollment"

LICENCE_CITATION = (
    "IPEDS, via Education Data Portal v. 0.27.0, Urban Institute, under ODC Attribution License "
    "(https://educationdata.urban.org/documentation/; https://opendatacommons.org/licenses/by/1-0/)"
)

URBAN_MISSING = ["-1", "-2", "-3"]

# Urban directory columns read; nothing else (no chief administrator, no phone).
DIRECTORY_KEEP = [
    "unitid", "year", "inst_name", "inst_alias", "ueis", "state_abbr", "city", "zip",
    "inst_system_name", "sector", "newid",
]
DIRECTORY_OPTIONAL = ["address"]  # street address, read when present (Census geocoder fallback); null otherwise
# Fall-enrollment breakdown columns; 99 means "total" in each.
ENROLLMENT_BREAKDOWNS = ["ftpt", "level_of_study", "degree_seeking", "class_level", "sex", "race"]


class IpedsDirectory(pa.DataFrameModel):
    """IPEDS directory history: one row per (UNITID, year)."""

    unitid: str
    year: int
    inst_name: str
    inst_alias: str = pa.Field(nullable=True)
    ueis: str = pa.Field(nullable=True)
    state_abbr: str = pa.Field(nullable=True)
    city: str = pa.Field(nullable=True)
    zip: str = pa.Field(nullable=True)
    address: str = pa.Field(nullable=True)
    inst_system_name: str = pa.Field(nullable=True)
    sector: int = pa.Field(nullable=True)
    newid: str = pa.Field(nullable=True)
    raw_file: str
    pull_date: dt.date

    class Config:
        strict = True
        unique = ["unitid", "year"]


class IpedsEnrollment(pa.DataFrameModel):
    """Total fall enrollment by UNITID and year."""

    unitid: str
    year: int
    enrollment: int
    raw_file: str
    pull_date: dt.date

    class Config:
        strict = True
        unique = ["unitid", "year"]


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


def _urls(config: Config) -> dict[str, str]:
    settings = config.section(SOURCE)
    return {"directory": settings["directory_url"], "enrollment": settings["enrollment_url"]}


# ---------------------------------------------------------------------- pull

Download = Callable[[str, Path], None]


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=600) as response, dest.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)


def pull(config: Config, pull_date: dt.date, *, download: Download = _download) -> list[PulledFile]:
    """Fetch the configured Urban bulk CSVs (serially) into data/raw/ipeds/<Pull date>/."""
    urls = _urls(config)
    for url in urls.values():
        if "/api/" in urlparse(url).path:
            raise StructuralBreak(f"Urban's /api/ is disallowed by robots.txt; use a /csv/ bulk file: {url}")
    folder = config.layout.raw_source(SOURCE) / pull_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    pulled = []
    for url in urls.values():
        dest = folder / _file_name(url)
        download(url, dest)
        data = dest.read_bytes()
        pulled.append(
            PulledFile(
                source=SOURCE, request=f"GET {url}", url=url, path=dest, pull_date=pull_date,
                bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), licence_citation=LICENCE_CITATION,
            )
        )
    return pulled


# --------------------------------------------------------------------- clean


def _urban_nulls(columns: list[str]) -> list[pl.Expr]:
    return [
        pl.col(c).str.strip_chars().replace(["", *URBAN_MISSING], None).alias(c) for c in columns
    ]


def _require(columns: list[str], header: list[str], label: str) -> None:
    missing = sorted(set(columns) - set(header))
    if missing:
        raise StructuralBreak(f"{label} lacks columns: {', '.join(missing)}")


def clean_directory(
    raw: pl.DataFrame | pl.LazyFrame, *, from_year: int, raw_file: str, pull_date: dt.date
) -> pl.DataFrame:
    """Raw Urban directory rows (all strings) -> the cleaned directory history."""
    raw = raw.lazy()
    header = raw.collect_schema().names()
    _require(DIRECTORY_KEEP, header, raw_file)
    optional = [c if c in header else pl.lit(None, dtype=pl.String).alias(c) for c in DIRECTORY_OPTIONAL]
    directory = (
        raw.select(*DIRECTORY_KEEP, *optional)
        .with_columns(_urban_nulls(DIRECTORY_KEEP + DIRECTORY_OPTIONAL))
        .with_columns(pl.col("year").cast(pl.Int64), pl.col("sector").cast(pl.Int64))
        .filter(pl.col("year") >= from_year)
        .with_columns(pl.lit(raw_file).alias("raw_file"), pl.lit(pull_date).alias("pull_date"))
        .collect()
        .select(list(IpedsDirectory.to_schema().columns))
        .sort("unitid", "year")
    )
    check_unique(directory, ["unitid", "year"], "IPEDS directory")
    return check_schema(IpedsDirectory, directory, "IPEDS directory")


def clean_enrollment(raw: pl.DataFrame | pl.LazyFrame, *, raw_file: str, pull_date: dt.date) -> pl.DataFrame:
    """Raw Urban fall-enrollment rows -> total enrollment per (UNITID, year)."""
    raw = raw.lazy()
    header = raw.collect_schema().names()
    _require(["unitid", "year", "enrollment_fall"], header, raw_file)
    breakdowns = [c for c in ENROLLMENT_BREAKDOWNS if c in header]
    enrollment = (
        raw.select("unitid", "year", "enrollment_fall", *breakdowns)
        .with_columns(_urban_nulls(["unitid", "year", "enrollment_fall", *breakdowns]))
        .filter(*[pl.col(c) == "99" for c in breakdowns])
        .filter(pl.col("enrollment_fall").is_not_null())
        .select(
            "unitid",
            pl.col("year").cast(pl.Int64),
            pl.col("enrollment_fall").cast(pl.Int64).alias("enrollment"),
            pl.lit(raw_file).alias("raw_file"),
            pl.lit(pull_date).alias("pull_date"),
        )
        .collect()
        .sort("unitid", "year")
    )
    check_unique(enrollment, ["unitid", "year"], "IPEDS enrollment")
    return check_schema(IpedsEnrollment, enrollment, "IPEDS enrollment")


def _scan(path: Path) -> pl.LazyFrame:
    if not path.exists():
        raise StructuralBreak(f"IPEDS pull lacks {path.name} ({path.parent})")
    return pl.scan_csv(path, infer_schema=False)


def clean(config: Config, pull_date: dt.date | None = None) -> pl.DataFrame:
    """Clean one IPEDS pull (default: the latest). No pull at all: no-op, empty frame."""
    layout = config.layout
    if pull_date is None:
        dates = pull_dates(layout)
        if not dates:
            return _empty(IpedsDirectory)
        pull_date = dates[-1]
    folder = layout.raw_source(SOURCE) / pull_date.isoformat()
    urls = _urls(config)
    from_year = int(config.section(SOURCE)["directory_from_year"])
    directory_name, enrollment_name = _file_name(urls["directory"]), _file_name(urls["enrollment"])
    directory_raw, enrollment_raw = _scan(folder / directory_name), _scan(folder / enrollment_name)
    input_hash = provenance.record_raw_inputs(config, SOURCE, [folder / directory_name, folder / enrollment_name])
    directory = clean_directory(directory_raw, from_year=from_year, raw_file=directory_name, pull_date=pull_date)
    enrollment = clean_enrollment(enrollment_raw, raw_file=enrollment_name, pull_date=pull_date)
    _log_clean(config, DIRECTORY_TABLE, directory_raw, directory, pull_date, input_hash, {
        "year_before_directory_from_year": _year(directory_raw).is_null() | (_year(directory_raw) < from_year),
    })
    breakdowns = [c for c in ENROLLMENT_BREAKDOWNS if c in enrollment_raw.collect_schema().names()]
    is_total = pl.all_horizontal([pl.col(c).str.strip_chars() == "99" for c in breakdowns]).fill_null(False)
    reported = ~pl.col("enrollment_fall").str.strip_chars().is_in(["", *URBAN_MISSING]).fill_null(True)
    _log_clean(config, ENROLLMENT_TABLE, enrollment_raw, enrollment, pull_date, input_hash, {
        "not_a_total_enrollment_row": ~is_total,
        "enrollment_not_reported": is_total & ~reported,
    })
    layout.cleaned.mkdir(parents=True, exist_ok=True)
    directory.write_parquet(layout.cleaned_table(DIRECTORY_TABLE))
    enrollment.write_parquet(layout.cleaned_table(ENROLLMENT_TABLE))
    return directory


def _year(raw: pl.LazyFrame) -> pl.Expr:
    return pl.col("year").str.strip_chars().replace(["", *URBAN_MISSING], None).cast(pl.Int64)


def _log_clean(
    config: Config, table: str, raw: pl.LazyFrame, cleaned: pl.DataFrame, pull_date: dt.date,
    input_hash: str, drops: dict[str, pl.Expr],
) -> None:
    """Run-log one cleaned IPEDS table; drops are counted on the raw rows in their own pass."""
    counts = raw.select(pl.len().alias("rows_in"), *[e.sum().alias(r) for r, e in drops.items()]).collect().row(0)
    run_log.record(
        config, layer="clean", source=table, rows_in=counts[0], rows_out=cleaned.height,
        drops={r: int(n) for r, n in zip(drops, counts[1:])}, pull_date=pull_date, input_hash=input_hash,
    )


def _empty(model: type[pa.DataFrameModel]) -> pl.DataFrame:
    return pl.DataFrame(schema={name: col.dtype.type for name, col in model.to_schema().columns.items()})


def read_directory(config: Config) -> pl.DataFrame:
    """The cleaned directory history; empty when IPEDS was never pulled and cleaned."""
    path = config.layout.cleaned_table(DIRECTORY_TABLE)
    return pl.read_parquet(path) if path.exists() else _empty(IpedsDirectory)


def read_enrollment(config: Config) -> pl.DataFrame:
    path = config.layout.cleaned_table(ENROLLMENT_TABLE)
    return pl.read_parquet(path) if path.exists() else _empty(IpedsEnrollment)
