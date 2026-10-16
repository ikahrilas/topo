"""Curated appropriation and ED per-program allocation files (data/curated/), as the maintainer files them."""

from __future__ import annotations

import csv
from pathlib import Path

APPROPRIATION_COLUMNS = ["program_family", "fiscal_year", "amount_usd", "citation", "note"]
ALLOCATION_COLUMNS = ["program", "fiscal_year", "allocation_usd", "award_count", "citation", "note"]

ED_BUDGET = "ED, FY 2023 Congressional Action (Excel, Jan. 27, 2023)"
ED_HISTORY = "ED program page, Funding History tab"

# docs/research/trio-gearup-funding-and-cycles.md §1a and §1b (whole dollars).
TRIO_APPROPRIATIONS = {2021: 1_097_000_000, 2022: 1_137_000_000, 2023: 1_191_000_000, 2024: 1_191_000_000}
TRIO_ALLOCATIONS = {
    "Student Support Services": {2021: 363_222_465, 2022: 367_195_716, 2023: 380_816_215, 2024: 379_616_682},
    "Talent Search": {2021: 184_987_311, 2022: 190_437_025, 2023: 195_115_784, 2024: 196_166_197},
    "Upward Bound": {2021: 335_817_182, 2022: 366_203_750, 2023: 380_199_608, 2024: 379_875_608},
    "Upward Bound Math and Science": {2021: 64_843_908, 2022: 73_699_494, 2023: 79_055_767, 2024: 79_381_834},
    "Veterans Upward Bound": {2021: 18_815_149, 2022: 20_557_756, 2023: 22_066_756, 2024: 22_253_222},
    "Educational Opportunity Centers": {2021: 61_412_887, 2022: 63_886_164, 2023: 63_934_646, 2024: 65_096_897},
    "McNair": {2021: 49_824_230, 2022: 56_378_254, 2023: 60_801_067, 2024: 60_166_049},
}


def appropriation(fy: int, amount: float, family: str = "TRIO", note: str = "") -> dict[str, str]:
    return {"program_family": family, "fiscal_year": str(fy), "amount_usd": str(amount), "citation": ED_BUDGET,
            "note": note}


def allocation(program: str, fy: int, dollars: float | None, count: int | None = None, note: str = "") -> dict[str, str]:
    return {"program": program, "fiscal_year": str(fy), "allocation_usd": "" if dollars is None else str(dollars),
            "award_count": "" if count is None else str(count), "citation": ED_HISTORY, "note": note}


def research_figures() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """The TRIO appropriations and allocations FY2021-24 from the research notes."""
    appropriations = [appropriation(fy, amount) for fy, amount in TRIO_APPROPRIATIONS.items()]
    allocations = [
        allocation(program, fy, dollars) for program, by_fy in TRIO_ALLOCATIONS.items() for fy, dollars in by_fy.items()
    ]
    return appropriations, allocations


def _write(path: Path, columns: list[str], rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_curated(root: Path, appropriations: list[dict[str, str]], allocations: list[dict[str, str]]) -> None:
    curated = root / "data" / "curated"
    _write(curated / "appropriations.csv", APPROPRIATION_COLUMNS, appropriations)
    _write(curated / "ed_program_allocations.csv", ALLOCATION_COLUMNS, allocations)
