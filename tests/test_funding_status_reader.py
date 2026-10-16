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


def test_continued_when_recorded_up_to_one_month_after_the_anniversary():
    reading = read([*TS_2021, act("2024-10-01", 300000, "2024-09-01")], "2025-01-15")
    assert statuses(reading)["2024-09-01"] == "continued"


def test_funded_late_when_first_recorded_more_than_one_month_after_the_anniversary():
    # Augsburg McNair pattern: no 2025 Continuation on time, then a B1 in March 2026.
    actions = [*TS_2021, act("2024-07-12", 300000, "2024-09-01"), act("2026-03-13", 272360, "2025-09-01")]
    reading = read(actions, "2026-04-01", expected_budget_periods=5)
    assert statuses(reading)["2024-09-01"] == "continued"
    assert statuses(reading)["2025-09-01"] == "funded late"
    assert reading.latest_readable_status == "funded late"


def test_back_funded_skipped_year_reads_funded_late_then_continued():
    # P047A220168 pattern: two B1s close together catch up two Budget periods.
    actions = [
        act("2022-05-14", 400000, "2022-09-01", "A1"),
        act("2023-05-14", 400000, "2023-09-01"),
        act("2024-05-14", 400000, "2024-09-01"),
        act("2026-06-18", 400000, "2025-09-01"),
        act("2026-07-29", 400000, "2026-09-01"),
    ]
    reading = read(actions, "2026-10-07", expected_budget_periods=5)
    assert statuses(reading)["2025-09-01"] == "funded late"
    assert statuses(reading)["2026-09-01"] == "continued"


@pytest.mark.parametrize(
    ("as_of", "status", "readable_from"),
    [
        ("2024-11-29", "not yet readable", "2024-11-30"),  # anniversary + 89 days
        ("2024-11-30", "unfunded", None),                  # anniversary + 90 days
    ],
)
def test_unfunded_only_from_anniversary_plus_90_days(as_of, status, readable_from):
    reading = read(TS_2021, as_of, expected_budget_periods=5)
    period = next(p for p in reading.periods if str(p.start) == "2024-09-01")
    assert period.status == status
    assert (str(period.readable_from) if period.readable_from else None) == readable_from


def test_not_yet_readable_shows_its_readable_from_date_and_keeps_the_latest_readable_status():
    actions = [*TS_2021, act("2024-06-10", 300000, "2024-09-01")]
    reading = read(actions, "2025-10-07", expected_budget_periods=5)
    assert statuses(reading)["2025-09-01"] == "not yet readable"
    assert reading.funding_status == "not yet readable"
    assert reading.readable_from == d("2025-11-30")
    assert reading.latest_readable_status == "continued"


def test_a_period_appears_only_once_its_read_window_opens():
    actions = [*TS_2021, act("2024-06-10", 300000, "2024-09-01")]
    assert "2025-09-01" not in statuses(read(actions, "2025-04-30", expected_budget_periods=5))
    assert "2025-09-01" in statuses(read(actions, "2025-05-01", expected_budget_periods=5))


def test_actions_after_the_as_of_date_are_not_seen():
    actions = [*TS_2021, act("2024-06-10", 300000, "2024-09-01")]
    reading = read(actions, "2024-05-31", expected_budget_periods=5)
    assert statuses(reading)["2024-09-01"] == "not yet readable"


def test_an_action_with_no_budget_period_counts_by_its_date_window():
    actions = [*TS_2021, act("2024-06-10", 300000, None)]
    reading = read(actions, "2025-01-15", expected_budget_periods=4)
    assert statuses(reading)["2024-09-01"] == "continued"


# Reversed: only an unpaired full-amount negative.

def test_reversed_by_an_unpaired_full_amount_negative():
    # Ivy Tech TS pattern: B1 +336,357 then EX −336,357 twelve days later.
    actions = [*TS_2021, act("2024-06-10", 300000, "2024-09-01"),
               act("2025-09-17", 336357, "2025-09-01"), act("2025-09-29", -336357, "2025-09-01", "EX")]
    reading = read(actions, "2026-01-15", expected_budget_periods=5)
    assert statuses(reading)["2025-09-01"] == "reversed"
    assert reading.latest_readable_status == "reversed"


