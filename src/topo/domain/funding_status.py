"""Funding status reader: what happened to a Grant's funding, per Budget period.

A pure function (ADR 0001, ADR 0003): one Grant's funding actions, the read
windows from config, an explicit As-of date and the same-day A1 actions on
other FAINs go in; Funding status per Budget period, the readable-from date,
the latest readable status, the 2025–26 disruption marker and the Lifecycle
stage come out. It never reads the clock, and actions dated after the As-of
date are not seen.

Rules (docs/research/status-signals-2025-26.md §4):
    continued          first positive obligation for the period dated no later
                       than the anniversary + `continued_after_months`
                       (a first Budget period's A1 counts)
    funded late        first positive obligation after that
    unfunded           none by anniversary + `unfunded_after_days`
    not yet readable   none yet, and that date is still ahead
    reversed           an unpaired negative equal to a full positive obligation
                       of the period; same-day ± pairs and Succession hand-offs
                       (a same-day A1 of the same amount on another FAIN) are
                       not reversals
End dates, transaction descriptions and partial negatives are never status signals.

Budget periods: an action's Budget period is keyed by its start date. The
Grant's Budget periods chain from its first one: each next period starts the
day after the previous one ends. Missing periods are filled with 12-month
periods until the Grant has `expected_budget_periods` of them.
"""

from __future__ import annotations

import calendar
import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

CONTINUED = "continued"
FUNDED_LATE = "funded late"
UNFUNDED = "unfunded"
REVERSED = "reversed"
NOT_YET_READABLE = "not yet readable"

NEW = "new"
CONTINUING = "continuing"
FINAL_BUDGET_PERIOD = "final budget period"
ENDED = "ended"

DISRUPTION_NO = "no"
DISRUPTION_YES = "yes"
DISRUPTION_RESTORED = "yes, since restored"

DISRUPTED = frozenset({UNFUNDED, FUNDED_LATE, REVERSED})
FUNDED = frozenset({CONTINUED, FUNDED_LATE})


@dataclass(frozen=True)
class ReadWindows:
    """The read windows and the 2025–26 window bounds (config `[funding_status]`)."""

    continued_before_months: int
    continued_after_months: int
    unfunded_after_days: int
    disruption_start: dt.date
    disruption_end: dt.date
    budget_periods: Mapping[str, int]  # expected Budget periods by Program family

    @classmethod
    def from_section(cls, section: Mapping[str, Any]) -> "ReadWindows":
        return cls(
            continued_before_months=int(section["continued_before_months"]),
            continued_after_months=int(section["continued_after_months"]),
            unfunded_after_days=int(section["unfunded_after_days"]),
            disruption_start=_as_date(section["disruption_window_start"]),
            disruption_end=_as_date(section["disruption_window_end"]),
            budget_periods={str(k): int(v) for k, v in dict(section.get("budget_periods", {})).items()},
        )

    @classmethod
    def from_config(cls, config) -> "ReadWindows":
        return cls.from_section(config.section("funding_status"))

    def expected_budget_periods(self, program_family: str) -> int:
        return self.budget_periods.get(program_family, 1)


@dataclass(frozen=True)
class FundingAction:
    """One funding action of the Grant. `description` is carried but never read."""

    action_date: dt.date
    obligation: float
    action_type: str | None = None
    budget_period_start: dt.date | None = None
    budget_period_end: dt.date | None = None
    description: str | None = None


@dataclass(frozen=True)
class OtherA1:
    """An A1 (new award) on another FAIN, for the Succession exclusion."""

    fain: str
    action_date: dt.date
    obligation: float


@dataclass(frozen=True)
class BudgetPeriodStatus:
    start: dt.date
    end: dt.date
    status: str
    readable_from: dt.date | None  # set only when not yet readable
    disrupted: bool  # a 2025–26 disruption of this period


@dataclass(frozen=True)
class FundingReading:
    periods: tuple[BudgetPeriodStatus, ...]  # periods whose read window has opened
    funding_status: str | None  # of the latest such period
    readable_from: dt.date | None
    latest_readable_status: str | None
    disruption: str
    lifecycle_stage: str | None


def read_funding_status(
    actions: Iterable[FundingAction],
    windows: ReadWindows,
    as_of: dt.date,
    other_fain_a1s: Iterable[OtherA1] = (),
    expected_budget_periods: int = 1,
) -> FundingReading:
    """Read one Grant's Funding status under an As-of date."""
    seen = [a for a in actions if a.action_date <= as_of]
    chain = _budget_periods(seen, expected_budget_periods)
    if not chain:
        return FundingReading((), None, None, None, DISRUPTION_NO, None)

    attributed: dict[dt.date, list[FundingAction]] = {start: [] for start, _ in chain}
    starts = set(attributed)
    for a in seen:
        start = a.budget_period_start if a.budget_period_start in starts else _period_by_window(a, chain, windows)
        if start is not None:
            attributed[start].append(a)

    signals = _status_signals(seen, list(other_fain_a1s))
    periods = []
    for start, end in chain:
        own = attributed[start]
        if not own and add_months(start, -windows.continued_before_months) > as_of:
            continue  # its read window hasn't opened
        status, readable_from = _period_status(start, own, signals, windows, as_of)
        disrupted = status in DISRUPTED and windows.disruption_start <= start <= windows.disruption_end
        periods.append(BudgetPeriodStatus(start, end, status, readable_from, disrupted))

    readable = [p for p in periods if p.status != NOT_YET_READABLE]
    latest_readable = readable[-1].status if readable else None
    if not any(p.disrupted for p in periods):
        disruption = DISRUPTION_NO
    elif latest_readable in FUNDED:
        disruption = DISRUPTION_RESTORED  # money flowed again after the disruption; sticks from here on
    else:
        disruption = DISRUPTION_YES
    current = periods[-1] if periods else None
    return FundingReading(
        periods=tuple(periods),
        funding_status=current.status if current else None,
        readable_from=current.readable_from if current else None,
        latest_readable_status=latest_readable,
        disruption=disruption,
        lifecycle_stage=_lifecycle_stage(chain, as_of),
    )


