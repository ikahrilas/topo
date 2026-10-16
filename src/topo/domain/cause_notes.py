"""Cause notes: the hand-curated, cited causes shown on the target list (ADR 0001).

A cause is never inferred from a funding pattern. A row of
data/curated/cause_notes.csv records one public source that names one FAIN,
and it must cite that source and a docket entry or a page. The file may be
empty (or absent); then no row carries a cause note.

    fain, cause_note, source, docket_entry, page, source_url
"""

from __future__ import annotations

from pathlib import Path

import pandera.polars as pa
import polars as pl

from topo.guards import check_schema

FILE_NAME = "cause_notes.csv"
COLUMNS = ("fain", "cause_note", "source", "docket_entry", "page", "source_url")
FAIN_PATTERN = r"^[A-Z]\d{3}[A-Z]\d{6}$"


class CauseNotes(pa.DataFrameModel):
    fain: str = pa.Field(str_matches=FAIN_PATTERN)
    cause_note: str = pa.Field(str_length={"min_value": 1})
    source: str = pa.Field(str_length={"min_value": 1})
    docket_entry: str = pa.Field(nullable=True)
    page: str = pa.Field(nullable=True)
    source_url: str = pa.Field(nullable=True)

    class Config:
        strict = True

    @pa.dataframe_check(error="each cause note needs a docket entry or a page")
    def cites_docket_entry_or_page(cls, data: pa.PolarsData) -> pl.LazyFrame:
        return data.lazyframe.select(pl.col("docket_entry").is_not_null() | pl.col("page").is_not_null())


def read_cause_notes(path: Path) -> pl.DataFrame:
    """The curated cause notes, schema-checked (a failure stops the run). Absent file = no notes."""
    if not path.exists():
        return pl.DataFrame(schema={c: pl.String for c in COLUMNS})
    frame = pl.read_csv(path, infer_schema=False)
    frame = frame.with_columns(
        pl.when(pl.col(c).str.strip_chars() == "").then(None).otherwise(pl.col(c).str.strip_chars()).alias(c)
        for c in frame.columns
    )
    return check_schema(CauseNotes, frame, f"cause notes ({path.name})")


def cited(notes: pl.DataFrame) -> pl.DataFrame:
    """One row per FAIN: its cause notes with citations, e.g. "<note> [<source>, docket entry 41]"."""
    citation = pl.concat_str(
        pl.col("source"),
        pl.when(pl.col("docket_entry").is_not_null()).then(pl.lit(", docket entry ") + pl.col("docket_entry"))
        .otherwise(pl.lit("")),
        pl.when(pl.col("page").is_not_null()).then(pl.lit(", p. ") + pl.col("page")).otherwise(pl.lit("")),
        pl.when(pl.col("source_url").is_not_null()).then(pl.lit(", ") + pl.col("source_url")).otherwise(pl.lit("")),
    )
    return (
        notes.with_columns((pl.col("cause_note") + pl.lit(" [") + citation + pl.lit("]")).alias("cited"))
        .group_by("fain", maintain_order=True)
        .agg(pl.col("cited").str.join("; ").alias("Cause note"))
    )