def test_same_day_plus_minus_pair_is_not_a_reversal():
    actions = [*TS_2021, act("2024-06-10", 300000, "2024-09-01"),
               act("2024-08-01", -300000, "2024-09-01", "FX"), act("2024-08-01", 300000, "2024-09-01", "FX")]
    reading = read(actions, "2025-01-15", expected_budget_periods=5)
    assert statuses(reading)["2024-09-01"] == "continued"


def test_partial_negatives_are_ignored():
    actions = [*TS_2021, act("2024-06-10", 300000, "2024-09-01"), act("2024-11-02", -41250.17, "2024-09-01", "FX")]
    reading = read(actions, "2025-01-15", expected_budget_periods=5)
    assert statuses(reading)["2024-09-01"] == "continued"


def test_end_dates_are_ignored():
    # A later modification cuts the Budget period end short; status is unchanged.
    actions = [*TS_2021, act("2024-06-10", 300000, "2024-09-01"),
               act("2024-10-20", 0, "2024-09-01", "C", bp_end="2024-09-30")]
    reading = read(actions, "2025-01-15", expected_budget_periods=4)
    assert statuses(reading)["2024-09-01"] == "continued"
    assert reading.latest_readable_status == "continued"


def test_transaction_descriptions_are_ignored():
    described = [act("2024-06-10", 300000, "2024-09-01", description="NON-CONTINUATION; GRANT TERMINATED")]
    plain = [act("2024-06-10", 300000, "2024-09-01")]
    assert read([*TS_2021, *described], "2025-01-15") == read([*TS_2021, *plain], "2025-01-15")


# The 4 known Succession cases (docs/research/status-signals-2025-26.md §1c): the old
# FAIN's negative matches a same-day A1 of the same amount on the new FAIN.

SUCCESSIONS = {
    "P047A221031 to P047A250002": ("2025-12-22", 513114.00, "P047A250002"),
    "P217A220158 to P217A250002": ("2026-06-15", 92117.37, "P217A250002"),
    "P042A250822 to P042A251923": ("2026-07-06", 202423.49, "P042A251923"),
    "P042A250292 to P042A251922": ("2026-06-24", 272364.00, "P042A251922"),
}


@pytest.mark.parametrize("case", list(SUCCESSIONS), ids=list(SUCCESSIONS))
def test_known_succession_hand_off_is_not_a_reversal(case):
    date, amount, new_fain = SUCCESSIONS[case]
    actions = [act("2025-07-01", amount, "2025-09-01", "A1"), act(date, -amount, "2025-09-01", "EX")]
    successor = OtherA1(fain=new_fain, action_date=d(date), obligation=amount)

    handed_off = read(actions, "2026-10-07", other_fain_a1s=[successor])
    assert statuses(handed_off)["2025-09-01"] == "continued"

    # Without the successor's same-day A1, the same negative reads as reversed.
    assert statuses(read(actions, "2026-10-07"))["2025-09-01"] == "reversed"


def test_a1_on_another_fain_on_a_different_day_does_not_excuse_a_reversal():
    actions = [act("2025-07-01", 513114, "2025-09-01", "A1"), act("2025-12-22", -513114, "2025-09-01", "EX")]
    other = OtherA1(fain="P047A250002", action_date=d("2025-12-23"), obligation=513114)
    assert statuses(read(actions, "2026-10-07", other_fain_a1s=[other]))["2025-09-01"] == "reversed"


# The 2025–26 disruption marker: Budget periods starting 2025-05-01 .. 2026-09-30.

def grant_with_period_starting(start: str, funded_on: str | None) -> list[FundingAction]:
    """A Grant whose first Budget period runs the year before `start`; `start` is funded on `funded_on`."""
    first = d(start).replace(year=d(start).year - 1)
    actions = [act(str(first - dt.timedelta(days=60)), 100000, str(first), "A1")]
    if funded_on:
        actions.append(act(funded_on, 100000, start))
    return actions


@pytest.mark.parametrize(
    ("start", "disruption"),
    [
        ("2025-04-30", "no"),
        ("2025-05-01", "yes"),
        ("2026-09-30", "yes"),
        ("2026-10-01", "no"),
    ],
)
def test_disruption_window_edges(start, disruption):
    reading = read(grant_with_period_starting(start, None), "2027-06-01", expected_budget_periods=2)
    assert statuses(reading)[start] == "unfunded"
    assert reading.disruption == disruption


def test_funded_late_in_the_window_is_a_disruption_since_restored():
    reading = read(grant_with_period_starting("2025-09-01", "2026-03-13"), "2026-04-01", expected_budget_periods=2)
    assert reading.disruption == "yes, since restored"


