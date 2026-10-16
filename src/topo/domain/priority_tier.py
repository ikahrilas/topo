"""The displayed label and Priority tier of one target-list row (spec #28, #26).

One label sits over the underlying fields, first match wins:
Unfunded or Reversed -> Re-competing soon -> New -> Final budget period -> Ended -> Continuing.
A row whose latest Budget period is not yet readable gets a suffix with its
readable-from date. The Priority tier is a call-order bucket, never a score:

    1  new, within `new_award_months` of the award
    2  re-competing soon (wired by renewal timing, #40)
    3  continuing (also new rows past the tier-1 window and final Budget periods)
    4  unfunded or reversed, shown with the reason

Ended rows (other than unfunded or reversed) get no tier: they sit on the
Ended sheet and are not a call list.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from topo.domain.funding_status import (
    CONTINUING,
    ENDED,
    FINAL_BUDGET_PERIOD,
    NEW,
    NOT_YET_READABLE,
    REVERSED,
    UNFUNDED,
    add_months,
)

LABEL_UNFUNDED = "Unfunded"
LABEL_REVERSED = "Reversed"
LABEL_RE_COMPETING_SOON = "Re-competing soon"
LABEL_NEW = "New"
LABEL_FINAL_BUDGET_PERIOD = "Final budget period"
LABEL_ENDED = "Ended"
LABEL_CONTINUING = "Continuing"

TIER_NEW = 1
TIER_RE_COMPETING_SOON = 2
TIER_CONTINUING = 3
TIER_UNFUNDED_OR_REVERSED = 4

_STAGE_LABELS = {
    NEW: LABEL_NEW,
    FINAL_BUDGET_PERIOD: LABEL_FINAL_BUDGET_PERIOD,
    ENDED: LABEL_ENDED,
    CONTINUING: LABEL_CONTINUING,
}


@dataclass(frozen=True)
class RowFacts:
    """What the label and tier are read from, for one Grant."""

    funding_status: str | None  # latest listed Budget period (may be "not yet readable")
    readable_from: dt.date | None  # when that period becomes readable
    latest_readable_status: str | None
    latest_readable_period: tuple[dt.date, dt.date] | None  # (start, end) of the latest readable Budget period
    lifecycle_stage: str | None
    award_date: dt.date | None  # the Grant's first action (its A1)
    re_competing_soon: bool = False  # set by renewal timing (#40)


@dataclass(frozen=True)
class RowLabel:
    label: str
    priority_tier: int | None
    tier_reason: str | None


def label_row(facts: RowFacts, as_of: dt.date, new_award_months: int) -> RowLabel:
    label, tier, reason = _base(facts, as_of, new_award_months)
    if facts.funding_status == NOT_YET_READABLE and facts.readable_from is not None:
        label = f"{label} (not yet readable; readable from {facts.readable_from.isoformat()})"
    return RowLabel(label, tier, reason)


def _base(facts: RowFacts, as_of: dt.date, new_award_months: int) -> tuple[str, int | None, str | None]:
    status = facts.latest_readable_status
    if status in (UNFUNDED, REVERSED):
        reason = status
        if facts.latest_readable_period is not None:
            start, end = facts.latest_readable_period
            reason = f"{status}: Budget period {start.isoformat()} to {end.isoformat()}"
        return (LABEL_UNFUNDED if status == UNFUNDED else LABEL_REVERSED), TIER_UNFUNDED_OR_REVERSED, reason
    stage = facts.lifecycle_stage
    if facts.re_competing_soon:
        return LABEL_RE_COMPETING_SOON, TIER_RE_COMPETING_SOON, None
    label = _STAGE_LABELS.get(stage or "", LABEL_CONTINUING)
    if stage == ENDED:
        return label, None, None
    award = facts.award_date
    if stage == NEW and award is not None and award <= as_of <= add_months(award, new_award_months):
        return label, TIER_NEW, f"awarded {award.isoformat()}"
    return label, TIER_CONTINUING, None
