"""Source modules. Each source is one module exposing:

    SOURCE: str                                   name used on the command line
    pull(config, pull_date, **http) -> list[PulledFile]   (omit for hand-filed sources)
    clean(config, pull_date=None) -> pl.DataFrame        writes data/cleaned/<table>.parquet

Register new sources in SOURCES below; `topo pull|clean <source>` and `topo run` use it.
"""

from __future__ import annotations

from types import ModuleType

from topo.sources import ccd, census_geocoder, ed_grantee_lists, edge, fac, ipeds, saipe, usaspending

SOURCES: dict[str, ModuleType] = {
    usaspending.SOURCE: usaspending,
    ipeds.SOURCE: ipeds,
    ed_grantee_lists.SOURCE: ed_grantee_lists,
    ccd.SOURCE: ccd,
    fac.SOURCE: fac,
    edge.SOURCE: edge,
    saipe.SOURCE: saipe,
    census_geocoder.SOURCE: census_geocoder,  # after edge and ipeds: a fallback for Hosts with no EDGE point
}
