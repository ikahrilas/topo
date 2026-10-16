"""The reconciliation table (#14, #42): the data compared with outside totals, nothing adjusted.

One long table, one row per (check, Program, FY) in the reporting window. Each
row carries both sides' values, the gap (compared - reference), the tolerance,
a Budget-period-variant diagnostic, a Reconciliation status, a Gap reason code
from a closed vocabulary, and a cited note. No cell is ever blank for want of a
figure: a side that can't be compared reads `not_published`, a program-year with
no ED grantee list reads `no_ed_list`.

Checks:
    appropriation_vs_allocations   (a) TRIO appropriation vs the sum of ED's seven per-program
                                   allocations. An overage is `exceeds_appropriation_unexplained`;
                                   a shortfall is shown as the unallocated remainder, no pass/fail.
    ed_allocation_dollars          (b) ED per-program allocation vs USAspending obligations
    ed_allocation_count            (b) ED per-program number of awards vs USAspending Grants funded
                                   (within the relative tolerance, or the absolute one for dollars,
                                   whichever is larger)
    ed_list_dollars                (c) ED grantee list total vs USAspending, exact. TRIO: every
    ed_list_count                      Grant of the Program; GEAR UP: new awards (A1) only.

FY basis: the action-date FY is primary. The Budget-period variant labels each
action by the FY its Budget period starts in; a row that passes only on the
variant is `timing_difference`. A year that ended less than `provisional_after_days`
before the Pull date and does not reconcile is `provisional`, not failed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import pandera.polars as pa
import polars as pl

from topo.domain.funding_status import UNFUNDED
from topo.domain.programs import GEAR_UP, PROGRAMS, TRIO
from topo.fiscal import ReportingWindow, fiscal_year, fy_end, fy_label
from topo.guards import StructuralBreak, check_schema, check_unique

# Checks
APPROPRIATION_VS_ALLOCATIONS = "appropriation_vs_allocations"
ED_ALLOCATION_DOLLARS = "ed_allocation_dollars"
ED_ALLOCATION_COUNT = "ed_allocation_count"
ED_LIST_DOLLARS = "ed_list_dollars"
ED_LIST_COUNT = "ed_list_count"
CHECKS = (APPROPRIATION_VS_ALLOCATIONS, ED_ALLOCATION_DOLLARS, ED_ALLOCATION_COUNT, ED_LIST_DOLLARS, ED_LIST_COUNT)

# Reconciliation status
RECONCILED = "reconciled"
STATED_DIFFERENCE = "stated difference"
NOT_COMPARABLE = "not comparable"

# Gap reason codes (closed vocabulary)
NOT_PUBLISHED = "not_published"
TIMING_DIFFERENCE = "timing_difference"
NO_ED_LIST = "no_ed_list"
PROVISIONAL = "provisional"
UNEXPLAINED = "unexplained"
EXCEEDS_APPROPRIATION_UNEXPLAINED = "exceeds_appropriation_unexplained"
GAP_REASON_CODES = (
    NOT_PUBLISHED, TIMING_DIFFERENCE, NO_ED_LIST, PROVISIONAL, UNEXPLAINED, EXCEEDS_APPROPRIATION_UNEXPLAINED,
)
NOT_COMPARABLE_CODES = (NOT_PUBLISHED, NO_ED_LIST)

FEDERAL_TRIO_PROGRAMS = "Federal TRIO Programs"
TRIO_PROGRAMS = tuple(p.name for p in PROGRAMS if p.family == TRIO)
GEAR_UP_PROGRAMS = tuple(p.name for p in PROGRAMS if p.family == GEAR_UP)
ALL_PROGRAMS = "All Programs"
ED_LIST_FILED = "ok"

# FY basis of a USAspending total
ACTION_DATE = "action_date"
BUDGET_PERIOD = "budget_period"

# ED-list FAIN differences (TRIO)
ED_LIST_ONLY = "ed_list_only"
USASPENDING_ONLY = "usaspending_only"
AMOUNT_DIFFERENCE = "amount_difference"


@dataclass(frozen=True)
class Tolerances:
    """Fixed in config before the first run (ASSUMPTION) and never tuned to close a gap."""

    relative: float  # (b): share of the reference value
    absolute_usd: float  # (b) dollars: the floor, whichever is larger
    count_relative: float  # (b) counts
    provisional_after_days: int  # a year ended fewer days than this before the Pull date is provisional
    evidence_large_share_overall: float  # ED-list evidence for unfunded Budget periods is "large" at or above
    evidence_large_share_program_fy: float  # ... or above this in any Program x FY

    @classmethod
    def from_config(cls, config) -> Tolerances:
        tolerances = config.tolerances
        section = config.section("reconciliation")
        return cls(
            relative=float(tolerances["reconciliation_relative"]),
            absolute_usd=float(tolerances["reconciliation_absolute_usd"]),
            count_relative=float(tolerances["reconciliation_count_relative"]),
            provisional_after_days=int(section["provisional_after_days"]),
            evidence_large_share_overall=float(section["evidence_large_share_overall"]),
            evidence_large_share_program_fy=float(section["evidence_large_share_program_fy"]),
        )


class Reconciliation(pa.DataFrameModel):
    """One row per (check, Program, FY)."""

    check: str = pa.Field(isin=list(CHECKS))
    program: str
    fiscal_year: int
    reference_source: str
    reference_value: float = pa.Field(nullable=True)
    compared_source: str
    compared_value: float = pa.Field(nullable=True)
    gap: float = pa.Field(nullable=True)  # compared - reference
    tolerance: float = pa.Field(nullable=True)
    budget_period_value: float = pa.Field(nullable=True)  # compared side by Budget-period-start FY
    budget_period_gap: float = pa.Field(nullable=True)
    unallocated_remainder: float = pa.Field(nullable=True)  # (a) only
    reconciliation_status: str = pa.Field(isin=[RECONCILED, STATED_DIFFERENCE, NOT_COMPARABLE])
    gap_reason_code: str = pa.Field(nullable=True, isin=list(GAP_REASON_CODES))
    note: str  # cited note

    class Config:
        strict = True


@dataclass(frozen=True)
class ReconciliationInputs:
    window: ReportingWindow
    pull_date: dt.date
    appropriations: pl.DataFrame  # curated_totals.Appropriations
    allocations: pl.DataFrame  # curated_totals.ProgramAllocations
    grants: pl.DataFrame  # joined Grants (fain, program, ...)
    grant_actions: pl.DataFrame  # joined GrantActions
    ed_trio_list_rows: pl.DataFrame  # cleaned EdTrioListRows (amounts are used only here)
    ed_gearup_list_rows: pl.DataFrame  # cleaned EdGearUpListRows (new awards)
    ed_list_coverage: pl.DataFrame  # cleaned EdListCoverage: filed or missing per (Program, FY)
    funding_status: pl.DataFrame  # joined BudgetPeriodFundingStatus (read, never changed here)


class EdListFainDifferences(pa.DataFrameModel):
    """TRIO ED-list rows that disagree with USAspending, by FAIN (action-date FY; neither side corrected)."""

    program: str
    fiscal_year: int
    fain: str
    kind: str = pa.Field(isin=[ED_LIST_ONLY, USASPENDING_ONLY, AMOUNT_DIFFERENCE])
    ed_amount: float = pa.Field(nullable=True)
    usaspending_amount: float = pa.Field(nullable=True)  # action-date FY
    budget_period_amount: float = pa.Field(nullable=True)  # Budget-period-start FY

    class Config:
        strict = True


class UnfundedEdListEvidence(pa.DataFrameModel):
    """Unfunded Budget periods with ED-list evidence (on a TRIO list with funding, no USAspending action).

    One row per (Program, FY) with an unfunded Budget period, plus an overall row
    (program "All Programs", no FY) that is always present. FY is the list year:
    the FY<N> list funds the N-(N+1) project year, so a Budget period is matched by
    the calendar year it starts in.
    """

    program: str
    fiscal_year: int = pa.Field(nullable=True)
    unfunded_budget_periods: int = pa.Field(ge=0)
    with_ed_list_evidence: int = pa.Field(ge=0)
    share: float = pa.Field(nullable=True)
    large: bool

    class Config:
        strict = True


@dataclass(frozen=True)
class ReconciliationResult:
    table: pl.DataFrame
    ed_list_fain_differences: pl.DataFrame
    unfunded_ed_list_evidence: pl.DataFrame

    @property
    def evidence_is_large(self) -> bool:
        return bool(self.unfunded_ed_list_evidence["large"].any())


def _money(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.0f}"


def _row(check: str, program: str, fy: int, reference_source: str, compared_source: str, **values: Any) -> dict:
    row = {
        "check": check, "program": program, "fiscal_year": fy,
        "reference_source": reference_source, "reference_value": None,
        "compared_source": compared_source, "compared_value": None,
        "gap": None, "tolerance": None, "budget_period_value": None, "budget_period_gap": None,
        "unallocated_remainder": None, "gap_reason_code": None,
    }
    row.update(values)
    return row


def _appropriation_vs_allocations(inputs: ReconciliationInputs) -> list[dict]:
    """(a) TRIO appropriation vs the sum of ED's seven per-program allocations."""
    rows = []
    appropriations = inputs.appropriations.filter(pl.col("program_family") == TRIO)
    for fy in inputs.window.fiscal_years:
        filed = appropriations.filter(pl.col("fiscal_year") == fy)
        allocations = inputs.allocations.filter(
            (pl.col("fiscal_year") == fy) & pl.col("program").is_in(list(TRIO_PROGRAMS))
        )
        citations = sorted(set(filed["citation"].to_list()) | set(allocations["citation"].to_list()))
        published = allocations.filter(pl.col("allocation_usd").is_not_null())
        unpublished = sorted(set(TRIO_PROGRAMS) - set(published["program"].to_list()))
        if filed.height == 0 or unpublished:
            missing = (["appropriation"] if filed.height == 0 else []) + (
                [f"ED allocation for {', '.join(unpublished)}"] if unpublished else []
            )
            notes = [n for n in (filed["note"].to_list() + allocations["note"].to_list()) if n]
            rows.extend(
                _row(
                    APPROPRIATION_VS_ALLOCATIONS, FEDERAL_TRIO_PROGRAMS, fy, "appropriation", "ED allocations sum",
                    reference_value=amount, reconciliation_status=NOT_COMPARABLE, gap_reason_code=NOT_PUBLISHED,
                    note="; ".join(
                        [f"{fy_label(fy)}: no published {' or '.join(missing)} filed in data/curated", *notes,
                         *citations]
                    ),
                )
                for amount in (filed["amount_usd"].to_list() or [None])
            )
            continue
        total = float(published["allocation_usd"].sum())
        for amount in filed["amount_usd"].to_list():
            gap = total - amount
            if gap > 0:
                status, code = STATED_DIFFERENCE, EXCEEDS_APPROPRIATION_UNEXPLAINED
                remainder = None
                lead = f"ED allocations sum {_money(gap)} above the appropriation; cause unknown"
            else:
                status, code = RECONCILED, None
                remainder = -gap
                lead = f"unallocated remainder {_money(remainder)}"
            rows.append(
                _row(
                    APPROPRIATION_VS_ALLOCATIONS, FEDERAL_TRIO_PROGRAMS, fy, "appropriation", "ED allocations sum",
                    reference_value=amount, compared_value=total, gap=gap, tolerance=0.0,
                    unallocated_remainder=remainder, reconciliation_status=status, gap_reason_code=code,
                    note="; ".join([lead, *citations]),
                )
            )
    return rows


