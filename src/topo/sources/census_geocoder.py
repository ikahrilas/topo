"""Census geocoder: Campus districts for college Hosts that have no EDGE campus point (fallback only).

`topo pull census_geocoder` reads the joined Host links and the cleaned EDGE
points and IPEDS directory, so it runs after a first `topo run`. For each
matched college Host (UNITID) with no EDGE point it makes one single-record
`geographies/address` call (batch calls return no school districts) with the
IPEDS street address, asking for the unified, secondary and elementary district
layers under the configured benchmark and vintage (`[census_geocoder]`; the
vintage should match the EDGE polygons' school year). Calls are made one at a
time with a pause between them. All replies go into one raw JSON file:

    data/raw/census_geocoder/<Pull date>/campus_district_lookups.json
        [{unitid, request, response}, ...]

Cleaned table:
    census_geocoder_campus_districts  one row per (UNITID, district): LEAID (the
        district GEOID), name, district type, and the benchmark/vintage as its year.
        Lookups with no address match (`no_address_match`) or no district at the
        matched address (`no_school_district_at_address`) give no rows.

Without any geocoder pull, `clean` is a no-op. No API key is needed.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request
from collections.abc import Callable
from urllib.parse import urlencode

import pandera.polars as pa
import polars as pl

from topo import provenance, run_log
from topo.config import Config
from topo.domain.host_linking import MATCHED, UNITID
from topo.guards import StructuralBreak, check_schema, check_unique
from topo.sources import edge, ipeds
from topo.sources import raw as raw_tree
from topo.sources.raw import PulledFile

SOURCE = "census_geocoder"
TABLE = "census_geocoder_campus_districts"
RAW_FILE = "campus_district_lookups.json"
DROP_NO_MATCH = "no_address_match"
DROP_NO_DISTRICT = "no_school_district_at_address"
HOST_LINKS = "host_links"

LAYERS = {
    "Unified School Districts": "unified",
    "Secondary School Districts": "secondary",
    "Elementary School Districts": "elementary",
}

LICENCE_CITATION = (
    "U.S. Census Bureau Geocoder (https://geocoding.geo.census.gov/geocoder/); "
    "U.S. Government work, not copyrighted"
)


class CensusGeocoderCampusDistricts(pa.DataFrameModel):
    unitid: str
    leaid: str
    district_name: str = pa.Field(nullable=True)
    district_type: str = pa.Field(isin=list(LAYERS.values()))
    school_year: str
    raw_file: str
    pull_date: dt.date

    class Config:
        strict = True
        unique = ["unitid", "leaid"]


GetJson = Callable[[str], dict]


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.loads(response.read())


def _hosts_without_a_point(config: Config) -> pl.DataFrame:
    """Matched college Hosts with no EDGE point, with their latest IPEDS address."""
    links_path = config.layout.joined_table(HOST_LINKS)
    if not links_path.exists():
        raise StructuralBreak(f"no joined Host links; run `topo run` before pulling {SOURCE} ({links_path})")
    links = pl.read_parquet(links_path)
    colleges = links.filter((pl.col("outcome") == MATCHED) & (pl.col("host_kind") == UNITID))["host_id"].unique()
    with_point = edge.read_geocodes(config)["unitid"]
    directory = ipeds.read_directory(config).sort("unitid", "year").group_by("unitid").last()
    return (
        directory.filter(pl.col("unitid").is_in(colleges.implode()) & ~pl.col("unitid").is_in(with_point.implode()))
        .filter(pl.col("address").is_not_null())
        .select("unitid", "address", "city", "state_abbr", "zip")
        .sort("unitid")
    )


def pull(
    config: Config, pull_date: dt.date, *, get_json: GetJson = _get_json, pause: Callable[[float], None] = time.sleep
) -> list[PulledFile]:
    """Look up the Campus districts of college Hosts with no EDGE point, one polite call at a time."""
    settings = config.section(SOURCE)
    lookups = []
    for i, host in enumerate(_hosts_without_a_point(config).iter_rows(named=True)):
        if i:
            pause(float(settings["pause_seconds"]))
        query = urlencode({
            "street": host["address"], "city": host["city"] or "", "state": host["state_abbr"] or "",
            "zip": host["zip"] or "", "benchmark": settings["benchmark"], "vintage": settings["vintage"],
            "layers": ",".join(LAYERS), "format": "json",
        })
        url = f"{settings['url']}?{query}"
        lookups.append({"unitid": host["unitid"], "request": url, "response": get_json(url)})
    folder = raw_tree.pull_folder(config.layout, SOURCE, pull_date)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / RAW_FILE
    dest.write_bytes(json.dumps(lookups, indent=1).encode())
    request = f"GET {settings['url']} x{len(lookups)} (one per college Host with no EDGE point)"
    return [raw_tree.described(SOURCE, request, settings["url"], dest, pull_date, LICENCE_CITATION)]


def clean_lookups(lookups: list[dict], *, year: str, raw_file: str, pull_date: dt.date) -> pl.DataFrame:
    rows = []
    for lookup in lookups:
        matches = (lookup.get("response") or {}).get("result", {}).get("addressMatches") or []
        if not matches:
            continue
        geographies = matches[0].get("geographies") or {}
        for layer, district_type in LAYERS.items():
            for found in geographies.get(layer) or []:
                rows.append((lookup["unitid"], found["GEOID"], found.get("NAME"), district_type))
    schema = {name: col.dtype.type for name, col in CensusGeocoderCampusDistricts.to_schema().columns.items()}
    districts = pl.DataFrame(
        rows, schema=["unitid", "leaid", "district_name", "district_type"], orient="row"
    ).with_columns(
        pl.lit(year).alias("school_year"), pl.lit(raw_file).alias("raw_file"), pl.lit(pull_date).alias("pull_date")
    ).cast(schema).sort("unitid", "leaid")
    check_unique(districts, ["unitid", "leaid"], "Census geocoder campus districts")
    return check_schema(CensusGeocoderCampusDistricts, districts, "Census geocoder campus districts")


def clean(config: Config, pull_date: dt.date | None = None) -> pl.DataFrame:
    """Clean one geocoder pull (default: the latest). No pull at all: no-op, empty frame."""
    layout = config.layout
    pull_date = pull_date or raw_tree.latest_pull_date(layout, SOURCE)
    if pull_date is None:
        return _empty()
    [path] = raw_tree.pulled_paths(layout, SOURCE, pull_date, [RAW_FILE], "Census geocoder")
    lookups = json.loads(path.read_text())
    settings = config.section(SOURCE)
    input_hash = provenance.record_raw_inputs(config, SOURCE, [path])
    districts = clean_lookups(
        lookups, year=f"Census geocoder {settings['benchmark']}/{settings['vintage']}", raw_file=RAW_FILE,
        pull_date=pull_date,
    )
    # Logged per lookup (one per Host): matched, or dropped with no address match.
    matched = districts["unitid"].n_unique()
    no_match = sum(1 for lk in lookups if not ((lk.get("response") or {}).get("result", {}).get("addressMatches")))
    no_district = sum(
        1 for lk in lookups
        if (lk.get("response") or {}).get("result", {}).get("addressMatches")
        and not any((lk["response"]["result"]["addressMatches"][0].get("geographies") or {}).get(layer) for layer in LAYERS)
    )
    run_log.record(
        config, layer="clean", source=TABLE, rows_in=len(lookups), rows_out=matched,
        drops={DROP_NO_MATCH: no_match, DROP_NO_DISTRICT: no_district}, pull_date=pull_date, input_hash=input_hash,
    )
    layout.cleaned.mkdir(parents=True, exist_ok=True)
    districts.write_parquet(layout.cleaned_table(TABLE))
    return districts


def _empty() -> pl.DataFrame:
    return pl.DataFrame(
        schema={name: col.dtype.type for name, col in CensusGeocoderCampusDistricts.to_schema().columns.items()}
    )


def read_campus_districts(config: Config) -> pl.DataFrame:
    path = config.layout.cleaned_table(TABLE)
    return pl.read_parquet(path) if path.exists() else _empty()
