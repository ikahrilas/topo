"""The `topo` command line: pull <source>, clean <source>, join, report, run."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Annotated, Optional

import typer

from topo import pipeline
from topo.config import Config, load_config
from topo.guards import StructuralBreak
from topo.sources import SOURCES

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)

AsOf = Annotated[
    Optional[str],
    typer.Option("--as-of", help="Date the run reads the data as of (YYYY-MM-DD). Default: latest USAspending Pull date."),
]


class State:
    config_path: Path = Path("config.toml")


def _config() -> Config:
    return load_config(State.config_path)


def _date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def _guarded(fn):
    try:
        return fn()
    except StructuralBreak as err:
        typer.echo(f"Structural break: {err}", err=True)
        raise typer.Exit(code=2) from err


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
        for pulled in module.pull(_config(), when):
            typer.echo(f"pulled {pulled.path} ({pulled.bytes} bytes, sha256 {pulled.sha256})")

    _guarded(go)


@app.command()
def clean(source: str) -> None:
    """Clean the latest pull of one source into data/cleaned/."""
    frame = _guarded(lambda: pipeline.clean(_config(), source))
    typer.echo(f"cleaned {source}: {frame.height} rows")


@app.command()
def join(as_of: AsOf = None) -> None:
    """Build the joined layer (Grant universe) under an As-of date."""
    context, universe = _guarded(lambda: pipeline.join(_config(), _date(as_of)))
    typer.echo(f"joined: {universe.grants.height} Grants as of {context.as_of}")


@app.command()
def report() -> None:
    """Write the outputs from the joined layer."""
    delivered = _guarded(lambda: pipeline.report(_config()))
    typer.echo(f"wrote {delivered.target_list_csv}")


@app.command()
def run(as_of: AsOf = None) -> None:
    """Clean every source, join and report in one go."""
    delivered = _guarded(lambda: pipeline.run(_config(), _date(as_of)))
    typer.echo(f"wrote {delivered.target_list_csv}")