def _usaspending_by_fy(inputs: ReconciliationInputs, actions: pl.DataFrame) -> pl.DataFrame:
    """Per (program, fain, fiscal_year, basis): net obligation; basis is action-date FY or Budget-period-start FY."""
    tagged = actions.join(inputs.grants.select("fain", pl.col("program").alias("grant_program")), on="fain").with_columns(
        pl.col("budget_period_start").fill_null(pl.col("action_date"))
        .map_elements(fiscal_year, return_dtype=pl.Int64).alias("budget_period_fy")
    )
    by_action = tagged.select("grant_program", "fain", pl.col("action_fy").cast(pl.Int64).alias("fiscal_year"),
                              "obligation", pl.lit(ACTION_DATE).alias("basis"))
    by_period = tagged.select("grant_program", "fain", pl.col("budget_period_fy").alias("fiscal_year"),
                              "obligation", pl.lit(BUDGET_PERIOD).alias("basis"))
    return (
        pl.concat([by_action, by_period])
        .group_by("grant_program", "fain", "fiscal_year", "basis")
        .agg(pl.col("obligation").sum())
        .rename({"grant_program": "program"})
    )


def _totals(by_fain: pl.DataFrame, program: str, fy: int, basis: str) -> tuple[float, int]:
    """(net dollars, Grants with positive net obligation) for one Program, FY and basis."""
    rows = by_fain.filter((pl.col("program") == program) & (pl.col("fiscal_year") == fy) & (pl.col("basis") == basis))
    return round(float(rows["obligation"].sum()), 2), rows.filter(pl.col("obligation") > 0).height


