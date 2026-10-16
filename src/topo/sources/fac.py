"""Federal Audit Clearinghouse (FAC) bulk CSVs: audited amounts expended per Assistance Listing.

Raw layout: data/raw/fac/<Pull date>/federal_awards.csv and general.csv, the full
public bulk files (no API key; the links redirect to signed S3 URLs). See
docs/research/federal-audit-clearinghouse.md.

Cleaned tables:
    fac_award_lines  one row per SEFA line on a TRIO/GEAR UP listing (prefix 84 plus
                     the first three extension characters, so `042A` reads 84.042):
                     report, auditee UEI, audit year, listing, amount expended, direct flag.
    fac_audits       one row per audit report with at least one such line: auditee
                     name, state, entity type, audit year and fiscal period. Contacts,
                     emails, phones and EINs are never read.

FAC is a third source used only for a plausibility check (#43); it never changes a
Grant, an amount or a reconciliation row. Without any FAC pull, `clean` is a no-op.
"""

from __future__ import annotations

import datetime as dt

import pandera.polars as pa
import polars as pl

from topo import provenance, run_log
from topo.config import Config
from topo.domain.programs import LISTINGS
from topo.guards import StructuralBreak, check_schema, check_unique
from topo.sources import raw as raw_tree
from topo.sources.raw import PulledFile

SOURCE = "fac"
AWARD_LINES_TABLE = "fac_award_lines"
AUDITS_TABLE = "fac_audits"
DROP_NOT_A_LISTING = "not_a_trio_gear_up_listing"
DROP_NO_LINE = "no_trio_gear_up_line"

LICENCE_CITATION = (
    "Federal Audit Clearinghouse (GSA), fac.gov, public domain "
    "(https://www.fac.gov/data/; bulk files https://www.fac.gov/data/download/current/)"
)

# Bulk columns read; nothing else.
AWARD_LINE_KEEP = [
    "report_id", "auditee_uei", "audit_year", "award_reference", "federal_agency_prefix",
    "federal_award_extension", "federal_program_name", "amount_expended", "is_direct",
]
AUDIT_KEEP = [
    "report_id", "auditee_uei", "auditee_name", "auditee_state", "entity_type", "audit_year",
    "fy_start_date", "fy_end_date",
]


class FacAwardLines(pa.DataFrameModel):
    """FAC SEFA lines on TRIO/GEAR UP listings."""

    report_id: str
    auditee_uei: str = pa.Field(nullable=True)
    audit_year: int
    award_reference: str
    listing: str = pa.Field(isin=list(LISTINGS))
    federal_award_extension: str
    federal_program_name: str = pa.Field(nullable=True)
    amount_expended: int
    is_direct: bool
    raw_file: str
    pull_date: dt.date

    class Config:
        strict = True
        unique = ["report_id", "award_reference"]


class FacAudits(pa.DataFrameModel):
    """FAC audit reports that carry a TRIO/GEAR UP line."""

    report_id: str
    auditee_uei: str = pa.Field(nullable=True)
    auditee_name: str = pa.Field(nullable=True)
    auditee_state: str = pa.Field(nullable=True)
    entity_type: str = pa.Field(nullable=True)
    audit_year: int
    fy_start_date: dt.date = pa.Field(nullable=True)
    fy_end_date: dt.date = pa.Field(nullable=True)
    raw_file: str
    pull_date: dt.date

    class Config:
        strict = True
        unique = ["report_id"]


# ---------------------------------------------------------------- pull dates


def _urls(config: Config) -> dict[str, str]:
    settings = config.section(SOURCE)
    return {"federal_awards": settings["federal_awards_url"], "general": settings["general_url"]}


# ---------------------------------------------------------------------- pull


def pull(
    config: Config, pull_date: dt.date, *, download: raw_tree.Download = raw_tree.slow_download
) -> list[PulledFile]:
    """Fetch the configured FAC bulk CSVs into data/raw/fac/<Pull date>/."""
    return raw_tree.fetch(config.layout, SOURCE, pull_date, _urls(config).values(), download, LICENCE_CITATION)


# --------------------------------------------------------------------- clean


def _require(raw: pl.LazyFrame, columns: list[str], raw_file: str) -> None:
    missing = sorted(set(columns) - set(raw.collect_schema().names()))
    if missing:
        raise StructuralBreak(f"FAC {raw_file} lacks columns: {', '.join(missing)}")


def _blank_to_null(columns: list[str]) -> list[pl.Expr]:
    return [pl.col(c).str.strip_chars().replace("", None).alias(c) for c in columns]


def _cast(frame: pl.DataFrame, column: str, dtype, table: str) -> pl.DataFrame:
    """Cast a string column; a non-blank value that doesn't parse is a structural break."""
    parsed = frame[column].str.to_date("%Y-%m-%d", strict=False) if dtype is pl.Date else frame[column].cast(
        dtype, strict=False)
    bad = frame.filter(pl.col(column).is_not_null() & parsed.is_null())
    if bad.height:
        raise StructuralBreak(f"{table}: unreadable {column} {bad[column][0]!r} ({bad.height} rows)")
    return frame.with_columns(parsed.alias(column))


def _is_target_line() -> pl.Expr:
    prefix = pl.col("federal_agency_prefix").str.strip_chars()
    extension = pl.col("federal_award_extension").str.strip_chars().str.slice(0, 3)
    return pl.concat_str(prefix, pl.lit("."), extension).is_in(list(LISTINGS)).fill_null(False)


