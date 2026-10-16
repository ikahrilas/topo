"""Hand-built curated files for Host linking: the frozen answer key, the tuning set and overrides.

Host values are written as the target list shows them: "UNITID 180595",
"LEAID 0100005", or "no single Host".
"""

from __future__ import annotations

import csv
from pathlib import Path

KEY_COLUMNS = ["fain", "host", "reviewer", "labelled_on", "note", "second_host", "second_reviewer"]
OVERRIDE_COLUMNS = ["fain", "host", "reviewer", "date", "note"]


def _write(path: Path, columns: list[str], rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, restval="")
        writer.writeheader()
        writer.writerows(rows)
    return path


def key_row(fain: str, host: str, reviewer: str = "owner", labelled_on: str = "2026-09-01", note: str = "",
            second_host: str = "", second_reviewer: str = ""):
    """One answer-key row; `second_host`/`second_reviewer` fill a double-labelled row (inter-rater check)."""
    return {"fain": fain, "host": host, "reviewer": reviewer, "labelled_on": labelled_on, "note": note,
            "second_host": second_host, "second_reviewer": second_reviewer}


def override_row(fain: str, host: str, reviewer: str = "owner", date: str = "2026-10-01", note: str = "checked"):
    return {"fain": fain, "host": host, "reviewer": reviewer, "date": date, "note": note}


def write_answer_key(root: Path, rows) -> Path:
    return _write(root / "data" / "curated" / "host_answer_key.csv", KEY_COLUMNS, list(rows))


def write_tuning_set(root: Path, rows) -> Path:
    return _write(root / "data" / "curated" / "host_tuning_set.csv", KEY_COLUMNS, list(rows))


def write_overrides(root: Path, rows) -> Path:
    return _write(root / "data" / "curated" / "host_overrides.csv", OVERRIDE_COLUMNS, list(rows))
