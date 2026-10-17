"""What every pulled source shares: the raw tree data/raw/<source>/<Pull date>/, fetching, and the clean preamble.

    pull_dates(layout, source)        Pull dates present in the raw tree, oldest first
    latest_pull_date(layout, source)  the latest, or None when the source was never pulled
    pull_folder(layout, source, d)    data/raw/<source>/<Pull date>/
    pulled_paths(...)                 the configured files of one pull; a missing one stops the run
    file_name(url)                    the file name a URL is stored under
    fetch(...)                        download URLs serially into a pull folder -> PulledFile rows
    retrying(call, pause)             retry a request on a transient error (HTTP 5xx/429, dropped connection)
    refuse_urban_api(url)             Urban's robots.txt disallows /api/: only /csv/ bulk files

A source's `clean` starts the same way: take the given Pull date, else the latest;
with no pull at all it is a no-op; then it reads the configured files of that pull.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import http.client
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from topo.config import Layout
from topo.guards import StructuralBreak

Download = Callable[[str, Path], None]
Pause = Callable[[float], None]

RETRY_PAUSES = (30.0, 120.0, 300.0)  # seconds before the 2nd, 3rd and 4th attempt


def _transient(error: Exception) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code >= 500 or error.code == 429
    return isinstance(error, (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError))


def retrying[**P, R](call: Callable[P, R], pause: Pause = time.sleep) -> Callable[P, R]:
    """`call`, retried after a pause on a transient error (HTTP 5xx or 429, a dropped connection).

    A client error (other 4xx) or the last attempt's error is raised. Real pulls hit
    one-off HTTP 500s from USAspending's list_monthly_files.
    """

    def attempt(*args: P.args, **kwargs: P.kwargs) -> R:
        for wait in RETRY_PAUSES:
            try:
                return call(*args, **kwargs)
            except Exception as error:  # noqa: BLE001 - narrowed by _transient
                if not _transient(error):
                    raise
                pause(wait)
        return call(*args, **kwargs)

    return attempt


@dataclass(frozen=True)
class PulledFile:
    """One fetched raw file, with what a manifest row needs."""

    source: str
    request: str
    url: str
    path: Path
    pull_date: dt.date
    bytes: int
    sha256: str
    licence_citation: str


def pull_dates(layout: Layout, source: str) -> list[dt.date]:
    """Pull dates present in the raw tree (folders named YYYY-MM-DD), oldest first."""
    root = layout.raw_source(source)
    if not root.is_dir():
        return []
    found = []
    for child in root.iterdir():
        if child.is_dir():
            try:
                found.append(dt.date.fromisoformat(child.name))
            except ValueError:
                continue
    return sorted(found)


def latest_pull_date(layout: Layout, source: str) -> dt.date | None:
    dates = pull_dates(layout, source)
    return dates[-1] if dates else None


def pull_folder(layout: Layout, source: str, pull_date: dt.date) -> Path:
    return layout.raw_source(source) / pull_date.isoformat()


def file_name(url: str) -> str:
    return Path(urlparse(url).path).name


def pulled_paths(layout: Layout, source: str, pull_date: dt.date, names: Iterable[str], label: str) -> list[Path]:
    """The named files of one pull, in order. A pull that lacks one stops the run."""
    folder = pull_folder(layout, source, pull_date)
    paths = [folder / name for name in names]
    for path in paths:
        if not path.exists():
            raise StructuralBreak(f"{label} pull lacks {path.name} ({folder})")
    return paths


def download(url: str, dest: Path, *, timeout: int = 600, urlopen=urllib.request.urlopen) -> None:
    """GET a URL into a file, streamed through `<dest>.part`, so a broken transfer leaves no `dest`."""
    part = dest.with_name(dest.name + ".part")
    try:
        with urlopen(url, timeout=timeout) as response, part.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)


def slow_download(url: str, dest: Path) -> None:
    """`download` with a 30-minute timeout, for the large FAC and EDGE files."""
    download(url, dest, timeout=1800)


def refuse_urban_api(url: str) -> None:
    if "/api/" in urlparse(url).path:
        raise StructuralBreak(f"Urban's /api/ is disallowed by robots.txt; use a /csv/ bulk file: {url}")


def described(source: str, request: str, url: str, path: Path, pull_date: dt.date, licence_citation: str) -> PulledFile:
    """A PulledFile for a file already on disk (size and sha256 read in chunks)."""
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return PulledFile(
        source=source, request=request, url=url, path=path, pull_date=pull_date, bytes=size,
        sha256=digest.hexdigest(), licence_citation=licence_citation,
    )


def fetch(
    layout: Layout, source: str, pull_date: dt.date, urls: Iterable[str], download: Download, licence_citation: str
) -> list[PulledFile]:
    """GET each URL (serially, polite to the host) into data/raw/<source>/<Pull date>/<file name>.

    Transient errors are retried (`retrying`)."""
    folder = pull_folder(layout, source, pull_date)
    folder.mkdir(parents=True, exist_ok=True)
    pulled = []
    for url in urls:
        dest = folder / file_name(url)
        retrying(download)(url, dest)
        pulled.append(described(source, f"GET {url}", url, dest, pull_date, licence_citation))
    return pulled
