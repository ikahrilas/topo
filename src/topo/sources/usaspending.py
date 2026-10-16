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
import json
import tempfile
import urllib.request
import zipfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pandera.polars as pa
import polars as pl

from topo import provenance, run_log
from topo.config import Config, Layout
from topo.domain.programs import LISTINGS
from topo.fiscal import fiscal_year
from topo.guards import StructuralBreak, check_schema, check_unique
from topo.sources import raw as raw_tree
from topo.sources.raw import PulledFile  # noqa: F401  (re-exported: sources' pull results)

SOURCE = "usaspending"
CLEANED_TABLE = "usaspending_actions"
DROP_NOT_A_TARGET_LISTING = "not_a_trio_gear_up_listing"

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


def latest_pull_date(layout: Layout) -> dt.date:
    """The latest USAspending Pull date; the pipeline cannot run without one."""
    latest = raw_tree.latest_pull_date(layout, SOURCE)
    if latest is None:
        raise StructuralBreak(f"no USAspending pull found under {layout.raw_source(SOURCE)}")
    return latest


# ---------------------------------------------------------------------- pull


PostJson = Callable[[str, dict], dict]


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def pull(
    config: Config,
    pull_date: dt.date,
    *,
    post_json: PostJson = _post_json,
    download: raw_tree.Download = raw_tree.download,
) -> list[PulledFile]:
    """Fetch the monthly Full assistance archive per configured agency and fiscal year.

    Fiscal years run from `[usaspending] pull_from_fy` through the FY of the Pull date.
    Files are fetched serially (polite to the API host).
    """
    settings = config.section(SOURCE)
    folder = raw_tree.pull_folder(config.layout, SOURCE, pull_date)
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
                request = f"POST {listing_url} {json.dumps(payload, sort_keys=True)}"
                pulled.append(raw_tree.described(SOURCE, request, entry["url"], dest, pull_date, LICENCE_CITATION))
    return pulled


# --------------------------------------------------------------------- clean


def raw_files(layout: Layout, pull_date: dt.date) -> list[Path]:
    folder = raw_tree.pull_folder(layout, SOURCE, pull_date)
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in {".csv", ".zip"})


def _read_csv(path: Path, label: str, tally: Counter) -> pl.DataFrame:
    header = pl.read_csv(path, n_rows=0, infer_schema=False).columns
    missing = sorted(set(KEEP_COLUMNS) - set(header))
    if missing:
        raise StructuralBreak(f"{label} lacks archive columns: {', '.join(missing)}")
    # Counted in their own pass so the run log's row balance is a real check.
    rows_in, off_listing = (
        pl.scan_csv(path, infer_schema=False)
        .select(pl.len(), (~pl.col("cfda_number").is_in(LISTINGS)).fill_null(True).sum())
        .collect()
        .row(0)
    )
    tally["rows_in"] += rows_in
    tally[DROP_NOT_A_TARGET_LISTING] += off_listing
    return (
        pl.scan_csv(path, infer_schema=False)
        .select(list(KEEP_COLUMNS))
        .filter(pl.col("cfda_number").is_in(LISTINGS))
        .collect()
        .with_columns(pl.lit(label).alias("raw_file"))
    )


def _read_raw_file(path: Path, tally: Counter) -> pl.DataFrame:
    if path.suffix.lower() == ".csv":
        return _read_csv(path, path.name, tally)
    frames = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as tmp:
        for member in archive.namelist():
            if member.lower().endswith(".csv"):
                extracted = Path(archive.extract(member, tmp))
                frames.append(_read_csv(extracted, f"{path.name}:{member}", tally))
    return pl.concat(frames) if frames else pl.DataFrame()


def _to_date(column: str) -> pl.Expr:
    return pl.col(column).str.slice(0, 10).str.to_date("%Y-%m-%d", strict=True)


def clean(config: Config, pull_date: dt.date | None = None) -> pl.DataFrame:
    """Clean one USAspending pull (default: the latest) into the cleaned actions table."""
    layout = config.layout
    pull_date = pull_date or latest_pull_date(layout)
    files = raw_files(layout, pull_date)
    input_hash = provenance.record_raw_inputs(config, SOURCE, files)
    tally: Counter = Counter()
    frames = [_read_raw_file(p, tally) for p in files]
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
    run_log.record(
        config, layer="clean", source=SOURCE, rows_in=tally["rows_in"], rows_out=actions.height,
        drops={DROP_NOT_A_TARGET_LISTING: tally[DROP_NOT_A_TARGET_LISTING]}, pull_date=pull_date,
        input_hash=input_hash,
    )
    layout.cleaned.mkdir(parents=True, exist_ok=True)
    actions.write_parquet(layout.cleaned_table(CLEANED_TABLE))
    return actions


def read_cleaned(config: Config) -> pl.DataFrame:
    path = config.layout.cleaned_table(CLEANED_TABLE)
    if not path.exists():
        raise StructuralBreak(f"cleaned USAspending table missing; run `topo clean {SOURCE}` first ({path})")
    return pl.read_parquet(path)
