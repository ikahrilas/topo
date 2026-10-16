"""Hand-built Urban IPEDS fixtures: raw bulk-CSV rows and cleaned directory frames.

Urban codes missing values as -1, -2 or -3. A unit's UEIs are one `|`-separated
field. Each fixture row is one (UNITID, year) directory record.
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import polars as pl

# The Urban directory columns the pipeline reads, plus a few it must ignore.
DIRECTORY_COLUMNS = [
    "unitid", "year", "opeid", "inst_name", "inst_alias", "ueis", "address", "state_abbr", "city", "zip",
    "inst_system_name", "sector", "newid", "chief_admin_name", "phone_number",
]
ENROLLMENT_COLUMNS = [
    "unitid", "year", "fips", "ftpt", "level_of_study", "degree_seeking", "class_level", "sex", "race",
    "enrollment_fall",
]


def directory_row(
    unitid: str,
    name: str,
    state: str,
    *,
    year: int = 2024,
    ueis: tuple[str, ...] = (),
    sector: int = 1,
    alias: str = "-2",
    newid: str = "-2",
    city: str = "ANYTOWN",
    zip: str = "00000",
    system: str = "-2",
) -> dict[str, str]:
    return {
        "unitid": unitid,
        "year": str(year),
        "opeid": "00000000",
        "inst_name": name,
        "inst_alias": alias,
        "ueis": "|".join(ueis) if ueis else "-2",
        "address": "1 MAIN ST",
        "state_abbr": state,
        "city": city,
        "zip": zip,
        "inst_system_name": system,
        "sector": str(sector),
        "newid": newid,
        "chief_admin_name": "DR PERSON",
        "phone_number": "5555555555",
    }


def enrollment_row(unitid: str, year: int, enrollment: int, **breakdown: int) -> dict[str, str]:
    """A fall-enrollment row; breakdown columns default to 99 (total)."""
    row = {c: "99" for c in ENROLLMENT_COLUMNS}
    row.update(unitid=unitid, year=str(year), fips="1", enrollment_fall=str(enrollment))
    row.update({k: str(v) for k, v in breakdown.items()})
    return row


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, restval="")
        writer.writeheader()
        writer.writerows(rows)
    return path


def directory(*rows: dict[str, str]) -> pl.DataFrame:
    """A cleaned IPEDS directory frame built from raw-shaped fixture rows."""
    from topo.sources.ipeds import clean_directory

    raw = pl.DataFrame([{c: r.get(c, "") for c in DIRECTORY_COLUMNS} for r in rows], schema={c: pl.String for c in DIRECTORY_COLUMNS})
    return clean_directory(raw, from_year=2015, raw_file="fixture.csv", pull_date=dt.date(2026, 10, 7))
