"""The single config file (config.toml) and the data layout it points at.

Layout (ADR 0003):
    data/raw/<source>/<Pull date>/...   pulled files, git-ignored
    data/cleaned/<name>.parquet          one cleaned table per source table
    data/joined/<name>.parquet           domain tables (Grant universe, ...)
    data/curated/                        committed hand-maintained and frozen inputs
    output/                              delivered files, never overwritten
"""

from __future__ import annotations

import datetime as dt
import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LATEST_USASPENDING_PULL = "latest_usaspending_pull"


@dataclass(frozen=True)
class Layout:
    data: Path
    output: Path

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def cleaned(self) -> Path:
        return self.data / "cleaned"

    @property
    def joined(self) -> Path:
        return self.data / "joined"

    @property
    def curated(self) -> Path:
        return self.data / "curated"

    def raw_source(self, source: str) -> Path:
        return self.raw / source

    def cleaned_table(self, name: str) -> Path:
        return self.cleaned / f"{name}.parquet"

    def joined_table(self, name: str) -> Path:
        return self.joined / f"{name}.parquet"


@dataclass(frozen=True)
class Config:
    path: Path
    raw: dict[str, Any]  # the parsed TOML, for sections added by later tickets
    layout: Layout

    @property
    def reporting_window_start_fy(self) -> int:
        return int(self.raw["reporting_window"]["start_fy"])

    @property
    def as_of_default(self) -> str:
        """Either LATEST_USASPENDING_PULL or an ISO date string."""
        return str(self.raw["as_of"]["default"])

    @property
    def tolerances(self) -> dict[str, float]:
        return dict(self.raw["tolerances"])

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.raw.get(name, {}))

    @property
    def sha256(self) -> str:
        """Hash of the config file bytes (for provenance sidecars)."""
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def load_config(path: Path) -> Config:
    path = Path(path).resolve()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    base = path.parent
    paths = raw.get("paths", {})
    layout = Layout(data=base / paths.get("data", "data"), output=base / paths.get("output", "output"))
    return Config(path=path, raw=raw, layout=layout)


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)
