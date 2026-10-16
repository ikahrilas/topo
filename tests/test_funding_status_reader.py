"""Seam 2a: the Funding status reader, tested directly as a table of cases.

Every case is one Grant's funding actions, read under an explicit As-of date
with the read windows from the repo's config.toml. Budget periods run
Sept–Aug (anniversary 1 September) unless a case says otherwise.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from topo.config import load_config
from topo.domain.funding_status import (
    FundingAction,
    OtherA1,
    ReadWindows,
    read_funding_status,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ReadWindows.from_config(load_config(REPO_ROOT / "config.toml"))


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def act(action_date: str, amount: float, bp_start: str | None, action_type: str = "B1", *,
        bp_end: str | None = None, description: str | None = None) -> FundingAction:
    """One funding action; the Budget period defaults to 12 months from bp_start."""
    if bp_start is not None and bp_end is None:
        start = d(bp_start)
        bp_end = str(start.replace(year=start.year + 1) - dt.timedelta(days=1))
    return FundingAction(
        action_date=d(action_date), obligation=amount, action_type=action_type,
        budget_period_start=d(bp_start) if bp_start else None,
        budget_period_end=d(bp_end) if bp_end else None, description=description,
    )


def statuses(reading) -> dict[str, str]:
    return {str(p.start): p.status for p in reading.periods}


def read(actions, as_of: str, **kw):
    return read_funding_status(actions, WINDOWS, d(as_of), **kw)


# A Talent Search Grant awarded in 2021: A1 in May funds the first Budget period.
TS_2021 = [
    act("2021-05-20", 300000, "2021-09-01", "A1"),
    act("2022-06-10", 300000, "2022-09-01"),
    act("2023-06-10", 300000, "2023-09-01"),
]


def test_continued_including_the_first_budget_period_continued_by_its_a1():
    reading = read(TS_2021, "2024-01-15")
    assert statuses(reading) == {
        "2021-09-01": "continued",
        "2022-09-01": "continued",
        "2023-09-01": "continued",
    }
    assert reading.latest_readable_status == "continued"
