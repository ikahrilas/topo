"""The committed curated area (data/curated/): hand-maintained and frozen inputs.

Host-linking files (ADR 0002), all CSV, each checked against its schema on read:

    host_answer_key.csv   the FROZEN answer key: fain, host, reviewer, labelled_on, note,
                          second_host, second_reviewer. Scored for Case-label gating only,
                          on `host` (the primary label); never tuned against. About 40 rows
                          are labelled twice: `second_host` feeds only inter-rater agreement.
                          A file without the two second-label columns still reads.
                          `[host_linking] answer_key_sha256` pins its bytes once labelled.
    host_tuning_set.csv   the separate, growing tuning set (same columns). Never scored for
                          gating; a FAIN in both files stops the run.
    host_overrides.csv    reviewed decisions: fain, host, reviewer, date, note. Versioned in
                          git; a FAIN may have several dated rows and the latest applies.

`host` is written as the target list shows it: "UNITID 180595", "LEAID 0100005" or
"no single Host". A missing file reads as empty, so the pipeline runs before any
labelling is done (every Case label then reports "unverified").
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandera.polars as pa
import polars as pl

from topo.config import Config
from topo.domain.host_gating import HostAnswerKey, HostOverrides
from topo.guards import StructuralBreak, check_schema

# Columns a curated file may lack (older headers): read as blank.
OPTIONAL_COLUMNS = ("second_host", "second_reviewer")
ANSWER_KEY = "host_answer_key.csv"
TUNING_SET = "host_tuning_set.csv"
OVERRIDES = "host_overrides.csv"


def curated_path(config: Config, name: str) -> Path:
    return config.layout.curated / name


def _read(path: Path, model: type[pa.DataFrameModel], label: str) -> pl.DataFrame:
    columns = list(model.to_schema().columns)
    if not path.exists():
        return pl.DataFrame(schema={c: pl.String for c in columns})
    frame = pl.read_csv(path, infer_schema=False)
    frame = frame.with_columns(
        pl.lit(None, dtype=pl.String).alias(c) for c in columns if c in OPTIONAL_COLUMNS and c not in frame.columns
    )
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise StructuralBreak(f"{label} ({path.name}) lacks columns: {', '.join(missing)}")
    frame = frame.select(columns).with_columns(
        pl.when(pl.col(c).str.strip_chars() == "").then(None).otherwise(pl.col(c).str.strip_chars()).alias(c)
        for c in columns
    )
    return check_schema(model, frame, label)


def read_answer_key(config: Config) -> pl.DataFrame:
    path = curated_path(config, ANSWER_KEY)
    pinned = str(config.section("host_linking").get("answer_key_sha256", "")).strip()
    if pinned and path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != pinned:
            raise StructuralBreak(
                f"the frozen answer key {path.name} changed: its sha256 no longer matches "
                "[host_linking] answer_key_sha256"
            )
    return _read(path, HostAnswerKey, "Host answer key")


def read_tuning_set(config: Config) -> pl.DataFrame:
    return _read(curated_path(config, TUNING_SET), HostAnswerKey, "Host tuning set")


def read_overrides(config: Config) -> pl.DataFrame:
    return _read(curated_path(config, OVERRIDES), HostOverrides, "Host overrides")