def _provisional(inputs: ReconciliationInputs, fy: int, tolerances: Tolerances) -> bool:
    return (inputs.pull_date - fy_end(fy)).days < tolerances.provisional_after_days


def _judge(
    reference: float, compared: float, variant: float | None, tolerance: float, provisional: bool
) -> tuple[str, str | None, str]:
    """(Reconciliation status, Gap reason code, note lead) for two comparable values."""
    if abs(compared - reference) <= tolerance + 1e-9:
        return RECONCILED, None, "within tolerance"
    if variant is not None and abs(variant - reference) <= tolerance + 1e-9:
        return STATED_DIFFERENCE, TIMING_DIFFERENCE, "reconciles only by Budget-period-start FY"
    if provisional:
        return STATED_DIFFERENCE, PROVISIONAL, "fiscal year ended too recently for USAspending to be complete"
    return STATED_DIFFERENCE, UNEXPLAINED, "no known cause"


def _compare(
    check: str, program: str, fy: int, reference_source: str, compared_source: str,
    reference: float | None, compared: float, variant: float, tolerance: float, provisional: bool,
    citations: list[str], unavailable: tuple[str, str] | None = None,
) -> dict:
    """One reconciliation row; `unavailable` = (code, note) when the reference side can't be compared."""
    if unavailable is not None or reference is None:
        code, lead = unavailable or (NOT_PUBLISHED, f"{fy_label(fy)}: {reference_source} not published")
        return _row(
            check, program, fy, reference_source, compared_source, compared_value=compared,
            budget_period_value=variant, reconciliation_status=NOT_COMPARABLE, gap_reason_code=code,
            note="; ".join([lead, *citations]),
        )
    status, code, lead = _judge(reference, compared, variant, tolerance, provisional)
    return _row(
        check, program, fy, reference_source, compared_source, reference_value=reference, compared_value=compared,
        gap=compared - reference, tolerance=tolerance, budget_period_value=variant,
        budget_period_gap=variant - reference, reconciliation_status=status, gap_reason_code=code,
        note="; ".join([lead, *citations]),
    )


