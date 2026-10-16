"""The one-pager: a plain-language summary for the founder, delivered as
output/one_pager_<Pull date>.md and the same text rendered to a one-page PDF.

Sections: what's out there, what's changed since 2025, what's coming up, and
how far to trust this. Headline numbers carry a one-word marker such as
"[provisional 1]" that points to numbered item 1 of "How far to trust this"
(at most 8 one-sentence items). The Census notice sits in the footer.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from topo.domain.funding_status import DISRUPTION_RESTORED, FUNDED_LATE, REVERSED, UNFUNDED, add_months
from topo.domain.programs import PROGRAMS
from topo.domain.fac_plausibility import BASIS as FAC_BASIS
from topo.domain.fac_plausibility import REVIEW as FAC_REVIEW
from topo.domain.reconciliation import EXCEEDS_APPROPRIATION_UNEXPLAINED, UNEXPLAINED
from topo.domain.renewal_backtest import MISS, PASS
from topo.fiscal import ReportingWindow, fy_label
from topo.outputs.delivery import delivery_paths, write_new
from topo.outputs.pdf import render_pdf
from topo.outputs.target_list import CENSUS_NOTICE

STEM = "one_pager"
MAX_TRUST_ITEMS = 8
ALL_PROGRAMS = "All Programs"

DISRUPTION_PATTERNS = (UNFUNDED, FUNDED_LATE, REVERSED)

# Trust item keys
PROVISIONAL = "provisional"
PATTERN = "pattern"
UNTESTED = "untested"
CHECKED = "checked"
BLIND_SPOT = "blind spot"
FAC = "fac"


@dataclass(frozen=True)
class OnePagerSettings:
    """`[one_pager]` in config.toml: the normal-year baseline for the disruption counts."""

    baseline_unfunded_grants: int = 95
    baseline_year: int = 2024
    baseline_source: str = "docs/research/status-signals-2025-26.md"

    @classmethod
    def from_section(cls, section: dict[str, Any]) -> "OnePagerSettings":
        return cls(
            baseline_unfunded_grants=int(section["baseline_unfunded_grants"]),
            baseline_year=int(section["baseline_year"]),
            baseline_source=str(section["baseline_source"]),
        )


@dataclass(frozen=True)
class OnePagerInputs:
    pull_date: dt.date
    as_of: dt.date
    window: ReportingWindow
    grants: pl.DataFrame  # joined grants (fain, program)
    fy_obligations: pl.DataFrame  # joined fy_obligations (fain, fiscal_year, obligation)
    provisional_fys: list[int] = field(default_factory=list)  # window FYs still inside the reporting lag
    provisional_lag_days: int = 90
    awaited: dict[str, str] = field(default_factory=dict)  # Program -> "FY2026 new awards not yet reported"
    funding_periods: pl.DataFrame | None = None  # joined funding_status: (fain, Budget period) with `disrupted`
    grant_funding: pl.DataFrame | None = None  # joined grant_funding_status: one row per FAIN with `disruption`
    disruption_window: tuple[dt.date, dt.date] = (dt.date(2025, 5, 1), dt.date(2026, 9, 30))
    evidence: pl.DataFrame | None = None  # joined unfunded_ed_list_evidence (with the `large` trigger)
    settings: OnePagerSettings = OnePagerSettings()
    grant_actions: pl.DataFrame | None = None  # joined grant_actions (award dates and dollars of new Grants)
    timing: pl.DataFrame | None = None  # joined renewal_timing: Re-competing soon, Predicted due date, evidence tier
    new_award_months: int = 3  # [target_list] new_award_months
    lead_months: int = 12  # [renewal_timing] lead_months
    reconciliation: pl.DataFrame | None = None  # joined reconciliation table
    backtest: pl.DataFrame | None = None  # joined renewal_backtest (#41): one row per TRIO Program
    backtest_bar: float = 0.95  # [renewal_backtest] pass_bar
    fac: pl.DataFrame | None = None  # joined fac_plausibility (#43): one row per (Recipient UEI, listing)


@dataclass(frozen=True)
class OnePagerFiles:
    markdown: Path
    pdf: Path


class TrustItems:
    """The numbered "How far to trust this" items; markers point to them by key."""

    def __init__(self, items: list[tuple[str, str]]):
        if len(items) > MAX_TRUST_ITEMS:
            raise ValueError(f"{len(items)} trust items; the one-pager allows {MAX_TRUST_ITEMS}")
        self.items = items
        self._number = {key: n for n, (key, _) in enumerate(items, start=1)}

    def marker(self, key: str, word: str) -> str:
        return f"[{word} {self._number[key]}]"

    def lines(self) -> list[str]:
        return [f"{n}. {sentence}" for n, (_, sentence) in enumerate(self.items, start=1)]


def money(value: float) -> str:
    """Short dollars: $250K, $1.5M, $1.14B, -$4.8M."""
    sign, value = ("-" if value < 0 else ""), abs(value)
    if value >= 1e9:
        return f"{sign}${value / 1e9:,.2f}B"
    if value >= 1e6:
        return f"{sign}${value / 1e6:,.1f}M"
    return f"{sign}${value / 1e3:,.0f}K"


def _untested_item(backtest: pl.DataFrame | None, bar: float) -> str:
    """The predictions caveat, with the backtest's per-Program results when it has scored any."""
    rule = "each is the prior Cohort's published deadline plus 60 months (or a deadline already published)"
    scored = pl.DataFrame() if backtest is None else backtest.filter(pl.col("result").is_in([PASS, MISS]))
    if not scored.height:
        return f"Predicted due dates are predictions not yet tested: {rule}, and the rule's backtest has not been scored."
    fy = fy_label(scored["competition_fy"].max())
    results = ", ".join(
        f"{r['program']} {r['result']}" for r in scored.sort("program").iter_rows(named=True)
    )
    passed = scored.filter(pl.col("result") == PASS).height
    errors = scored["timing_error_months"].drop_nulls().abs()
    error = f", mean timing error {errors.mean():.1f} months" if errors.len() else ""
    return (
        f"Predicted due dates are predictions not yet tested on the coming competitions: {rule}; on the {fy} "
        f"backtest {passed} of {scored.height} Programs met the {bar:.0%} recall and precision bar ({results}{error})."
    )