def clean_award_lines(raw: pl.DataFrame | pl.LazyFrame, *, raw_file: str, pull_date: dt.date) -> pl.DataFrame:
    """Raw federal_awards rows (all strings) -> TRIO/GEAR UP SEFA lines."""
    raw = raw.lazy()
    _require(raw, AWARD_LINE_KEEP, raw_file)
    lines = (
        raw.select(AWARD_LINE_KEEP)
        .filter(_is_target_line())
        .with_columns(_blank_to_null(AWARD_LINE_KEEP))
        .with_columns(
            pl.concat_str(
                pl.col("federal_agency_prefix"), pl.lit("."), pl.col("federal_award_extension").str.slice(0, 3)
            ).alias("listing"),
            pl.col("is_direct").str.to_uppercase(),
        )
        .collect()
    )
    lines = _cast(lines, "audit_year", pl.Int64, "FAC award lines")
    lines = _cast(lines, "amount_expended", pl.Int64, "FAC award lines")
    unknown = lines.filter(~pl.col("is_direct").is_in(["Y", "N"]).fill_null(False))
    if unknown.height:
        raise StructuralBreak(f"FAC award lines: is_direct must be Y or N, got {unknown['is_direct'][0]!r}")
    lines = (
        lines.with_columns(
            (pl.col("is_direct") == "Y").alias("is_direct"),
            pl.lit(raw_file).alias("raw_file"),
            pl.lit(pull_date).alias("pull_date"),
        )
        .select(list(FacAwardLines.to_schema().columns))
        .sort("report_id", "award_reference")
    )
    check_unique(lines, ["report_id", "award_reference"], "FAC award lines")
    return check_schema(FacAwardLines, lines, "FAC award lines")


def clean_audits(
    raw: pl.DataFrame | pl.LazyFrame, report_ids: pl.Series, *, raw_file: str, pull_date: dt.date
) -> pl.DataFrame:
    """Raw general rows (all strings) -> the audit reports that carry a TRIO/GEAR UP line."""
    raw = raw.lazy()
    _require(raw, AUDIT_KEEP, raw_file)
    audits = (
        raw.select(AUDIT_KEEP)
        .filter(pl.col("report_id").str.strip_chars().is_in(report_ids.implode()))
        .with_columns(_blank_to_null(AUDIT_KEEP))
        .collect()
    )
    audits = _cast(audits, "audit_year", pl.Int64, "FAC audits")
    for column in ("fy_start_date", "fy_end_date"):
        audits = _cast(audits, column, pl.Date, "FAC audits")
    audits = (
        audits.with_columns(pl.lit(raw_file).alias("raw_file"), pl.lit(pull_date).alias("pull_date"))
        .select(list(FacAudits.to_schema().columns))
        .sort("report_id")
    )
    check_unique(audits, ["report_id"], "FAC audits")
    return check_schema(FacAudits, audits, "FAC audits")


def clean(config: Config, pull_date: dt.date | None = None) -> pl.DataFrame:
    """Clean one FAC pull (default: the latest). No pull at all: no-op, empty frame."""
    layout = config.layout
    pull_date = pull_date or raw_tree.latest_pull_date(layout, SOURCE)
    if pull_date is None:
        return _empty(FacAwardLines)
    urls = _urls(config)
    paths = dict(zip(urls, raw_tree.pulled_paths(
        layout, SOURCE, pull_date, [raw_tree.file_name(url) for url in urls.values()], "FAC"
    )))
    input_hash = provenance.record_raw_inputs(config, SOURCE, list(paths.values()))

    raw_lines = pl.scan_csv(paths["federal_awards"], infer_schema=False)
    lines = clean_award_lines(raw_lines, raw_file=paths["federal_awards"].name, pull_date=pull_date)
    # Drops are counted on the raw rows in their own pass, not from the cleaned frame.
    counts = raw_lines.select(pl.len().alias("rows_in"), (~_is_target_line()).sum().alias("dropped")).collect().row(0)
    run_log.record(
        config, layer="clean", source=AWARD_LINES_TABLE, rows_in=counts[0], rows_out=lines.height,
        drops={DROP_NOT_A_LISTING: int(counts[1])}, pull_date=pull_date, input_hash=input_hash,
    )

    raw_audits = pl.scan_csv(paths["general"], infer_schema=False)
    audits = clean_audits(raw_audits, lines["report_id"].unique(), raw_file=paths["general"].name, pull_date=pull_date)
    has_line = pl.col("report_id").str.strip_chars().is_in(lines["report_id"].unique().implode())
    counts = raw_audits.select(pl.len().alias("rows_in"), (~has_line).sum().alias("dropped")).collect().row(0)
    run_log.record(
        config, layer="clean", source=AUDITS_TABLE, rows_in=counts[0], rows_out=audits.height,
        drops={DROP_NO_LINE: int(counts[1])}, pull_date=pull_date, input_hash=input_hash,
    )

    layout.cleaned.mkdir(parents=True, exist_ok=True)
    lines.write_parquet(layout.cleaned_table(AWARD_LINES_TABLE))
    audits.write_parquet(layout.cleaned_table(AUDITS_TABLE))
    return lines


def _empty(model: type[pa.DataFrameModel]) -> pl.DataFrame:
    return pl.DataFrame(schema={name: col.dtype.type for name, col in model.to_schema().columns.items()})


def read_award_lines(config: Config) -> pl.DataFrame:
    """The cleaned FAC TRIO/GEAR UP lines; empty when FAC was never pulled and cleaned."""
    path = config.layout.cleaned_table(AWARD_LINES_TABLE)
    return pl.read_parquet(path) if path.exists() else _empty(FacAwardLines)


def read_audits(config: Config) -> pl.DataFrame:
    """The cleaned FAC audit reports; empty when FAC was never pulled and cleaned."""
    path = config.layout.cleaned_table(AUDITS_TABLE)
    return pl.read_parquet(path) if path.exists() else _empty(FacAudits)
