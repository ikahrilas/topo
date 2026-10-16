"""Delivered-file naming. Every delivered file carries the Pull date, and an
existing delivered file is never overwritten: a rerun gets the next free
version suffix instead.

    output/<stem>_<Pull date>.<ext>, then <stem>_<Pull date>_v2.<ext>, _v3, ...
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path


def delivery_path(output_dir: Path, stem: str, pull_date: dt.date, ext: str) -> Path:
    """The first free path for a delivered file; never one that already exists."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base = f"{stem}_{pull_date.isoformat()}"
    candidate = output_dir / f"{base}.{ext}"
    version = 2
    while candidate.exists():
        candidate = output_dir / f"{base}_v{version}.{ext}"
        version += 1
    return candidate


def delivery_paths(output_dir: Path, stem: str, pull_date: dt.date, exts: tuple[str, ...]) -> dict[str, Path]:
    """Paths for files delivered together (e.g. XLSX + CSV): one version suffix, free for every extension."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base = f"{stem}_{pull_date.isoformat()}"
    suffix, version = "", 2
    while any((output_dir / f"{base}{suffix}.{ext}").exists() for ext in exts):
        suffix, version = f"_v{version}", version + 1
    return {ext: output_dir / f"{base}{suffix}.{ext}" for ext in exts}


def write_new(path: Path, data: bytes) -> None:
    """Write bytes to a path that must not exist yet (exclusive create)."""
    with path.open("xb") as f:
        f.write(data)