def _unexplained_item(inputs: OnePagerInputs) -> str:
    """Every unexplained reconciliation row, named in one sentence."""
    table = inputs.reconciliation
    rows = pl.DataFrame() if table is None else table.filter(
        pl.col("gap_reason_code").is_in([UNEXPLAINED, EXCEEDS_APPROPRIATION_UNEXPLAINED])
    )
    file = f"reconciliation_{inputs.pull_date.isoformat()}.csv"
    if not rows.height:
        return (f"No reconciliation row is unexplained: against ED's totals and grantee lists every row in {file} "
                "reconciles, has a stated reason, or could not be compared.")
    named = "; ".join(
        f"{program} {check} {', '.join(fy_label(fy) for fy in sorted(fys))}"
        for program, check, fys in rows.group_by("program", "check").agg("fiscal_year").sort("program", "check").rows()
    )
    rows_are = "row is" if rows.height == 1 else "rows are"
    return f"{rows.height} reconciliation {rows_are} unexplained, with no reason found for the gap ({file}): {named}."


def _trust_items(inputs: OnePagerInputs) -> TrustItems:
    items: list[tuple[str, str]] = []
    if inputs.provisional_fys:
        years = ", ".join(fy_label(fy) for fy in inputs.provisional_fys)
        by_note: dict[str, list[str]] = {}
        for program, note in sorted(inputs.awaited.items()):
            by_note.setdefault(note, []).append(program)
        awaited = "".join(f", with {note} for {' and '.join(programs)}" for note, programs in by_note.items())
        items.append((PROVISIONAL, (
            f"{years} {'is' if len(inputs.provisional_fys) == 1 else 'are'} provisional (as of {inputs.pull_date.isoformat()}; reporting lag): USAspending is still "
            f"catching up until {inputs.provisional_lag_days} days after the year ends{awaited}."
        )))
    items.append((PATTERN, (
        "Funding status is a pattern read from funding actions, never a cause: gaps are routine in normal years and "
        "court records name only about 11 Grants, so the counts are not proof of a policy cut."
    )))
    items.append((UNTESTED, _untested_item(inputs.backtest, inputs.backtest_bar)))
    items.append((CHECKED, _unexplained_item(inputs)))
    items.append((BLIND_SPOT, (
        "Blind spot: applications that were never funded have no FAIN, so they are not Grants and appear nowhere "
        "here; this covers funded Grants only."
    )))
    if inputs.fac is not None and inputs.fac.height:
        fac = inputs.fac
        review = fac.filter(pl.col("flag") == FAC_REVIEW).height
        span = f"{fy_label(fac['span_start_fy'].min())} to {fy_label(fac['span_end_fy'].max())}"
        items.append((FAC, (
            f"Federal Audit Clearinghouse (FAC) spending was compared {span} as {FAC_BASIS}: {review} of "
            f"{fac.height} Recipient-and-listing pairs found in both sources are marked review, with no pass or fail "
            f"(fac_plausibility_{inputs.pull_date.isoformat()}.csv)."
        )))
    return TrustItems(items)