def _ed_allocations_vs_usaspending(
    inputs: ReconciliationInputs, tolerances: Tolerances, by_fain: pl.DataFrame
) -> list[dict]:
    """(b) ED per-program allocation dollars and award counts vs USAspending, per TRIO Program and FY."""
    rows = []
    for program in TRIO_PROGRAMS:
        for fy in inputs.window.fiscal_years:
            dollars, count = _totals(by_fain, program, fy, ACTION_DATE)
            variant_dollars, variant_count = _totals(by_fain, program, fy, BUDGET_PERIOD)
            provisional = _provisional(inputs, fy, tolerances)
            filed = inputs.allocations.filter((pl.col("program") == program) & (pl.col("fiscal_year") == fy))
            if filed.height == 0:
                filed = pl.DataFrame(
                    {"allocation_usd": [None], "award_count": [None], "citation": [None], "note": [None]},
                    schema={"allocation_usd": pl.Float64, "award_count": pl.Int64, "citation": pl.String,
                            "note": pl.String},
                )
            for allocation, awards, citation, note in filed.select(
                "allocation_usd", "award_count", "citation", "note"
            ).iter_rows():
                citations = [c for c in (note, citation) if c] or ["no ED allocation filed in data/curated"]
                rows.append(_compare(
                    ED_ALLOCATION_DOLLARS, program, fy, "ED allocation", "USAspending obligations",
                    allocation, dollars, variant_dollars,
                    None if allocation is None else max(tolerances.relative * allocation, tolerances.absolute_usd),
                    provisional, citations,
                ))
                rows.append(_compare(
                    ED_ALLOCATION_COUNT, program, fy, "ED number of awards", "USAspending Grants funded",
                    None if awards is None else float(awards), float(count), float(variant_count),
                    None if awards is None else tolerances.count_relative * awards, provisional, citations,
                ))
    return rows


