"""The match-quality report on Host linking (Markdown), delivered as output/match_quality_<Pull date>.md.

Sections: outcome split by count and dollars; accuracy per Case label with its
sample size and gating; overrides in force; review and unmatched lists by FAIN;
Recipients with no UEI link; UEI error exposure; still-active pre-2022 Grants
with no UEI; breakdowns by Program and by start year; Pull date, As-of date and
input hashes. Dollars are obligations over the reporting-window fiscal years.
Context reason codes: Grants per Local context reason code (#38), every code
listed. Later tickets add the renewal-timing backtest, the observed-gap table
and the founder spot-check block.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from topo.domain.host_gating import Gate
from topo.domain.host_linking import MATCHED, NO_SINGLE_HOST, REVIEW, UNMATCHED
from topo.domain.local_context import context_reason_counts
from topo.fiscal import fiscal_year
from topo.outputs.delivery import delivery_path, write_new
from topo.outputs.review_queue import grant_dollars

STEM = "match_quality"
OUTCOMES = (MATCHED, NO_SINGLE_HOST, REVIEW, UNMATCHED)
UEI_ERA_START = dt.date(2022, 1, 1)  # Grants that started before 2022 were awarded under DUNS


@dataclass(frozen=True)
class MatchQualityInputs:
    pull_date: dt.date
    as_of: dt.date
    grants: pl.DataFrame  # joined grants
    fy_obligations: pl.DataFrame
    host_links: pl.DataFrame  # gated and overridden (topo.domain.host_gating.GatedHostLinks)
    candidates: pl.DataFrame  # host_link_candidates
    accuracy: pl.DataFrame  # CaseLabelAccuracy
    gate: Gate
    answer_key_rows: int
    tuning_set_rows: int
    input_hashes: list[tuple[str, str]]  # (path, sha256)
    local_context: pl.DataFrame | None = None  # joined local_context (topo.domain.local_context.LocalContext)


def _money(value: float | None) -> str:
    return f"${(value or 0):,.0f}"


def _pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f}%" if whole else ""


def _cell(value) -> str:
    return "" if value is None else str(value).replace("|", "/")


def _table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return lines


def _outcome_counts(frame: pl.DataFrame, by: str) -> list[list]:
    rows = []
    for key in sorted(frame[by].unique().to_list(), key=lambda v: (v is None, v)):
        part = frame.filter(pl.col(by) == key) if key is not None else frame.filter(pl.col(by).is_null())
        counts = [part.filter(pl.col("outcome") == o).height for o in OUTCOMES]
        rows.append([key, *counts, part.height, _money(part["dollars"].sum())])
    return rows


def render_match_quality(inputs: MatchQualityInputs) -> str:
    grants = inputs.grants.join(grant_dollars(inputs.grants, inputs.fy_obligations), on="fain")
    links = inputs.host_links.join(
        grants.select("fain", "recipient_name", "recipient_uei", "recipient_state", "program", "project_start",
                      "project_end", "dollars"),
        on="fain",
    )
    total_n, total_usd = links.height, links["dollars"].sum()
    out = [
        "# Match-quality report",
        "",
        f"Pull date: {inputs.pull_date.isoformat()}. As-of date: {inputs.as_of.isoformat()}. "
        f"Grants: {total_n}. Dollars are obligations over the reporting-window fiscal years.",
        "",
        "## Outcome split",
        "",
    ]
    split = []
    for outcome in OUTCOMES:
        part = links.filter(pl.col("outcome") == outcome)
        usd = part["dollars"].sum()
        split.append([outcome, part.height, _pct(part.height, total_n), _money(usd), _pct(usd, total_usd)])
    out += _table(["Outcome", "Grants", "Share of Grants", "Dollars", "Share of dollars"], split)

    gate = inputs.gate
    out += [
        "",
        "## Accuracy per Case label",
        "",
        f"A Case label that decides automatically is auto-accepted at {gate.accuracy:.0%} or better with at least "
        f"{gate.min_checks} checks on the frozen answer key, demoted to review below that, and unverified with fewer "
        f"checks (its rule outcome then stands). Answer key: {inputs.answer_key_rows} rows. Tuning set: "
        f"{inputs.tuning_set_rows} rows, never scored here. Accuracy is measured on the rules' own decisions, "
        "before overrides.",
        "",
    ]
    out += _table(
        ["Case label", "Rule outcome", "Links", "Checks", "Correct", "Accuracy", "Gating"],
        [
            [r["case_label"], r["rule_outcome"], r["links"], r["checks"], r["correct"],
             "" if r["accuracy"] is None else f"{100 * r['accuracy']:.1f}%", r["gating"]]
            for r in inputs.accuracy.iter_rows(named=True)
        ],
    )

    overridden = links.filter(pl.col("gating") == "override").sort("fain")
    out += ["", "## Overrides", "", f"{overridden.height} Host links decided by a reviewer's override.", ""]
    out += _table(
        ["FAIN", "Host", "Reviewer", "Date", "Note", "Rule case label"],
        [
            [r["fain"], f"{r['host_kind']} {r['host_id']}" if r["host_id"] else "no single Host",
             r["override_reviewer"], r["override_date"], r["override_note"], r["rule_case_label"]]
            for r in overridden.iter_rows(named=True)
        ],
    )

    for heading, outcome in (("Review list", REVIEW), ("Unmatched list", UNMATCHED)):
        part = links.filter(pl.col("outcome") == outcome).sort("fain")
        out += ["", f"## {heading}", "", f"{part.height} Grants, {_money(part['dollars'].sum())}.", ""]
        out += _table(
            ["FAIN", "Recipient", "State", "Program", "Case label", "Gating", "Dollars"],
            [
                [r["fain"], r["recipient_name"], r["recipient_state"], r["program"], r["case_label"], r["gating"],
                 _money(r["dollars"])]
                for r in part.iter_rows(named=True)
            ],
        )

    uei_linked = inputs.candidates.filter(pl.col("signals").str.split("+").list.contains("uei"))["fain"].unique()
    no_link = (
        links.with_columns(pl.col("fain").is_in(uei_linked.implode()).alias("uei_linked"))
        .group_by("recipient_name", "recipient_uei", "recipient_state")
        .agg(pl.col("uei_linked").any(), pl.len().alias("grants"), pl.col("dollars").sum())
        .filter(~pl.col("uei_linked"))
        .sort("recipient_state", "recipient_name", "recipient_uei", nulls_last=True)
    )
    out += [
        "",
        "## Recipients with no UEI link",
        "",
        f"{no_link.height} Recipients whose UEI matched no same-state IPEDS unit on any of their Grants "
        "(UEI \"none\": the Recipient carries no UEI and is matched on name and text only).",
        "",
    ]
    out += _table(
        ["Recipient", "Recipient UEI", "State", "Grants", "Dollars"],
        [
            [r["recipient_name"], r["recipient_uei"] or "none", r["recipient_state"], r["grants"], _money(r["dollars"])]
            for r in no_link.iter_rows(named=True)
        ],
    )

    picked = links.filter(pl.col("host_id").is_not_null() & pl.col("outcome").is_in([MATCHED, REVIEW])).join(
        inputs.candidates.select("fain", "host_kind", "host_id", "signals"), on=["fain", "host_kind", "host_id"]
    )
    exposed = picked.filter(pl.col("signals") == "uei")
    by_label = exposed.group_by("case_label").agg(pl.len().alias("grants"), pl.col("dollars").sum()).sort("case_label")
    out += [
        "",
        "## UEI error exposure",
        "",
        f"{exposed.height} Grants ({_money(exposed['dollars'].sum())}) have a Host that rests on the Recipient UEI "
        "alone, with no other signal agreeing. If IPEDS lists that UEI against the wrong unit, these links are wrong.",
        "",
    ]
    out += _table(
        ["Case label", "Grants", "Dollars"],
        [[r["case_label"], r["grants"], _money(r["dollars"])] for r in by_label.iter_rows(named=True)],
    )

    pre_uei = links.filter(
        pl.col("recipient_uei").is_null()
        & (pl.col("project_start") < UEI_ERA_START)
        & (pl.col("project_end") >= inputs.as_of)
    ).sort("fain")
    out += [
        "",
        "## Still-active pre-2022 Grants with no UEI",
        "",
        f"{pre_uei.height} Grants started before {UEI_ERA_START.isoformat()}, are still active on the As-of date "
        "(project end on or after it) and carry no Recipient UEI on any action. No DUNS value is used to link them.",
        "",
    ]
    out += _table(
        ["FAIN", "Recipient", "State", "Program", "Outcome"],
        [[r["fain"], r["recipient_name"], r["recipient_state"], r["program"], r["outcome"]]
         for r in pre_uei.iter_rows(named=True)],
    )

    header = [*OUTCOMES, "Grants", "Dollars"]
    out += ["", "## By Program", ""]
    out += _table(["Program", *header], _outcome_counts(links, "program"))
    by_year = links.with_columns(
        pl.col("project_start").map_elements(fiscal_year, return_dtype=pl.Int64).alias("start_fy")
    )
    out += ["", "## By start year", "", "Fiscal year of the Grant's project start.", ""]
    out += _table(["Start FY", *header], _outcome_counts(by_year, "start_fy"))

    if inputs.local_context is not None:
        reasons = context_reason_counts(inputs.local_context)
        out += [
            "",
            "## Context reason codes",
            "",
            "Grants whose Local context is blank, in whole or in part, by reason. Context comes only through the "
            "Host institution, never the Recipient or the state. A Grant can carry more than one code.",
            "",
        ]
        out += _table(["Context reason", "Grants"], reasons.rows())

    out += ["", "## Inputs", ""]
    out += _table(["Input", "SHA-256"], [[path, sha] for path, sha in inputs.input_hashes])
    return "\n".join(out) + "\n"


def write_match_quality(text: str, output_dir: Path, pull_date: dt.date) -> Path:
    path = delivery_path(output_dir, STEM, pull_date, "md")
    write_new(path, text.encode())
    return path
