"""Local context: institution type, enrollment and the ages 5-17 poverty rate, via the Host institution.

Context attaches only through a Grant's Host (never the Recipient, never the
state), as one latest snapshot with each field's data year:

    college Host (UNITID)  institution type = IPEDS sector (control and level) of the
                           latest directory year; enrollment = latest IPEDS total fall
                           enrollment; poverty rate = SAIPE rate of the Campus district.
    district Host (LEAID)  institution type = CCD agency type and enrollment = CCD,
                           latest directory year; poverty rate = SAIPE rate of the LEAID.

The Campus district is found by point-in-polygon of the EDGE campus point
against EDGE district polygons (DuckDB spatial); a Census geocoder result is
used only for a Host with no EDGE point. A campus inside several districts
keeps them all: a unified or secondary district is primary (before an
elementary one) and the overlap is flagged.

Null context carries a reason code (`|`-joined when several apply):
    in_review, no_single_host, unmatched   the Host link has no single Host (all fields null)
    no_saipe_row                           the Host's or Campus district's LEAID has no SAIPE row
    no_campus_district                     a college Host with no located Campus district
    no_enrollment_row                      no enrollment reported for the Host
"""

from __future__ import annotations

from pathlib import Path

import pandera.polars as pa
import polars as pl

from topo import spatial
from topo.domain.host_linking import LEAID, MATCHED, NO_SINGLE_HOST, REVIEW, UNITID, UNMATCHED
from topo.guards import check_schema

IN_REVIEW = "in_review"
NO_SAIPE_ROW = "no_saipe_row"
NO_CAMPUS_DISTRICT = "no_campus_district"
NO_ENROLLMENT_ROW = "no_enrollment_row"
OUTCOME_REASONS = {REVIEW: IN_REVIEW, NO_SINGLE_HOST: NO_SINGLE_HOST, UNMATCHED: UNMATCHED}
REASON_CODES = (NO_SAIPE_ROW, NO_CAMPUS_DISTRICT, NO_ENROLLMENT_ROW, NO_SINGLE_HOST, UNMATCHED, IN_REVIEW)

CAMPUS_DISTRICT = "campus_district"
HOST_DISTRICT = "host_district"
EDGE_POINT = "edge_point"
CENSUS_GEOCODER = "census_geocoder"

# A unified or secondary district is primary over an elementary one.
DISTRICT_TYPE_RANK = {"unified": 0, "secondary": 1, "elementary": 2, "administrative": 3}

IPEDS_SECTORS = {
    0: "Administrative unit",
    1: "Public, 4-year or above",
    2: "Private nonprofit, 4-year or above",
    3: "Private for-profit, 4-year or above",
    4: "Public, 2-year",
    5: "Private nonprofit, 2-year",
    6: "Private for-profit, 2-year",
    7: "Public, less-than 2-year",
    8: "Private nonprofit, less-than 2-year",
    9: "Private for-profit, less-than 2-year",
}
CCD_AGENCY_TYPES = {
    1: "Regular school district",
    2: "Component of a supervisory union",
    3: "Supervisory union",
    4: "Regional education service agency",
    5: "State agency",
    6: "Federal agency",
    7: "Independent charter district",
    8: "Other education agency",
    9: "Specialized public school district",
}


class CampusDistricts(pa.DataFrameModel):
    """Every district a college Host's campus lies in: (UNITID, LEAID)."""

    unitid: str
    leaid: str
    district_name: str = pa.Field(nullable=True)
    district_type: str = pa.Field(isin=list(DISTRICT_TYPE_RANK))
    school_year: str = pa.Field(nullable=True)
    is_primary: bool
    overlap: bool
    located_by: str = pa.Field(isin=[EDGE_POINT, CENSUS_GEOCODER])

    class Config:
        strict = True
        unique = ["unitid", "leaid"]


