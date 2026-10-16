"""USAspending Award Data Archive (per-agency assistance files): pull and clean.

Raw layout: data/raw/usaspending/<Pull date>/FY<fy>_<agency>_Assistance_Full_<yyyymmdd>[_<n>].{zip,csv}
The directory name is the Pull date. The newest directory is "the latest
USAspending Pull date", which is the As-of default.

Clean reads only an allow-list of archive columns. DUNS columns (D&B terms) and
highly-compensated-officer columns (individual people) are never read, so
they can't reach any later layer.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandera.polars as pa
import polars as pl

from topo import provenance
from topo.config import Config, Layout
from topo.domain.programs import LISTINGS
from topo.fiscal import fiscal_year
from topo.guards import StructuralBreak, check_schema, check_unique

SOURCE = "usaspending"
CLEANED_TABLE = "usaspending_actions"

API = "https://api.usaspending.gov/api/v2"
LICENCE_CITATION = (
    "USAspending.gov, U.S. Department of Treasury, Bureau of the Fiscal Service, "
    "https://www.usaspending.gov (Licensing: https://www.usaspending.gov/about; "
    "D&B limitation: https://www.usaspending.gov/db-info)"
)

# archive column -> cleaned column. Nothing outside this map is ever read.
KEEP_COLUMNS: dict[str, str] = {
    "assistance_transaction_unique_key": "transaction_key",
    "assistance_award_unique_key": "award_key",
    "award_id_fain": "fain",
    "modification_number": "modification_number",
    "action_date": "action_date",
    "action_type_code": "action_type",
    "federal_action_obligation": "obligation",
    "period_of_performance_start_date": "budget_period_start",
    "period_of_performance_current_end_date": "budget_period_end",
    "cfda_number": "listing",
    "awarding_agency_code": "awarding_agency_code",
    "awarding_agency_name": "awarding_agency_name",
    "funding_agency_code": "funding_agency_code",
    "funding_agency_name": "funding_agency_name",
    "recipient_uei": "recipient_uei",
    "recipient_name": "recipient_name",
    "recipient_name_raw": "recipient_name_raw",
    "recipient_address_line_1": "recipient_address_line_1",
    "recipient_city_name": "recipient_city",
    "recipient_state_code": "recipient_state",
    "recipient_zip_code": "recipient_zip",
    "transaction_description": "transaction_description",
    "prime_award_base_transaction_description": "base_transaction_description",
    "business_types_description": "business_types",
}


class UsaspendingActions(pa.DataFrameModel):
    """Cleaned funding actions (one row per transaction) on TRIO/GEAR UP listings."""

    transaction_key: str = pa.Field(unique=True)
    award_key: str
    fain: str
    modification_number: str = pa.Field(nullable=True)
    action_date: dt.date
    action_fy: int
    action_type: str = pa.Field(nullable=True)
    obligation: float
    budget_period_start: dt.date = pa.Field(nullable=True)
    budget_period_end: dt.date = pa.Field(nullable=True)
    listing: str = pa.Field(isin=list(LISTINGS))
    awarding_agency_code: str = pa.Field(nullable=True)
    awarding_agency_name: str = pa.Field(nullable=True)
    funding_agency_code: str = pa.Field(nullable=True)
    funding_agency_name: str = pa.Field(nullable=True)
    recipient_uei: str = pa.Field(nullable=True)
    recipient_name: str = pa.Field(nullable=True)
    recipient_name_raw: str = pa.Field(nullable=True)
    recipient_address_line_1: str = pa.Field(nullable=True)
    recipient_city: str = pa.Field(nullable=True)
    recipient_state: str = pa.Field(nullable=True)
    recipient_zip: str = pa.Field(nullable=True)
    transaction_description: str = pa.Field(nullable=True)
    base_transaction_description: str = pa.Field(nullable=True)
    business_types: str = pa.Field(nullable=True)
    raw_file: str
    pull_date: dt.date

    class Config:
        strict = True


# ---------------------------------------------------------------- pull dates


def pull_dates(layout: Layout) -> list[dt.date]:
    """Pull dates present in the raw tree, oldest first."""
    root = layout.raw_source(SOURCE)
    if not root.is_dir():
        return []
    found = []
    for child in root.iterdir():
        if child.is_dir():
            try:
                found.append(dt.date.fromisoformat(child.name))
            except ValueError:
                continue
    return sorted(found)


def latest_pull_date(layout: Layout) -> dt.date:
    dates = pull_dates(layout)
    if not dates:
        raise StructuralBreak(f"no USAspending pull found under {layout.raw_source(SOURCE)}")
    return dates[-1]


# ---------------------------------------------------------------------- pull


@dataclass(frozen=True)
class PulledFile:
    """One fetched raw file, with what a manifest row needs."""

    source: str
    request: str
    url: str
    path: Path
    pull_date: dt.date
    bytes: int
    sha256: str
    licence_citation: str = LICENCE_CITATION


PostJson = Callable[[str, dict], dict]
Download = Callable[[str, Path], None]


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=600) as response, dest.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)


def pull(
    config: Config,
    pull_date: dt.date,
    *,
    post_json: PostJson = _post_json,
    download: Download = _download,
) -> list[PulledFile]:
    """Fetch the monthly Full assistance archive per configured agency and fiscal year.

    Fiscal years run from `[usaspending] pull_from_fy` through the FY of the Pull date.
    Files are fetched serially (polite to the API host).
    """
    settings = config.section(SOURCE)
    folder = config.layout.raw_source(SOURCE) / pull_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    pulled: list[PulledFile] = []
    for agency in settings["archive_agencies"]:
        for fy in range(int(settings["pull_from_fy"]), fiscal_year(pull_date) + 1):
            payload = {"agency": int(agency["bulk_agency_id"]), "fiscal_year": fy, "type": "assistance"}
            listing_url = f"{API}/bulk_download/list_monthly_files/"
            files = post_json(listing_url, payload).get("monthly_files", [])
            for entry in files:
                if "_Full_" not in entry["file_name"]:
                    continue
                dest = folder / entry["file_name"]
                download(entry["url"], dest)
                data = dest.read_bytes()
                pulled.append(
                    PulledFile(
                        source=SOURCE,
                        request=f"POST {listing_url} {json.dumps(payload, sort_keys=True)}",
                        url=entry["url"],
                        path=dest,
                        pull_date=pull_date,
                        bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                    )
                )
    return pulled


# --------------------------------------------------------------------- clean


def raw_files(layout: Layout, pull_date: dt.date) -> list[Path]:
    folder = layout.raw_source(SOURCE) / pull_date.isoformat()
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in {".csv", ".zip"})


def _read_csv(path: Path, label: str) -> pl.DataFrame:
    header = pl.read_csv(path, n_rows=0, infer_schema=False).columns
    missing = sorted(set(KEEP_COLUMNS) - set(header))
    if missing:
        raise StructuralBreak(f"{label} lacks archive columns: {', '.join(missing)}")
    return (
        pl.scan_csv(path, infer_schema=False)
        .select(list(KEEP_COLUMNS))
        .filter(pl.col("cfda_number").is_in(LISTINGS))
        .collect()
        .with_columns(pl.lit(label).alias("raw_file"))
    )


def _read_raw_file(path: Path) -> pl.DataFrame:
    if path.suffix.lower() == ".csv":
        return _read_csv(path, path.name)
    frames = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as tmp:
        for member in archive.namelist():
            if member.lower().endswith(".csv"):
                extracted = Path(archive.extract(member, tmp))
                frames.append(_read_csv(extracted, f"{path.name}:{member}"))
    return pl.concat(frames) if frames else pl.DataFrame()


def _to_date(column: str) -> pl.Expr:
    return pl.col(column).str.slice(0, 10).str.to_date("%Y-%m-%d", strict=True)


def clean(config: Config, pull_date: dt.date | None = None) -> pl.DataFrame:
    """Clean one USAspending pull (default: the latest) into the cleaned actions table."""
    layout = config.layout
    pull_date = pull_date or latest_pull_date(layout)
    files = raw_files(layout, pull_date)
    provenance.record_raw_inputs(config, SOURCE, files)
    frames = [_read_raw_file(p) for p in files]
    frames = [f for f in frames if f.height]
    if frames:
        raw = pl.concat(frames)
    else:
        raw = pl.DataFrame(schema={c: pl.String for c in [*KEEP_COLUMNS, "raw_file"]})
    actions = (
        raw.rename(KEEP_COLUMNS)
        .with_columns(
            pl.col(pl.String).str.strip_chars().replace("", None),
        )
        .with_columns(
            _to_date("action_date"),
            _to_date("budget_period_start"),
            _to_date("budget_period_end"),
            pl.col("obligation").cast(pl.Float64).fill_null(0.0),
            pl.col("fain").str.to_uppercase(),
            pl.lit(pull_date).alias("pull_date"),
        )
        .with_columns(
            (pl.col("action_date").dt.year() + (pl.col("action_date").dt.month() >= 10).cast(pl.Int32))
            .cast(pl.Int64)
            .alias("action_fy"),
        )
        .select(list(UsaspendingActions.to_schema().columns))
        .sort("fain", "action_date", "transaction_key")
    )
    check_unique(actions, "transaction_key", "USAspending actions")
    actions = check_schema(UsaspendingActions, actions, "USAspending actions")
    layout.cleaned.mkdir(parents=True, exist_ok=True)
    actions.write_parquet(layout.cleaned_table(CLEANED_TABLE))
    return actions


def read_cleaned(config: Config) -> pl.DataFrame:
    path = config.layout.cleaned_table(CLEANED_TABLE)
    if not path.exists():
        raise StructuralBreak(f"cleaned USAspending table missing; run `topo clean {SOURCE}` first ({path})")
    return pl.read_parquet(path)