def _list_coverage(inputs: ReconciliationInputs, program: str, fy: int) -> tuple[bool, str]:
    """(filed, note): whether an ED grantee list is filed for the Program and FY."""
    rows = inputs.ed_list_coverage.filter((pl.col("program") == program) & (pl.col("fiscal_year") == fy))
    filed = rows.filter(pl.col("status") == ED_LIST_FILED)
    if filed.height:
        return True, "; ".join(f"ED list {f} filed {d}" for f, d in filed.select("raw_file", "filed_date").iter_rows())
    notes = [n for n in rows["note"].to_list() if n]
    return False, "; ".join([f"{fy_label(fy)}: no ED grantee list", *notes] if notes else [
        f"{fy_label(fy)}: no ED grantee list filed in the raw manifest"])


def _fain_differences(trio: pl.DataFrame, by_fain: pl.DataFrame, program: str, fy: int) -> pl.DataFrame:
    on_list = trio.select("fain", "ed_amount")
    funded = by_fain.filter((pl.col("program") == program) & (pl.col("fiscal_year") == fy))
    in_usaspending = funded.filter(pl.col("basis") == ACTION_DATE).select(
        "fain", pl.col("obligation").round(2).alias("usaspending_amount")
    ).filter(pl.col("usaspending_amount") != 0)
    by_period = funded.filter(pl.col("basis") == BUDGET_PERIOD).select(
        "fain", pl.col("obligation").round(2).alias("budget_period_amount")
    )
    both = on_list.join(in_usaspending, on="fain", how="full", coalesce=True).join(by_period, on="fain", how="left")
    return (
        both.with_columns(
            pl.when(pl.col("usaspending_amount").is_null()).then(pl.lit(ED_LIST_ONLY))
            .when(pl.col("ed_amount").is_null()).then(pl.lit(USASPENDING_ONLY))
            .when(pl.col("ed_amount").round(2) != pl.col("usaspending_amount")).then(pl.lit(AMOUNT_DIFFERENCE))
            .otherwise(None).alias("kind"),
            pl.lit(program).alias("program"),
            pl.lit(fy, dtype=pl.Int64).alias("fiscal_year"),
        )
        .filter(pl.col("kind").is_not_null())
        .select(list(EdListFainDifferences.to_schema().columns))
    )


def _ed_lists_vs_usaspending(
    inputs: ReconciliationInputs, tolerances: Tolerances, by_fain: pl.DataFrame
) -> tuple[list[dict], list[pl.DataFrame]]:
    """(c) ED grantee lists vs USAspending, exactly: TRIO every Grant by FAIN, GEAR UP new awards."""
    rows, differences = [], []
    new_awards = _usaspending_by_fy(inputs, inputs.grant_actions.filter(pl.col("action_type") == "A1"))
    for program in TRIO_PROGRAMS + GEAR_UP_PROGRAMS:
        trio = program in TRIO_PROGRAMS
        totals = by_fain if trio else new_awards
        compared_source = "USAspending obligations" if trio else "USAspending new awards (A1)"
        for fy in inputs.window.fiscal_years:
            dollars, count = _totals(totals, program, fy, ACTION_DATE)
            variant_dollars, variant_count = _totals(totals, program, fy, BUDGET_PERIOD)
            provisional = _provisional(inputs, fy, tolerances)
            filed, note = _list_coverage(inputs, program, fy)
            unavailable = None if filed else (NO_ED_LIST, note)
            listed = (inputs.ed_trio_list_rows if trio else inputs.ed_gearup_list_rows).filter(
                (pl.col("program") == program) & (pl.col("fiscal_year") == fy)
            )
            citations = [note]
            if filed and trio:
                found = _fain_differences(listed, by_fain, program, fy)
                differences.append(found)
                tally = {kind: found.filter(pl.col("kind") == kind).height
                         for kind in (ED_LIST_ONLY, USASPENDING_ONLY, AMOUNT_DIFFERENCE)}
                citations.append(
                    f"{tally[ED_LIST_ONLY]} on ED list only, {tally[USASPENDING_ONLY]} in USAspending only, "
                    f"{tally[AMOUNT_DIFFERENCE]} amount differences"
                )
            reference = round(float(listed["ed_amount"].sum()), 2) if filed else None
            rows.append(_compare(
                ED_LIST_DOLLARS, program, fy, "ED grantee list", compared_source, reference, dollars,
                variant_dollars, 0.0, provisional, citations, unavailable,
            ))
            rows.append(_compare(
                ED_LIST_COUNT, program, fy, "ED grantee list", compared_source,
                float(listed.height) if filed else None, float(count), float(variant_count), 0.0, provisional,
                citations, unavailable,
            ))
    return rows, differences


