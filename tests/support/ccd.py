"""Hand-built Urban CCD LEA directory fixtures: raw bulk-CSV rows and cleaned frames.

Each fixture row is one (LEAID, year) district directory record. Urban codes
missing values as -1, -2 or -3. CCD agency types: 1 regular, 2 component of a
supervisory union, 3 supervisory union, 4 regional education service agency,
5 state agency, 7 independent charter, 8 other, 9 specialized public school.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

# The Urban LEA directory columns the pipeline reads, plus a few it must ignore.
LEA_COLUMNS = [
    "leaid", "year", "lea_name", "fips", "state_leaid", "state_location", "street_location",
    "city_location", "zip_location", "agency_type", "phone", "number_of_schools",
]

LEA_CSV = "school-districts_lea_directory.csv"


def lea_row(
    leaid: str,
    name: str,
    state: str,
    *,
    year: int = 2024,
    agency_type: int = 1,
    city: str = "ANYTOWN",
    zip: str = "00000",
) -> dict[str, str]:
    return {
        "leaid": leaid,
        "year": str(year),
        "lea_name": name,
        "fips": "1",
        "state_leaid": f"{state}-{leaid}",
        "state_location": state,
        "street_location": "1 SCHOOL ST",
        "city_location": city,
        "zip_location": zip,
        "agency_type": str(agency_type),
        "phone": "5555555555",
        "number_of_schools": "12",
    }


def lea_directory(*rows: dict[str, str]) -> pl.DataFrame:
    """A cleaned CCD LEA directory frame built from raw-shaped fixture rows."""
    from topo.sources.ccd import clean_lea_directory

    raw = pl.DataFrame([{c: r.get(c, "") for c in LEA_COLUMNS} for r in rows], schema={c: pl.String for c in LEA_COLUMNS})
    return clean_lea_directory(
        raw, from_year=2015, agency_types=[1, 2, 4, 5, 7], raw_file="fixture.csv", pull_date=dt.date(2026, 10, 7)
    )