def _whats_out_there(inputs: OnePagerInputs, trust: TrustItems) -> list[str]:
    fys = inputs.window.fiscal_years
    by_program = (
        inputs.fy_obligations.join(inputs.grants.select("fain", "program"), on="fain")
        .group_by("program", "fiscal_year")
        .agg((pl.col("obligation") > 0).sum().alias("grants"), pl.col("obligation").sum().alias("dollars"))
    )
    totals = by_program.group_by("fiscal_year").agg(pl.col("grants").sum(), pl.col("dollars").sum()).with_columns(
        pl.lit(ALL_PROGRAMS).alias("program")
    )
    cells = {
        (r["program"], r["fiscal_year"]): f"{r['grants']} / {money(r['dollars'])}" if r["grants"] else "-"
        for r in pl.concat([by_program, totals.select(by_program.columns)]).iter_rows(named=True)
    }
    header = [
        fy_label(fy) + (f" {trust.marker(PROVISIONAL, 'provisional')}" if fy in inputs.provisional_fys else "")
        for fy in fys
    ]
    names = [p.name for p in PROGRAMS] + [ALL_PROGRAMS]
    out = [
        f"Grants funded and dollars obligated per fiscal year, by Program, {fy_label(fys[0])} to {fy_label(fys[-1])} "
        "(USAspending obligations by action date; a Grant counts in a year when its net obligation that year is "
        f"positive), checked against ED's published totals {trust.marker(CHECKED, 'checked')}.",
        "",
    ]
    out += _table(["Program", *header], [[name, *(cells.get((name, fy), "-") for fy in fys)] for name in names])
    return out


def _whats_changed(inputs: OnePagerInputs, trust: TrustItems) -> list[str]:
    periods = inputs.funding_periods
    disrupted = periods.filter(pl.col("disrupted")) if periods is not None else pl.DataFrame(
        schema={"fain": pl.String, "funding_status": pl.String})
    grants = disrupted["fain"].n_unique()
    restored = 0 if inputs.grant_funding is None else inputs.grant_funding.filter(
        pl.col("disruption") == DISRUPTION_RESTORED).height
    start, end = inputs.disruption_window
    settings = inputs.settings
    out = [
        f"{grants} Grants {trust.marker(PATTERN, 'pattern')} had a Budget period starting {start.isoformat()} to "
        f"{end.isoformat()} that was unfunded, funded late or reversed; {restored} since restored. This is a "
        "funding pattern read from USAspending, not proof of a policy cut or any other cause. For a baseline, "
        f"{settings.baseline_unfunded_grants} Grants went unfunded in normal {settings.baseline_year} "
        f"({settings.baseline_source}).",
        "",
    ]
    out += _table(
        ["Funding pattern", "Grants"],
        [[p, disrupted.filter(pl.col("funding_status") == p)["fain"].n_unique()] for p in DISRUPTION_PATTERNS],
    )
    evidence = inputs.evidence
    if evidence is not None and evidence["large"].any():
        overall = evidence.filter(pl.col("fiscal_year").is_null()).row(0, named=True)
        out += [
            "",
            "Unfunded status may partly reflect USAspending reporting gaps: "
            f"{overall['with_ed_list_evidence']} of {overall['unfunded_budget_periods']} unfunded Budget periods "
            f"({100 * (overall['share'] or 0):.0f}%) show funding on an ED grantee list.",
        ]
    return out