def test_continued_throughout_is_no_disruption():
    reading = read(grant_with_period_starting("2025-09-01", "2025-06-15"), "2026-04-01", expected_budget_periods=2)
    assert reading.disruption == "no"


def test_since_restored_sticks_after_a_later_restoration():
    # Unfunded in 2025–26, then later Budget periods are continued: restored, and it stays so.
    actions = [
        act("2024-06-01", 100000, "2024-09-01", "A1"),
        act("2026-06-15", 100000, "2026-09-01"),
        act("2027-06-15", 100000, "2027-09-01"),
    ]
    assert read(actions[:1], "2026-01-15", expected_budget_periods=4).disruption == "yes"
    for as_of in ("2026-10-15", "2027-10-15", "2028-10-15"):
        reading = read(actions, as_of, expected_budget_periods=4)
        assert statuses(reading)["2025-09-01"] == "unfunded"
        assert reading.disruption == "yes, since restored"


def test_reversed_after_restoration_is_disrupted_and_not_restored():
    # Augsburg McNair: unfunded on time, funded late 2026-03-13, reversed 2026-09-14.
    actions = [act("2024-07-12", 272360, "2024-09-01", "A1"), act("2026-03-13", 272360, "2025-09-01"),
               act("2026-09-14", -272360, "2025-09-01", "EX")]
    assert read(actions, "2026-04-01", expected_budget_periods=2).disruption == "yes, since restored"
    after = read(actions, "2026-10-07", expected_budget_periods=2)
    assert statuses(after)["2025-09-01"] == "reversed"
    assert after.disruption == "yes"


# Lifecycle stage, judged at the As-of date against the expected Budget periods.

@pytest.mark.parametrize(
    ("as_of", "stage"),
    [
        ("2021-06-01", "new"),                  # awarded, first Budget period not yet started
        ("2022-08-31", "new"),                  # last day of the first Budget period
        ("2022-09-01", "continuing"),
        ("2025-08-31", "continuing"),
        ("2025-09-01", "final budget period"),  # fifth of five Budget periods
        ("2026-08-31", "final budget period"),
        ("2026-09-01", "ended"),
    ],
)
def test_lifecycle_stage(as_of, stage):
    actions = [*TS_2021, act("2024-06-10", 300000, "2024-09-01"), act("2025-06-10", 300000, "2025-09-01")]
    assert read(actions, as_of, expected_budget_periods=5).lifecycle_stage == stage


def test_read_windows_come_from_config(tmp_path):
    assert (WINDOWS.continued_before_months, WINDOWS.continued_after_months, WINDOWS.unfunded_after_days) == (4, 1, 90)
    assert (WINDOWS.disruption_start, WINDOWS.disruption_end) == (d("2025-05-01"), d("2026-09-30"))

    text = (REPO_ROOT / "config.toml").read_text()
    for old, new in [
        ("continued_after_months = 1", "continued_after_months = 2"),
        ("unfunded_after_days = 90", "unfunded_after_days = 120"),
        ("disruption_window_start = 2025-05-01", "disruption_window_start = 2025-10-01"),
    ]:
        assert old in text
        text = text.replace(old, new)
    (tmp_path / "config.toml").write_text(text)
    edited = ReadWindows.from_config(load_config(tmp_path / "config.toml"))

    recorded_in_october = [*TS_2021, act("2024-06-10", 1, "2024-09-01"), act("2025-10-20", 1, "2025-09-01")]
    assert statuses(read(recorded_in_october, "2026-01-15"))["2025-09-01"] == "funded late"
    assert statuses(read_funding_status(recorded_in_october, edited, d("2026-01-15")))["2025-09-01"] == "continued"

    assert statuses(read(TS_2021, "2024-12-15", expected_budget_periods=5))["2024-09-01"] == "unfunded"
    assert statuses(read_funding_status(TS_2021, edited, d("2024-12-15"), expected_budget_periods=5))[
        "2024-09-01"] == "not yet readable"

    unfunded_2025 = grant_with_period_starting("2025-09-01", None)
    assert read(unfunded_2025, "2026-06-01", expected_budget_periods=2).disruption == "yes"
    assert read_funding_status(unfunded_2025, edited, d("2026-06-01"), expected_budget_periods=2).disruption == "no"
