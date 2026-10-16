"""The `topo` command line: pull <source>, clean <source>, join, report, run."""

from __future__ import annotations

import datetime as dt
import warnings
from pathlib import Path
from typing import Annotated, Optional

import typer

from topo import manifest, pipeline, provenance
from topo.config import Config, load_config
from topo.guards import RunWarning, StructuralBreak
from topo.sources import SOURCES

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)

AsOf = Annotated[
    Optional[str],
    typer.Option("--as-of", help="Date the run reads the data as of (YYYY-MM-DD). Default: latest USAspending Pull date."),
]

AllowDirty = Annotated[
    bool,
    typer.Option("--allow-dirty", help="Run even though the work tree has uncommitted or untracked files."),
]


class State:
    config_path: Path = Path("config.toml")


def _config() -> Config:
    return load_config(State.config_path)


def _date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def _guarded(fn, allow_dirty: bool | None = None):
    """Run fn; print warnings; a structural break exits 2.

    With allow_dirty set (True/False) fn runs as one provenance run under the
    dirty-tree guard; `pull` passes None (it writes raw files and the manifest only).
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RunWarning)
        try:
            if allow_dirty is None:
                return fn()
            with provenance.run_scope(_config(), allow_dirty):
                return fn()
        except StructuralBreak as err:
            typer.echo(f"Structural break: {err}", err=True)
            raise typer.Exit(code=2) from err
        finally:
            for w in caught:
                if issubclass(w.category, RunWarning):
                    typer.echo(f"Warning: {w.message}", err=True)


@app.callback()
def main(
    config: Annotated[Path, typer.Option("--config", help="Path to config.toml.")] = Path("config.toml"),
) -> None:
    State.config_path = config


@app.command()
def pull(
    source: str,
    pull_date: Annotated[
        Optional[str], typer.Option("--pull-date", help="Pull date to record (default: today, the fetch date).")
    ] = None,
) -> None:
    """Fetch one source into data/raw/<source>/<Pull date>/."""

    def go():
        module = SOURCES.get(source)
        if module is None or not hasattr(module, "pull"):
            raise StructuralBreak(f"source {source!r} cannot be pulled")
        # The Pull date is the fetch date, so this is the one place the clock is read.
        when = _date(pull_date) or dt.date.today()
        config = _config()
        pulled_files = module.pull(config, when)
        for pulled in pulled_files:
            typer.echo(f"pulled {pulled.path} ({pulled.bytes} bytes, sha256 {pulled.sha256})")
        written = manifest.append(config, pulled_files)
        typer.echo(f"appended {written} rows to {manifest.manifest_path(config)}")

    _guarded(go)


@app.command()
def clean(source: str, allow_dirty: AllowDirty = False) -> None:
    """Clean the latest pull of one source into data/cleaned/."""
    frame = _guarded(lambda: pipeline.clean(_config(), source), allow_dirty)
    typer.echo(f"cleaned {source}: {frame.height} rows")


@app.command()
def join(as_of: AsOf = None, allow_dirty: AllowDirty = False) -> None:
    """Build the joined layer (Grant universe) under an As-of date."""
    context, universe = _guarded(lambda: pipeline.join(_config(), _date(as_of)), allow_dirty)
    typer.echo(f"joined: {universe.grants.height} Grants as of {context.as_of}")


@app.command()
def report(allow_dirty: AllowDirty = False) -> None:
    """Write the outputs from the joined layer."""
    delivered = _guarded(lambda: pipeline.report(_config()), allow_dirty)
    typer.echo(f"wrote {delivered.target_list_xlsx}")
    typer.echo(f"wrote {delivered.target_list_csv}")


@app.command()
def run(as_of: AsOf = None, allow_dirty: AllowDirty = False) -> None:
    """Clean every source, join and report in one go."""
    delivered = _guarded(lambda: pipeline.run(_config(), _date(as_of)), allow_dirty)
    typer.echo(f"wrote {delivered.target_list_xlsx}")
    typer.echo(f"wrote {delivered.target_list_csv}")
