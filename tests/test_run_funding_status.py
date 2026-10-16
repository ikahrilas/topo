"""Seam 1: Funding status on the target list and the Funding status history, via `topo run`."""

from __future__ import annotations

import datetime as dt
import json

import polars as pl
from support.usaspending import action, write_actions
from support.workbook import read_sheet

PULL = "2026-10-07"
HISTORY = "funding_status_history.parquet"

USF_UB = [  # continued every year; 2026-09-01 is its fifth and final Budget period
    action("P047A220845", 1, "2022-05-23", 824294, ("2022-06-01", "2023-08-31"), action_type="A1"),
    action("P047A220845", 2, "2023-05-13", 857266, ("2023-09-01", "2024-08-31")),
    action("P047A220845", 3, "2024-05-15", 857266, ("2024-09-01", "2025-08-31")),
    action("P047A220845", 4, "2025-09-17", 857266, ("2025-09-01", "2026-08-31")),
    action("P047A220845", 5, "2026-07-28", 857266, ("2026-09-01", "2027-08-31")),
]

MCNAIR = dict(recipient="AUGSBURG UNIVERSITY", uei="MCNAIRUEI001", state="MN")
AUGSBURG_MCNAIR = [  # no 2025 Continuation on time, then funded late in March 2026
    action("P217A220172", 1, "2022-07-01", 272360, ("2022-10-01", "2023-09-30"), action_type="A1", **MCNAIR),
    action("P217A220172", 2, "2023-07-12", 272360, ("2023-10-01", "2024-09-30"), **MCNAIR),
    action("P217A220172", 3, "2024-07-12", 272360, ("2024-10-01", "2025-09-30"),
           transaction_description="NON-CONTINUATION NOTICE", **MCNAIR),
    action("P217A220172", 4, "2026-03-13", 272360, ("2025-10-01", "2026-09-30"), **MCNAIR),
]

TS = dict(recipient="IVY TECH COMMUNITY COLLEGE", uei="IVYTECHUEI01", state="IN")
IVY_TECH_TS = [  # 2025-26 Continuation reversed in full twelve days later
    action("P044A210683", 1, "2021-06-01", 336357, ("2021-09-01", "2022-08-31"), action_type="A1", **TS),
    action("P044A210683", 2, "2022-06-01", 336357, ("2022-09-01", "2023-08-31"), **TS),
    action("P044A210683", 3, "2023-06-01", 336357, ("2023-09-01", "2024-08-31"), **TS),
    action("P044A210683", 4, "2024-06-01", 336357, ("2024-09-01", "2025-08-31"), **TS),
    action("P044A210683", 5, "2025-09-17", 336357, ("2025-09-01", "2026-08-31"), **TS),
    action("P044A210683", 6, "2025-09-29", -336357, ("2025-09-01", "2026-08-31"), action_type="EX", **TS),
]

SITE = dict(recipient="SIENA HEIGHTS UNIVERSITY", uei="SIENAUEI0001", state="MI")
ADRIAN = dict(recipient="ADRIAN COLLEGE", uei="ADRIANUEI001", state="MI")
SIENA_TO_ADRIAN = [  # Succession: the old FAIN's negative matches the new FAIN's same-day A1
    action("P217A220158", 1, "2021-07-01", 92117.37, ("2021-10-01", "2022-09-30"), action_type="A1", **SITE),
    action("P217A220158", 6, "2022-07-01", 92117.37, ("2022-10-01", "2023-09-30"), **SITE),
    action("P217A220158", 2, "2023-07-01", 92117.37, ("2023-10-01", "2024-09-30"), **SITE),
    action("P217A220158", 3, "2024-07-01", 92117.37, ("2024-10-01", "2025-09-30"), **SITE),
    action("P217A220158", 4, "2025-07-01", 92117.37, ("2025-10-01", "2026-09-30"), **SITE),
    action("P217A220158", 5, "2026-06-15", -92117.37, ("2025-10-01", "2026-09-30"), action_type="EX", **SITE),
    action("P217A250002", 1, "2026-06-15", 92117.37, ("2026-07-01", "2027-06-30"), action_type="A1", **ADRIAN),
]


