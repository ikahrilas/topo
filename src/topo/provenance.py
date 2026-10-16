"""Provenance (ADR 0003): the run, its git state, raw inputs and per-output sidecars.

A run has a random run id (never the clock), the commit of the git checkout
holding config.toml, and whether that tree was dirty. A dirty tree (tracked
changes or untracked, non-ignored files) stops the run unless `--allow-dirty`
is passed. Outside a git checkout the run only warns and records no commit.

Each `clean` records the raw files it read (path, SHA-256, bytes) in
data/cleaned/<source>.raw_inputs.json. Each output file gets a sidecar
`<output file name>.provenance.json` (e.g. target_list_2026-10-07.csv.provenance.json)
listing those raw files, the commit, the As-of date, the Pull date, the config
hash, the run id and the dirty flag.
"""

from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import hashlib
import json
import subprocess
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from topo.config import Config
from topo.guards import StructuralBreak, warn

RAW_INPUTS_SUFFIX = ".raw_inputs.json"
SIDECAR_SUFFIX = ".provenance.json"


@dataclass(frozen=True)
class Run:
    run_id: str
    commit: str | None  # None outside a git checkout
    dirty: bool | None  # None outside a git checkout


_current: contextvars.ContextVar[Run | None] = contextvars.ContextVar("topo_run", default=None)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def git_state(root: Path) -> tuple[str | None, bool | None]:
    """(commit, dirty) of the checkout holding `root`; (None, None) when it isn't one."""
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None, None
    head = _git(root, "rev-parse", "--verify", "HEAD")
    commit = head.stdout.strip() if head.returncode == 0 else None
    status = _git(root, "status", "--porcelain", "--untracked-files=normal")
    if status.returncode != 0:
        raise StructuralBreak(f"git status failed: {status.stderr.strip()}")
    return commit, bool(status.stdout.strip()) or commit is None


def begin_run(config: Config, allow_dirty: bool = False) -> Run:
    """Start a run: read the git state and apply the dirty-tree guard."""
    root = config.path.parent
    commit, dirty = git_state(root)
    if commit is None and dirty is None:
        warn(f"not a git checkout ({root}); outputs record no commit")
    elif dirty and not allow_dirty:
        raise StructuralBreak(
            f"the git tree at {root} is dirty (uncommitted or untracked files); "
            "commit them or pass --allow-dirty"
        )
    return Run(run_id=uuid.uuid4().hex, commit=commit, dirty=dirty)


@contextlib.contextmanager
def run_scope(config: Config, allow_dirty: bool = False) -> Iterator[Run]:
    """Every layer inside the block shares one run (one run id, one git state)."""
    run = begin_run(config, allow_dirty)
    token = _current.set(run)
    try:
        yield run
    finally:
        _current.reset(token)


def current_run(config: Config) -> Run:
    """The active run; outside `run_scope` (direct library calls) a new unguarded one."""
    return _current.get() or begin_run(config, allow_dirty=True)


# ---------------------------------------------------------------- raw inputs


def _relative(config: Config, path: Path) -> str:
    root = config.path.parent.resolve()
    path = Path(path).resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def record_raw_inputs(config: Config, source: str, paths: Iterable[Path]) -> str:
    """Record the raw files one `clean` read; returns their combined input hash."""
    files = [
        {"source": source, "path": _relative(config, p), "sha256": file_sha256(p), "bytes": Path(p).stat().st_size}
        for p in sorted(paths)
    ]
    cleaned = config.layout.cleaned
    cleaned.mkdir(parents=True, exist_ok=True)
    (cleaned / f"{source}{RAW_INPUTS_SUFFIX}").write_text(json.dumps(files, indent=2))
    return combined_hash(f"{f['path']} {f['sha256']}" for f in files)


def raw_inputs(config: Config) -> list[dict]:
    """Every raw file recorded by the cleans behind the current cleaned layer."""
    cleaned = config.layout.cleaned
    if not cleaned.is_dir():
        return []
    files: list[dict] = []
    for record in sorted(cleaned.glob(f"*{RAW_INPUTS_SUFFIX}")):
        files.extend(json.loads(record.read_text()))
    return files


def combined_hash(parts: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# ------------------------------------------------------------------ sidecars


def sidecar_path(output: Path) -> Path:
    return output.with_name(output.name + SIDECAR_SUFFIX)


def write_sidecar(
    config: Config, output: Path, *, as_of: dt.date, pull_date: dt.date, appended: bool = False
) -> Path:
    """Write `<output>.provenance.json` next to a delivered file (never overwriting one).

    An `appended` output (the append-only Funding status history) is one file that every
    run extends; its sidecar is replaced to describe the run that last appended to it.
    """
    run = current_run(config)
    sidecar = {
        "output": output.name,
        "run_id": run.run_id,
        "commit": run.commit,
        "dirty": run.dirty,
        "as_of": as_of.isoformat(),
        "pull_date": pull_date.isoformat(),
        "config_sha256": config.sha256,
        "raw_files": raw_inputs(config),
    }
    path = sidecar_path(output)
    text = json.dumps(sidecar, indent=2) + "\n"
    if appended:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)
        return path
    with path.open("x") as f:
        f.write(text)
    return path
