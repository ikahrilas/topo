"""Hand-built USAspending Award Data Archive fixtures.

A fixture row is one funding action (transaction). Only the columns given are
filled; every other archive column is written blank, including the DUNS and
highly-compensated-officer columns that the pipeline must never ingest.
"""

from __future__ import annotations

import csv
from pathlib import Path

# Archive column header, in archive order (FY2024 ED Assistance_Full file).
ARCHIVE_COLUMNS = [
    "assistance_transaction_unique_key", "assistance_award_unique_key", "award_id_fain",
    "modification_number", "award_id_uri", "sai_number", "federal_action_obligation",
    "total_obligated_amount", "total_outlayed_amount_for_overall_award", "action_date",
    "action_date_fiscal_year", "period_of_performance_start_date",
    "period_of_performance_current_end_date", "awarding_agency_code", "awarding_agency_name",
    "awarding_sub_agency_code", "awarding_sub_agency_name", "funding_agency_code",
    "funding_agency_name", "recipient_uei", "recipient_duns", "recipient_name",
    "recipient_name_raw", "recipient_parent_uei", "recipient_parent_duns", "recipient_parent_name",
    "recipient_address_line_1", "recipient_city_name", "recipient_state_code",
    "recipient_zip_code", "primary_place_of_performance_state_name", "cfda_number", "cfda_title",
    "transaction_description", "prime_award_base_transaction_description",
    "business_types_description", "action_type_code", "action_type_description",
    "record_type_code", "highly_compensated_officer_1_name", "highly_compensated_officer_1_amount",
    "usaspending_permalink", "initial_report_date", "last_modified_date",
]

AGENCY_NAMES = {"091": "Department of Education", "1601": "Department of Labor"}


def action(
    fain: str,
    mod: int,
    action_date: str,
    amount: float,
    budget_period: tuple[str, str],
    *,
    listing: str | None = None,
    action_type: str = "B1",
    recipient: str = "UNIVERSITY OF SOUTH FLORIDA",
    uei: str = "NKAZLXLL7Z91",
    state: str = "FL",
    agency: str = "091",
    **extra: str,
) -> dict[str, str]:
    """One funding action as an archive row."""
    year, month = int(action_date[:4]), int(action_date[5:7])
    fy = year + 1 if month >= 10 else year
    listing = listing or f"84.{fain[1:4]}"
    row = {
        "assistance_transaction_unique_key": f"{agency}00_{fain}_-NONE-_{listing}_{mod}",
        "assistance_award_unique_key": f"ASST_NON_{fain}_{agency}",
        "award_id_fain": fain,
        "modification_number": str(mod),
        "federal_action_obligation": f"{amount:.2f}",
        "action_date": action_date,
        "action_date_fiscal_year": str(fy),
        "period_of_performance_start_date": budget_period[0],
        "period_of_performance_current_end_date": budget_period[1],
        "awarding_agency_code": agency,
        "awarding_agency_name": AGENCY_NAMES.get(agency, agency),
        "funding_agency_code": agency,
        "funding_agency_name": AGENCY_NAMES.get(agency, agency),
        "recipient_uei": uei,
        "recipient_duns": "069687242",
        "recipient_parent_duns": "069687242",
        "recipient_name": recipient,
        "recipient_name_raw": recipient,
        "recipient_city_name": "TAMPA",
        "recipient_state_code": state,
        "cfda_number": listing,
        "cfda_title": "FIXTURE LISTING",
        "transaction_description": f"{recipient} PROJECT",
        "prime_award_base_transaction_description": f"{recipient} PROJECT",
        "action_type_code": action_type,
        "action_type_description": {"A1": "New Award", "B1": "Continuation"}.get(action_type, "Other"),
        "record_type_code": "2",
        "highly_compensated_officer_1_name": "JANE DOE",
        "highly_compensated_officer_1_amount": "250000",
        "total_obligated_amount": "99999999.00",
    }
    row.update(extra)
    return row


def write_archive(raw_usaspending: Path, pull_date: str, fy: int, rows: list[dict], agency: str = "091") -> Path:
    """Write one fiscal year's archive CSV into data/raw/usaspending/<pull_date>/."""
    folder = raw_usaspending / pull_date
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"FY{fy}_{agency}_Assistance_Full_{pull_date.replace('-', '')}_1.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ARCHIVE_COLUMNS, restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def write_actions(raw_usaspending: Path, pull_date: str, rows: list[dict]) -> None:
    """Split actions into per-(FY, agency) archive files, as the real archive is laid out."""
    groups: dict[tuple[int, str], list[dict]] = {}
    for row in rows:
        key = (int(row["action_date_fiscal_year"]), row["awarding_agency_code"])
        groups.setdefault(key, []).append(row)
    for (fy, agency), group in sorted(groups.items()):
        write_archive(raw_usaspending, pull_date, fy, group, agency)