def add_months(day: dt.date, months: int) -> dt.date:
    """Calendar month arithmetic, clamping to the month's last day."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _as_date(value: Any) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))


def _cents(amount: float) -> int:
    return round(amount * 100)


def _budget_periods(actions: list[FundingAction], expected: int) -> list[tuple[dt.date, dt.date]]:
    """The Grant's chain of Budget periods (start, end), funded or expected."""
    ends: dict[dt.date, dt.date] = {}
    for a in actions:
        if a.budget_period_start is None:
            continue
        end = a.budget_period_end or _twelve_months(a.budget_period_start)
        ends[a.budget_period_start] = max(end, ends.get(a.budget_period_start, end))
    known = sorted(ends)
    if not known:
        return []
    chain = [(known[0], ends[known[0]])]
    pending = known[1:]
    while pending or len(chain) < expected:
        next_start = chain[-1][1] + dt.timedelta(days=1)
        pending = [s for s in pending if s >= next_start]
        if pending and pending[0] < next_start.replace(year=next_start.year + 1):
            start = pending.pop(0)
            chain.append((start, ends[start]))
        else:
            chain.append((next_start, _twelve_months(next_start)))
    return chain


def _twelve_months(start: dt.date) -> dt.date:
    return add_months(start, 12) - dt.timedelta(days=1)


def _period_by_window(
    action: FundingAction, chain: list[tuple[dt.date, dt.date]], windows: ReadWindows
) -> dt.date | None:
    for start, _ in chain:
        opens = add_months(start, -windows.continued_before_months)
        closes = add_months(start, windows.continued_after_months)
        if opens <= action.action_date <= closes:
            return start
    return None


@dataclass(frozen=True)
class _Signals:
    """Which actions carry a status signal, after removing pairs and hand-offs."""

    ignored: frozenset[int]  # ids of actions in same-day ± pairs or Succession hand-offs


def _status_signals(actions: list[FundingAction], others: list[OtherA1]) -> _Signals:
    ignored: set[int] = set()
    # Same-day ± pairs on this Grant cancel out: neither side is a signal.
    for neg in actions:
        if neg.obligation >= 0:
            continue
        for pos in actions:
            if (
                id(pos) not in ignored
                and pos.obligation > 0
                and pos.action_date == neg.action_date
                and _cents(pos.obligation) == -_cents(neg.obligation)
            ):
                ignored.update({id(neg), id(pos)})
                break
    # A negative matched by a same-day A1 of the same amount on another FAIN is a Succession hand-off.
    handoffs = {(o.action_date, _cents(o.obligation)) for o in others}
    for neg in actions:
        if neg.obligation < 0 and id(neg) not in ignored and (neg.action_date, -_cents(neg.obligation)) in handoffs:
            ignored.add(id(neg))
    return _Signals(frozenset(ignored))


def _period_status(
    start: dt.date,
    own: list[FundingAction],
    signals: _Signals,
    windows: ReadWindows,
    as_of: dt.date,
) -> tuple[str, dt.date | None]:
    live = [a for a in own if id(a) not in signals.ignored]
    positives = sorted((a for a in live if a.obligation > 0), key=lambda a: a.action_date)
    for neg in (a for a in live if a.obligation < 0):
        prior = {_cents(p.obligation) for p in positives if p.action_date <= neg.action_date}
        if -_cents(neg.obligation) in prior:
            return REVERSED, None
        # Any other negative is partial and is not a status signal.
    if positives:
        on_time = positives[0].action_date <= add_months(start, windows.continued_after_months)
        return (CONTINUED if on_time else FUNDED_LATE), None
    readable_from = start + dt.timedelta(days=windows.unfunded_after_days)
    if as_of >= readable_from:
        return UNFUNDED, None
    return NOT_YET_READABLE, readable_from


def _lifecycle_stage(chain: list[tuple[dt.date, dt.date]], as_of: dt.date) -> str:
    if as_of > chain[-1][1]:
        return ENDED
    if as_of <= chain[0][1]:
        return NEW
    if as_of >= chain[-1][0]:
        return FINAL_BUDGET_PERIOD
    return CONTINUING