class LocalContext(pa.DataFrameModel):
    """One Local context row per Grant (FAIN), keyed to its Host."""

    fain: str = pa.Field(unique=True)
    host_kind: str = pa.Field(nullable=True)
    host_id: str = pa.Field(nullable=True)
    institution_type: str = pa.Field(nullable=True)
    institution_type_year: int = pa.Field(nullable=True)
    enrollment: int = pa.Field(nullable=True)
    enrollment_year: int = pa.Field(nullable=True)
    poverty_rate_5_17: float = pa.Field(nullable=True, ge=0, le=1)
    poverty_rate_basis: str = pa.Field(nullable=True, isin=[CAMPUS_DISTRICT, HOST_DISTRICT])
    poverty_district_leaid: str = pa.Field(nullable=True)
    poverty_district_name: str = pa.Field(nullable=True)
    poverty_rate_year: int = pa.Field(nullable=True)
    campus_district_year: str = pa.Field(nullable=True)
    campus_district_overlap: str = pa.Field(nullable=True)
    context_reason: str = pa.Field(nullable=True)

    class Config:
        strict = True


def _empty(model: type[pa.DataFrameModel]) -> pl.DataFrame:
    return pl.DataFrame(schema={name: col.dtype.type for name, col in model.to_schema().columns.items()})


# ---------------------------------------------------------- Campus district


def locate_campus_districts(
    points: pl.DataFrame, polygons: Path | None, geocoded: pl.DataFrame | None = None
) -> pl.DataFrame:
    """Campus districts of college Hosts.

    `points`: unitid, lat, lon (EDGE campus points). `polygons`: the cleaned EDGE
    district parquet (leaid, district_name, district_type, school_year, wkb), or None.
    `geocoded`: Census geocoder districts (unitid, leaid, district_name, district_type,
    school_year), used only for UNITIDs with no EDGE point.
    """
    hits: list[tuple] = []
    if polygons is not None and polygons.exists() and points.height:
        con = spatial.connect()
        con.execute("CREATE TABLE points (unitid VARCHAR, lat DOUBLE, lon DOUBLE)")
        con.executemany("INSERT INTO points VALUES (?, ?, ?)", points.select("unitid", "lat", "lon").rows())
        hits = con.execute(
            f"""
            SELECT p.unitid, d.leaid, d.district_name, d.district_type, d.school_year
            FROM points p
            JOIN (SELECT *, ST_GeomFromWKB(wkb) AS geom
                  FROM read_parquet({spatial.sql_string(polygons.resolve().as_posix())})) d
              ON ST_Contains(d.geom, ST_Point(p.lon, p.lat))
            """
        ).fetchall()
        con.close()
    located = pl.DataFrame(
        hits, schema=["unitid", "leaid", "district_name", "district_type", "school_year"], orient="row"
    ).with_columns(pl.lit(EDGE_POINT).alias("located_by"))
    if geocoded is not None and geocoded.height:
        fallback = geocoded.filter(~pl.col("unitid").is_in(points["unitid"].implode())).select(
            "unitid", "leaid", "district_name", "district_type", "school_year", pl.lit(CENSUS_GEOCODER).alias("located_by")
        )
        located = pl.concat([located, fallback], how="vertical_relaxed")
    if not located.height:
        return _empty(CampusDistricts)
    ranked = (
        located.unique(["unitid", "leaid"], keep="first")
        .with_columns(pl.col("district_type").replace_strict(DISTRICT_TYPE_RANK, return_dtype=pl.Int64).alias("rank"))
        .sort("unitid", "rank", "leaid")
        .with_columns(
            (pl.int_range(pl.len()).over("unitid") == 0).alias("is_primary"),
            (pl.len().over("unitid") > 1).alias("overlap"),
        )
        .select(list(CampusDistricts.to_schema().columns))
    )
    return check_schema(CampusDistricts, ranked, "campus districts")


# ------------------------------------------------------------ Local context


def _latest(frame: pl.DataFrame, key: str, value: str) -> dict[str, tuple]:
    """key -> (value, year) from each key's latest year with a non-null value."""
    rows = frame.filter(pl.col(value).is_not_null()).sort(key, "year").group_by(key).last()
    return {r[key]: (r[value], r["year"]) for r in rows.iter_rows(named=True)}


