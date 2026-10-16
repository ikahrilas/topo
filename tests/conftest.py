from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from topo.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Project:
    """A throwaway project root: the repo's config.toml plus a fixture data tree."""

    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config.toml"

    @property
    def raw_usaspending(self) -> Path:
        return self.root / "data" / "raw" / "usaspending"

    @property
    def output(self) -> Path:
        return self.root / "output"

    def set_config(self, old: str, new: str) -> None:
        text = self.config.read_text()
        assert old in text, old
        self.config.write_text(text.replace(old, new))

    def topo(self, *args: str, expect_exit: int = 0):
        result = CliRunner().invoke(app, ["--config", str(self.config), *args])
        assert result.exit_code == expect_exit, (result.output, result.exception)
        return result

    def read_csv(self, name: str) -> list[dict[str, str]]:
        with (self.output / name).open(newline="") as f:
            return list(csv.DictReader(f))


@pytest.fixture
def project(tmp_path: Path) -> Project:
    shutil.copy(REPO_ROOT / "config.toml", tmp_path / "config.toml")
    return Project(tmp_path)