def _whats_coming_up(inputs: OnePagerInputs, trust: TrustItems) -> list[str]:
    timing = inputs.timing
    soon = (
        timing.filter(pl.col("re_competing_soon"))
        .join(inputs.grants.select("fain", "program"), on="fain")
        .group_by("program", "predicted_due_date", "evidence_tier")
        .agg(pl.len().alias("grants"))
        .sort("predicted_due_date", "program")
        if timing is not None else pl.DataFrame()
    )
    out = []
    if soon.height:
        out += [
            f"Programs with Grants re-competing within {inputs.lead_months} months of the As-of date. The dates are "
            "predictions of the next application deadline, not announced dates unless the evidence tier says "
            "notice published.",
            "",
        ]
        out += _table(
            ["Program", "Predicted due date", "Evidence tier", "Grants re-competing"],
            [[r["program"], f"{r['predicted_due_date'].isoformat()} {trust.marker(UNTESTED, 'untested')}",
              r["evidence_tier"], r["grants"]] for r in soon.iter_rows(named=True)],
        )
    else:
        out.append(
            f"No Program has Grants re-competing within {inputs.lead_months} months of the As-of date by the "
            f"predicted due dates on file {trust.marker(UNTESTED, 'untested')}."
        )
    months = inputs.new_award_months
    out += ["", f"### New Grants in the last {months} months", ""]
    new = _new_grants(inputs)
    if new.height:
        out += _table(
            ["Program", "New Grants", "Dollars"],
            [[r["program"], r["grants"], money(r["dollars"])] for r in new.iter_rows(named=True)],
        )
    else:
        out.append(f"No new Grants were awarded in the {months} months up to the As-of date.")
    return out


def _new_grants(inputs: OnePagerInputs) -> pl.DataFrame:
    """Per Program: Grants whose first award (A1) is within `new_award_months` before the As-of date."""
    if inputs.grant_actions is None:
        return pl.DataFrame()
    actions = inputs.grant_actions.filter(pl.col("action_date") <= inputs.as_of)
    awarded = actions.filter(pl.col("action_type") == "A1").group_by("fain").agg(
        pl.col("action_date").min().alias("award_date"))
    since = add_months(inputs.as_of, -inputs.new_award_months)
    new = awarded.filter(pl.col("award_date") >= since)["fain"]
    return (
        actions.filter(pl.col("fain").is_in(new.implode()))
        .join(inputs.grants.select("fain", "program"), on="fain")
        .group_by("program")
        .agg(pl.col("fain").n_unique().alias("grants"), pl.col("obligation").sum().alias("dollars"))
        .sort("program")
    )


def _table(header: list[str], rows: list[list]) -> list[str]:
    def cell(value) -> str:
        return "" if value is None else str(value).replace("|", "/")

    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return lines + ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]


def render_one_pager(inputs: OnePagerInputs) -> str:
    trust = _trust_items(inputs)
    out = [
        "# TRIO and GEAR UP Grants: one-page summary",
        "",
        f"Pull date {inputs.pull_date.isoformat()}. As-of date {inputs.as_of.isoformat()}.",
        "",
        "## What's out there",
        "",
        *_whats_out_there(inputs, trust),
        "",
        "## What's changed since 2025",
        "",
        *_whats_changed(inputs, trust),
        "",
        "## What's coming up",
        "",
        *_whats_coming_up(inputs, trust),
        "",
        "## How far to trust this",
        "",
        *trust.lines(),
        "",
        "---",
        "",
        f"Sources: USAspending.gov, accessed {inputs.pull_date.isoformat()} (Recipient data include D&B Open Data); "
        "ED grantee lists and budget tables; IPEDS and CCD via the Urban Institute Education Data Portal (ODC-By).",
        CENSUS_NOTICE,
    ]
    return "\n".join(out) + "\n"


def write_one_pager(text: str, output_dir: Path, pull_date: dt.date) -> OnePagerFiles:
    """Write the Markdown and its PDF under one version suffix; never overwrite."""
    paths = delivery_paths(output_dir, STEM, pull_date, ("md", "pdf"))
    write_new(paths["md"], text.encode())
    write_new(paths["pdf"], render_pdf(text))
    return OnePagerFiles(markdown=paths["md"], pdf=paths["pdf"])