def target_rows(project, name=f"target_list_{PULL}.xlsx") -> dict[str, dict[str, str]]:
    """Rows of the main and Ended sheets (ended Grants live on the Ended sheet)."""
    path = project.output / name
    return {r["FAIN"]: r for r in read_sheet(path, "Target list") + read_sheet(path, "Ended")}


def test_target_list_shows_funding_status_lifecycle_stage_and_disruption(project):
    write_actions(project.raw_usaspending, PULL, USF_UB + AUGSBURG_MCNAIR + IVY_TECH_TS + SIENA_TO_ADRIAN)

    project.topo("run", "--as-of", PULL)

    rows = target_rows(project)
    shown = {
        fain: (r["Funding status"], r["Latest readable status"], r["Readable from"], r["Lifecycle stage"],
               r["2025–26 disruption"])
        for fain, r in rows.items()
    }
    assert shown == {
        "P047A220845": ("continued", "continued", "", "final budget period", "no"),
        "P217A220172": ("not yet readable", "funded late", "2026-12-30", "final budget period", "yes, since restored"),
        "P044A210683": ("reversed", "reversed", "", "ended", "yes"),
        "P217A220158": ("continued", "continued", "", "ended", "no"),
        "P217A250002": ("continued", "continued", "", "new", "no"),
    }


def test_each_run_appends_a_funding_status_snapshot_keyed_by_fain_budget_period_and_as_of(project):
    write_actions(project.raw_usaspending, PULL, AUGSBURG_MCNAIR)

    project.topo("run", "--as-of", "2026-04-01")
    project.topo("run", "--as-of", PULL)
    project.topo("run", "--as-of", PULL)  # a rerun under the same As-of date adds nothing

    history = pl.read_parquet(project.output / HISTORY).sort("as_of_date", "budget_period_start")
    assert history.select("fain", "budget_period_start", "as_of_date", "funding_status").rows() == [
        ("P217A220172", d("2022-10-01"), d("2026-04-01"), "continued"),
        ("P217A220172", d("2023-10-01"), d("2026-04-01"), "continued"),
        ("P217A220172", d("2024-10-01"), d("2026-04-01"), "continued"),
        ("P217A220172", d("2025-10-01"), d("2026-04-01"), "funded late"),
        ("P217A220172", d("2022-10-01"), d(PULL), "continued"),
        ("P217A220172", d("2023-10-01"), d(PULL), "continued"),
        ("P217A220172", d("2024-10-01"), d(PULL), "continued"),
        ("P217A220172", d("2025-10-01"), d(PULL), "funded late"),
        ("P217A220172", d("2026-10-01"), d(PULL), "not yet readable"),
    ]
    readable_from = history.filter(pl.col("funding_status") == "not yet readable")["readable_from"].to_list()
    assert readable_from == [d("2026-12-30")]
    assert set(history["pull_date"].to_list()) == {d(PULL)}


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def test_the_history_gets_a_run_log_row_per_append_and_a_sidecar_for_its_latest_append(project):
    write_actions(project.raw_usaspending, PULL, AUGSBURG_MCNAIR)

    project.topo("run", "--as-of", "2026-04-01")
    project.topo("run", "--as-of", PULL)
    project.topo("run", "--as-of", PULL)

    log = pl.read_parquet(project.output / "run_log.parquet").filter(
        (pl.col("layer") == "join") & (pl.col("source") == "funding_status_history")
    )
    assert log.select("rows_in", "rows_out").rows() == [(4, 4), (5, 5), (5, 0)]
    assert log["drops"].to_list()[-1] == [{"reason": "already_in_history", "rows": 5}]
    sidecar = json.loads((project.output / f"{HISTORY}.provenance.json").read_text())
    assert (sidecar["output"], sidecar["as_of"], sidecar["pull_date"]) == (HISTORY, PULL, PULL)
    assert sidecar["run_id"] == log["run_id"].to_list()[-1]
