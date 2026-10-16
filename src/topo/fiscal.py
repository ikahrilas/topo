"""Federal fiscal years and the reporting window.

A federal fiscal year FY<N> runs from 1 October of N-1 to 30 September of N.
Amounts are always labelled by federal FY ("FY2025"), never by academic year.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


def fiscal_year(day: dt.date) -> int:
    """The federal fiscal year a date falls in."""
    return day.year + 1 if day.month >= 10 else day.year


def fy_label(fy: int) -> str:
    """Column label for a federal fiscal year, e.g. 2025 -> "FY2025"."""
    return f"FY{fy}"


def fy_start(fy: int) -> dt.date:
    return dt.date(fy - 1, 10, 1)


def fy_end(fy: int) -> dt.date:
    return dt.date(fy, 9, 30)


def last_ended_fy(as_of: dt.date) -> int:
    """The last fiscal year that has fully ended on the As-of date."""
    return fiscal_year(as_of) - 1


@dataclass(frozen=True)
class ReportingWindow:
    """Fiscal years that get amount columns and target-list rows.

    Starts at the configured first FY and ends at the last FY ended on the
    As-of date, so it rolls forward with no code change.
    """

    start_fy: int
    end_fy: int

    @classmethod
    def ending_before(cls, start_fy: int, as_of: dt.date) -> "ReportingWindow":
        return cls(start_fy=start_fy, end_fy=last_ended_fy(as_of))

    @property
    def start(self) -> dt.date:
        return fy_start(self.start_fy)

    @property
    def end(self) -> dt.date:
        return fy_end(self.end_fy)

    @property
    def fiscal_years(self) -> list[int]:
        return list(range(self.start_fy, self.end_fy + 1))

    def overlaps(self, start: dt.date, end: dt.date) -> bool:
        """True when the period [start, end] overlaps the window."""
        return start <= self.end and end >= self.start
