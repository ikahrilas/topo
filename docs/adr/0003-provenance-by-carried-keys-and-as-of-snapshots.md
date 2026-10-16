# Provenance is carried keys plus a per-output sidecar, and Funding status is derived under an as-of date

Every figure must trace to source, query, and pull date. We considered per-cell lineage metadata and rejected it as heavy machinery for a pipeline this size. Instead each joined row **carries its source keys** (USAspending FAIN and transaction id, IPEDS UNITID or LEA id, ED list row id), and each output file gets a **sidecar** (`<name>.provenance.json`). The sidecar lists the raw files used by SHA-256, the code commit, the as-of date, the config hash, the run id, and whether the tree was dirty. A dirty tree fails the run unless `--allow-dirty` is passed. A figure then traces key → raw file hash → manifest row (URL or request, pull date, licence or citation).

**Funding status is derived, not curated.** It is computed at join time from USAspending funding sequences, using read windows from `config.toml`, under an explicit `--as-of` date that defaults to the latest USAspending pull date. "Not yet readable" depends on that date, so the date is an input, never the clock. Each run appends a snapshot keyed by (FAIN, Budget period, as-of) to a local history file, which makes any published reading reproducible. Only the cause-note table is hand-maintained (committed CSV, each row requires a source and a docket entry or page).

Layout and tooling:

- One committed `data/raw/manifest.csv` for all sources (extends the #5 manifest with `source`, `request`, `licence_citation`); raw files stay git-ignored. Layers are `data/raw/<source>/` → `data/cleaned/` → `data/joined/` → `output/`, plus committed `data/curated/` for hand-maintained and frozen inputs (cause notes, answer key, overrides, FY2027 predictions).
- A Python CLI package (uv, `pyproject.toml`): `topo pull|clean <source>`, `topo join`, `topo report`, `topo run`. `pull` writes its own manifest row.
- Schemas are Pandera with the polars backend, checked at the end of every `clean` and `join`. Only structural breaks stop a run (#14).
- One `config.toml` holds tolerances, read windows, the reporting window, thresholds, and the as-of default. The row-count log is an append-only Parquet file, `output/run_log.parquet`.

## Consequences

- Cleaned, joined, and output layers are rebuildable and not committed. Only frozen artifacts and published snapshots are.
- Reproducing a published one-pager needs its sidecar, the manifest, and the raw files whose hashes it names.
- Revisit per-cell lineage only if a reviewer needs to trace an aggregate to rows without the keys.

Decided in [Pipeline shape and provenance model](https://github.com/ikahrilas/topo/issues/15).