def build_local_context(
    host_links: pl.DataFrame,
    *,
    ipeds_directory: pl.DataFrame,
    ipeds_enrollment: pl.DataFrame,
    lea_directory: pl.DataFrame,
    campus_districts: pl.DataFrame,
    saipe: pl.DataFrame,
) -> pl.DataFrame:
    """One Local context row per Host link (FAIN)."""
    sectors = _latest(ipeds_directory, "unitid", "sector")
    college_enrollment = _latest(ipeds_enrollment, "unitid", "enrollment")
    agency_types = _latest(lea_directory, "leaid", "agency_type")
    district_enrollment = _latest(lea_directory, "leaid", "enrollment")
    poverty = {r["leaid"]: r for r in saipe.iter_rows(named=True)}
    districts: dict[str, list[dict]] = {}
    for r in campus_districts.sort("unitid", "is_primary", descending=[False, True]).iter_rows(named=True):
        districts.setdefault(r["unitid"], []).append(r)

    rows = []
    for link in host_links.iter_rows(named=True):
        row = {name: None for name in LocalContext.to_schema().columns}
        row.update(fain=link["fain"], host_kind=link["host_kind"], host_id=link["host_id"])
        reasons: list[str] = []
        if link["outcome"] != MATCHED:
            row["context_reason"] = OUTCOME_REASONS[link["outcome"]]
            rows.append(row)
            continue
        host = link["host_id"]
        if link["host_kind"] == UNITID:
            sector, row["institution_type_year"] = sectors.get(host, (None, None))
            row["institution_type"] = IPEDS_SECTORS.get(sector)
            row["enrollment"], row["enrollment_year"] = college_enrollment.get(host, (None, None))
            campus = districts.get(host, [])
            if campus:
                primary, others = campus[0], campus[1:]
                row.update(
                    poverty_rate_basis=CAMPUS_DISTRICT, poverty_district_leaid=primary["leaid"],
                    poverty_district_name=primary["district_name"], campus_district_year=primary["school_year"],
                )
                if others:
                    row["campus_district_overlap"] = "; ".join(
                        f"also in {o['district_type']} district {o['district_name']} (LEAID {o['leaid']})"
                        for o in others
                    )
        elif link["host_kind"] == LEAID:
            agency_type, row["institution_type_year"] = agency_types.get(host, (None, None))
            row["institution_type"] = CCD_AGENCY_TYPES.get(agency_type)
            row["enrollment"], row["enrollment_year"] = district_enrollment.get(host, (None, None))
            row.update(poverty_rate_basis=HOST_DISTRICT, poverty_district_leaid=host)
        if row["enrollment"] is None:
            reasons.append(NO_ENROLLMENT_ROW)
        leaid = row["poverty_district_leaid"]
        if leaid is None:
            reasons.append(NO_CAMPUS_DISTRICT)
        elif leaid in poverty:
            estimate = poverty[leaid]
            row.update(poverty_rate_5_17=estimate["poverty_rate_5_17"], poverty_rate_year=estimate["data_year"])
            if row["poverty_district_name"] is None:
                row["poverty_district_name"] = estimate["district_name"]
        else:
            reasons.append(NO_SAIPE_ROW)
            row.update(poverty_rate_basis=None, poverty_district_leaid=None, poverty_district_name=None)
        row["context_reason"] = "|".join(reasons) or None
        rows.append(row)

    schema = {name: col.dtype.type for name, col in LocalContext.to_schema().columns.items()}
    context = pl.DataFrame(rows, schema=schema, orient="row") if rows else _empty(LocalContext)
    return check_schema(LocalContext, context.sort("fain"), "local context")


def context_reason_counts(local_context: pl.DataFrame) -> pl.DataFrame:
    """Grants per context reason code (every code listed, zero included)."""
    codes = local_context["context_reason"].drop_nulls().str.split("|").explode()
    counted = codes.value_counts()
    found = dict(zip(counted[counted.columns[0]].to_list(), counted["count"].to_list()))
    return pl.DataFrame(
        {"context_reason": list(REASON_CODES), "grants": [found.get(code, 0) for code in REASON_CODES]},
        schema={"context_reason": pl.String, "grants": pl.Int64},
    )
