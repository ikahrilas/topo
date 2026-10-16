"""The raw manifest: one committed `data/raw/manifest.csv` for all sources (ADR 0003).

Every raw file traces to one row: source, request or URL, Pull date, bytes,
SHA-256 and licence citation. `topo pull <source>` appends its own rows; the
hand-downloaded ED grantee lists (#5) keep their rows, including the known
gaps (`status = "missing"`, no file). Rows are only ever appended.

Columns are the #5 ED grantee-list manifest's plus `source`, `request` and
`licence_citation`. `program`, `fy`, `source_page_url` and `original_name` are
ED-list fields and stay blank for automated pulls. `stored_path` is relative
to the directory holding config.toml.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

import pandera.polars as pa
import polars as pl

from topo.config import Config
from topo.guards import check_schema

COLUMNS = [
    "source",
    "program",
    "fy",
    "status",
    "source_page_url",
    "request",
    "file_url",
    "pull_date",
    "bytes",
    "sha256",
    "licence_citation",
    "original_name",
    "stored_path",
    "note",
]
OK = "ok"


class ManifestRows(pa.DataFrameModel):
    """A valid manifest: every row names its source, Pull date and licence citation;
    every `ok` row names its file, bytes and SHA-256."""

    source: str
    program: str = pa.Field(nullable=True)
    fy: str = pa.Field(nullable=True)
    status: str = pa.Field(isin=[OK, "missing"])
    source_page_url: str = pa.Field(nullable=True)
    request: str = pa.Field(nullable=True)
    file_url: str = pa.Field(nullable=True)
    pull_date: str = pa.Field(str_matches=r"^\d{4}-\d{2}-\d{2}$")
    bytes: str = pa.Field(nullable=True, str_matches=r"^\d+$")
    sha256: str = pa.Field(nullable=True, str_matches=r"^[0-9a-f]{64}$")
    licence_citation: str
    original_name: str = pa.Field(nullable=True)
    stored_path: str = pa.Field(nullable=True)
    note: str = pa.Field(nullable=True)

    @pa.dataframe_check
    def ok_rows_name_their_file(cls, data) -> pl.LazyFrame:
        ok = pl.col("status") == OK
        named = pl.all_horizontal(pl.col("bytes", "sha256", "stored_path").is_not_null())
        return data.lazyframe.select((~ok | named).alias("ok_rows_name_their_file"))

    class Config:
        strict = True


class ManifestEntry(Protocol):
    """What a source's `pull` returns per fetched file (topo.sources.raw.PulledFile)."""

    source: str
    request: str
    url: str
    path: Path
    pull_date: object
    bytes: int
    sha256: str
    licence_citation: str


def manifest_path(config: Config) -> Path:
    return config.layout.raw / "manifest.csv"


def read_manifest(path: Path) -> pl.DataFrame:
    """Read and validate a manifest (all columns as strings; blanks are nulls)."""
    frame = pl.read_csv(path, infer_schema=False).with_columns(pl.col(pl.String).replace("", None))
    return check_schema(ManifestRows, frame.select(COLUMNS), "raw manifest")


def append(config: Config, pulled: Iterable[ManifestEntry]) -> int:
    """Append one manifest row per pulled file; create the manifest if absent. Returns rows written."""
    path = manifest_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    root = config.path.parent
    rows = [
        {
            "source": p.source,
            "status": OK,
            "request": p.request,
            "file_url": p.url,
            "pull_date": str(p.pull_date),
            "bytes": str(p.bytes),
            "sha256": p.sha256,
            "licence_citation": p.licence_citation,
            "stored_path": Path(p.path).resolve().relative_to(root.resolve()).as_posix(),
        }
        for p in pulled
    ]
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL, lineterminator="\n", restval="")
        if new:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)
