"""DuckDB with the spatial extension: reading EDGE shapefiles and point-in-polygon.

The extension is loaded from DuckDB's local extension directory; it is
installed (one network fetch) only the first time a machine needs it.
Frames cross into DuckDB as Python rows or Parquet files (no pyarrow).
"""

from __future__ import annotations

import duckdb


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    try:
        con.execute("LOAD spatial")
    except duckdb.Error:
        con.execute("INSTALL spatial")
        con.execute("LOAD spatial")
    return con


def sql_string(text: str) -> str:
    """A SQL string literal."""
    return "'" + text.replace("'", "''") + "'"
