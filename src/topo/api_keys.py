"""API keys come from environment variables, never from committed files.

Only the Census API needs a key. config.toml names the variable (`[api_keys]
census = "CENSUS_API_KEY"`), never the key itself. The variable is read from the
process environment first, then from a `.env` file beside config.toml, which
is git-ignored.
"""

from __future__ import annotations

import os
from pathlib import Path

from topo.config import Config
from topo.guards import StructuralBreak

KEYED_APIS = ("census",)  # the only API that needs a key


def _dot_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.removeprefix("export ").split("=", 1)
        values[name.strip()] = value.strip().strip("'\"")
    return values


def api_key(config: Config, api: str) -> str:
    """The key for `api` from its environment variable (or the git-ignored .env)."""
    if api not in KEYED_APIS:
        raise StructuralBreak(f"no API key is configured for {api!r}; only the Census API takes a key")
    variable = config.section("api_keys").get(api)
    if not variable:
        raise StructuralBreak(f"config.toml has no [api_keys] {api} entry naming its environment variable")
    value = os.environ.get(variable) or _dot_env(config.path.parent / ".env").get(variable)
    if not value:
        raise StructuralBreak(f"{api} API key missing: set the {variable} environment variable (or put it in .env)")
    return value
