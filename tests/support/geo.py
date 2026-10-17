"""Hand-built Local context fixtures: EDGE postsecondary geocodes, EDGE district polygons, the SAIPE flat file.

Polygons are written as a zipped shapefile (as EDGE ships them) with DuckDB
spatial. Coordinates are lon/lat degrees; fixture districts are small boxes.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import duckdb
from openpyxl import Workbook

GEOCODE_ZIP = "EDGE_GEOCODE_POSTSECSCH_2526.zip"
DISTRICTS_ZIP = "EDGE_SCHOOLDISTRICT_TL25_SY2425.zip"
SAIPE_CSV = "ussd24.csv"

# EDGE geocode columns (a subset of the published file, plus ones the pipeline ignores).
GEOCODE_COLUMNS = ["UNITID", "NAME", "STREET", "CITY", "STATE", "ZIP", "LAT", "LON", "LOCALE", "SCHOOLYEAR"]

# MTFCC codes for school district polygons.
ELEMENTARY, SECONDARY, UNIFIED = "G5400", "G5410", "G5420"

# The real ussd24.csv header (Census codes, no title line): total population, state FIPS,
# district id, name, state postal code, relevant children 5-17 in poverty, children 5-17.
SAIPE_HEADER = ["rpopall_24", "state", "distid", "name", "STABREV", "saepov5_17rv_24", "rpop5_17v_24"]


def geocode_row(unitid: str, name: str, state: str, lat: float | str, lon: float | str) -> dict[str, str]:
    return {
        "UNITID": unitid, "NAME": name, "STREET": "1 MAIN ST", "CITY": "ANYTOWN", "STATE": state, "ZIP": "00000",
        "LAT": str(lat), "LON": str(lon), "LOCALE": "11", "SCHOOLYEAR": "2025-2026",
    }


def write_geocodes(path: Path, rows: list[dict[str, str]]) -> Path:
    """A zip holding the geocodes as XLSX (plus a readme the pipeline ignores)."""
    book = Workbook()
    sheet = book.active
    sheet.append(GEOCODE_COLUMNS)
    for row in rows:
        sheet.append([_number(row[c]) if c in ("LAT", "LON") else row[c] for c in GEOCODE_COLUMNS])
    buffer = io.BytesIO()
    book.save(buffer)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("EDGE_GEOCODE_POSTSECSCH_2526/EDGE_GEOCODE_POSTSECSCH_2526.xlsx", buffer.getvalue())
        z.writestr("EDGE_GEOCODE_POSTSECSCH_2526/readme.txt", "fixture")
    return path


def _number(value: str):
    try:
        return float(value)
    except ValueError:
        return value or None


def box(west: float, south: float, east: float, north: float) -> str:
    return f"POLYGON(({west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}))"


def district(geoid: str, name: str, mtfcc: str, polygon: str) -> dict[str, str]:
    return {"GEOID": geoid, "NAME": name, "MTFCC": mtfcc, "SCHOOLYEAR": "2024-2025", "wkt": polygon}


def write_districts(path: Path, rows: list[dict[str, str]]) -> Path:
    """A zip holding one composite district shapefile, as EDGE ships it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.parent / f".{path.stem}_shp"
    work.mkdir(exist_ok=True)
    con = duckdb.connect()
    con.execute("LOAD spatial")
    con.execute("CREATE TABLE d (GEOID VARCHAR, NAME VARCHAR, MTFCC VARCHAR, SCHOOLYEAR VARCHAR, wkt VARCHAR)")
    con.executemany("INSERT INTO d VALUES (?, ?, ?, ?, ?)", [list(r.values()) for r in rows])
    shp = work / "EDGE_SCHOOLDISTRICT_TL25_SY2425.shp"
    con.execute(
        f"COPY (SELECT GEOID, NAME, MTFCC, SCHOOLYEAR, ST_GeomFromText(wkt) AS geom FROM d) "
        f"TO '{shp}' (FORMAT GDAL, DRIVER 'ESRI Shapefile')"
    )
    with zipfile.ZipFile(path, "w") as z:
        for part in sorted(work.iterdir()):
            z.write(part, part.name)
            part.unlink()
    work.rmdir()
    return path


def saipe_row(state: str, fips: str, district_id: str, name: str, children: int, poor: int) -> list[str]:
    return [str(children * 6), fips, district_id, name, state, str(poor), str(children)]


def write_saipe(path: Path, rows: list[list[str]]) -> Path:
    """The Census flat file as published: the header row, then one row per district, Windows-1252."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="cp1252") as f:
        writer = csv.writer(f)
        writer.writerow(SAIPE_HEADER)
        writer.writerows(rows)
    return path
