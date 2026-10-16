"""Source modules. Each source is one module exposing:

    SOURCE: str                                   name used on the command line
    pull(config, pull_date, **http) -> list[PulledFile]   (omit for hand-filed sources)
    clean(config, pull_date=None) -> pl.DataFrame        writes data/cleaned/<table>.parquet

Register new sources in SOURCES below; `topo pull|clean <source>` and `topo run` use it.
"""

from __future__ import annotations

from types import ModuleType

from topo.sources import ccd, ipeds, usaspending

SOURCES: dict[str, ModuleType] = {
    usaspending.SOURCE: usaspending,
    ipeds.SOURCE: ipeds,
    ccd.SOURCE: ccd,
}
