"""Census SAIPE school-district estimates from the Census flat file (never Urban's API).

Raw layout: data/raw/saipe/<Pull date>/<file name from the configured URL>
(e.g. ussd24.csv). The file may open with title lines; the header row is the
first row holding a "District ID" cell. Columns are found by header text:
State FIPS Code, District ID, Name, Estimated Population 5-17 and the
estimated number of relevant children 5 to 17 in poverty.

Cleaned table:
    saipe_school_districts  one row per LEAID (state FIPS + 5-digit district id,
                            as NCES builds it): district name, children 5-17,
                            children 5-17 in poverty, the ages 5-17 poverty rate
                            and the estimate year (`[saipe] data_year`).

Rows with no children 5-17 have no rate and are dropped (`no_children_5_17`).
Without any SAIPE pull, `clean` is a no-op.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
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

SOURCE = "saipe"
TABLE = "saipe_school_districts"
DROP_NO_CHILDREN = "no_children_5_17"

LICENCE_CITATION = (
    "U.S. Census Bureau, Small Area Income and Poverty Estimates (SAIPE), school district estimates; "
    "U.S. Government work, not copyrighted (https://www.census.gov/programs-surveys/saipe.html). "
    "This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau."
)

# Header text (lowercased, substring) -> cleaned column.
HEADER_MATCH = {
    "state fips": "state_fips",
    "district id": "district_id",
    "population 5-17": "children_5_17",
    "in poverty": "children_5_17_in_poverty",
}


class SaipeSchoolDistricts(pa.DataFrameModel):
    """SAIPE estimates: one row per LEAID."""

    leaid: str = pa.Field(str_length=7)
    district_name: str
    children_5_17: int = pa.Field(gt=0)
    children_5_17_in_poverty: int = pa.Field(ge=0)
    poverty_rate_5_17: float = pa.Field(ge=0, le=1)
    data_year: int
    raw_file: str
    pull_date: dt.date

    class Config:
        strict = True
        unique = ["leaid"]


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


Download = Callable[[str, Path], None]


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=600) as response, dest.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)


def pull(config: Config, pull_date: dt.date, *, download: Download = _download) -> list[PulledFile]:
    """Fetch the configured SAIPE school-district file (one request) into data/raw/saipe/<Pull date>/."""
    url = config.section(SOURCE)["school_districts_url"]
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


def _raw_rows(text: str, raw_file: str) -> pl.DataFrame:
    """The data rows under the header row, with the columns the pipeline reads, all strings."""
    rows = list(csv.reader(io.StringIO(text)))
    start = next(
        (i for i, row in enumerate(rows) if any(c.strip().lower() == "district id" for c in row)), None
    )
    if start is None:
        raise StructuralBreak(f"{raw_file} has no header row with a 'District ID' column")
    header = [c.strip().lower() for c in rows[start]]
    index: dict[str, int] = {}
    for i, name in enumerate(header):
        if name == "name":
            index["district_name"] = i
        for text_, column in HEADER_MATCH.items():
            if text_ in name and column not in index:
                index[column] = i
    missing = sorted({"district_name", *HEADER_MATCH.values()} - set(index))
    if missing:
        raise StructuralBreak(f"{raw_file} lacks columns: {', '.join(missing)}")
    body = [row for row in rows[start + 1:] if any(c.strip() for c in row)]
    return pl.DataFrame(
        {col: [row[i].strip() if i < len(row) else "" for row in body] for col, i in index.items()},
        schema={col: pl.String for col in index},
    )


def clean_school_districts(raw: pl.DataFrame, *, data_year: int, raw_file: str, pull_date: dt.date) -> pl.DataFrame:
    districts = (
        raw.with_columns(
            pl.col("children_5_17").str.replace_all(",", "").cast(pl.Int64, strict=False),
            pl.col("children_5_17_in_poverty").str.replace_all(",", "").cast(pl.Int64, strict=False),
        )
        .filter(pl.col("children_5_17") > 0)
        .select(
            (pl.col("state_fips").str.zfill(2) + pl.col("district_id").str.zfill(5)).alias("leaid"),
            "district_name",
            "children_5_17",
            "children_5_17_in_poverty",
            (pl.col("children_5_17_in_poverty") / pl.col("children_5_17")).alias("poverty_rate_5_17"),
            pl.lit(data_year, dtype=pl.Int64).alias("data_year"),
            pl.lit(raw_file).alias("raw_file"),
            pl.lit(pull_date).alias("pull_date"),
        )
        .sort("leaid")
    )
    check_unique(districts, ["leaid"], "SAIPE school districts")
    return check_schema(SaipeSchoolDistricts, districts, "SAIPE school districts")


def clean(config: Config, pull_date: dt.date | None = None) -> pl.DataFrame:
    """Clean one SAIPE pull (default: the latest). No pull at all: no-op, empty frame."""
    layout = config.layout
    if pull_date is None:
        dates = pull_dates(layout)
        if not dates:
            return _empty()
        pull_date = dates[-1]
    settings = config.section(SOURCE)
    name = _file_name(settings["school_districts_url"])
    path = layout.raw_source(SOURCE) / pull_date.isoformat() / name
    if not path.exists():
        raise StructuralBreak(f"SAIPE pull lacks {name} ({path.parent})")
    raw = _raw_rows(path.read_text(encoding="utf-8-sig", errors="replace"), name)
    input_hash = provenance.record_raw_inputs(config, SOURCE, [path])
    districts = clean_school_districts(raw, data_year=int(settings["data_year"]), raw_file=name, pull_date=pull_date)
    # Counted on the raw rows in their own pass.
    no_children = raw.filter(
        ~(pl.col("children_5_17").str.replace_all(",", "").cast(pl.Int64, strict=False) > 0).fill_null(False)
    ).height
    run_log.record(
        config, layer="clean", source=TABLE, rows_in=raw.height, rows_out=districts.height,
        drops={DROP_NO_CHILDREN: no_children}, pull_date=pull_date, input_hash=input_hash,
    )
    layout.cleaned.mkdir(parents=True, exist_ok=True)
    districts.write_parquet(layout.cleaned_table(TABLE))
    return districts


def _empty() -> pl.DataFrame:
    return pl.DataFrame(
        schema={name: col.dtype.type for name, col in SaipeSchoolDistricts.to_schema().columns.items()}
    )


def read_school_districts(config: Config) -> pl.DataFrame:
    """The cleaned SAIPE table; empty when SAIPE was never pulled and cleaned."""
    path = config.layout.cleaned_table(TABLE)
    return pl.read_parquet(path) if path.exists() else _empty()