def count_unfunded_ed_list_evidence(inputs: ReconciliationInputs, tolerances: Tolerances) -> pl.DataFrame:
    """Count and share of unfunded Budget periods that an ED list shows as funded. Funding status is unchanged."""
    funded_on_list = inputs.ed_trio_list_rows.filter(pl.col("ed_amount") > 0).select(
        "fain", pl.col("fiscal_year").cast(pl.Int64).alias("list_year"), pl.lit(True).alias("evidence")
    ).unique()
    unfunded = (
        inputs.funding_status.filter(pl.col("funding_status") == UNFUNDED)
        .join(inputs.grants.select("fain", "program"), on="fain")
        .with_columns(pl.col("budget_period_start").dt.year().cast(pl.Int64).alias("list_year"))
        .join(funded_on_list, on=["fain", "list_year"], how="left")
        .with_columns(pl.col("evidence").fill_null(False))
    )
    per_program = (
        unfunded.group_by("program", pl.col("list_year").alias("fiscal_year"))
        .agg(pl.len().cast(pl.Int64).alias("unfunded_budget_periods"),
             pl.col("evidence").sum().cast(pl.Int64).alias("with_ed_list_evidence"))
        .with_columns((pl.col("with_ed_list_evidence") / pl.col("unfunded_budget_periods")).alias("share"))
        .with_columns((pl.col("share") > tolerances.evidence_large_share_program_fy).alias("large"))
        .select(list(UnfundedEdListEvidence.to_schema().columns))
        .sort("program", "fiscal_year")
    )
    total, evidence = unfunded.height, int(unfunded["evidence"].sum())
    share = evidence / total if total else None
    overall = pl.DataFrame(
        {"program": [ALL_PROGRAMS], "fiscal_year": [None], "unfunded_budget_periods": [total],
         "with_ed_list_evidence": [evidence], "share": [share],
         "large": [share is not None and share >= tolerances.evidence_large_share_overall]},
        schema=per_program.schema,
    )
    return check_schema(UnfundedEdListEvidence, pl.concat([per_program, overall]), "unfunded ED-list evidence")


def build_reconciliation(inputs: ReconciliationInputs, tolerances: Tolerances) -> ReconciliationResult:
    """Every check for every Program and reporting-window FY. A duplicate key stops the run."""
    by_fain = _usaspending_by_fy(inputs, inputs.grant_actions)
    list_rows, differences = _ed_lists_vs_usaspending(inputs, tolerances, by_fain)
    records = (
        _appropriation_vs_allocations(inputs) + _ed_allocations_vs_usaspending(inputs, tolerances, by_fain) + list_rows
    )
    columns = Reconciliation.to_schema().columns
    dtypes = {name: col.dtype.type for name, col in columns.items()}
    table = pl.DataFrame(records, schema=dtypes).select(list(columns)).sort("check", "program", "fiscal_year")
    check_unique(table, ["check", "program", "fiscal_year"], "reconciliation table")
    unlabelled = table.filter(
        (pl.col("reconciliation_status") != RECONCILED) & pl.col("gap_reason_code").is_null()
    )
    if unlabelled.height:
        raise StructuralBreak(f"{unlabelled.height} reconciliation rows differ without a Gap reason code")
    table = check_schema(Reconciliation, table, "reconciliation table")
    fain_differences = pl.concat(
        [pl.DataFrame(schema={n: c.dtype.type for n, c in EdListFainDifferences.to_schema().columns.items()}),
         *differences]
    ).sort("program", "fiscal_year", "fain")
    fain_differences = check_schema(EdListFainDifferences, fain_differences, "ED list FAIN differences")
    return ReconciliationResult(
        table=table,
        ed_list_fain_differences=fain_differences,
        unfunded_ed_list_evidence=count_unfunded_ed_list_evidence(inputs, tolerances),
    )
