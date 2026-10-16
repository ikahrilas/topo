"""Hand-built FAC bulk CSV fixtures (federal_awards.csv, general.csv).

Only the columns given are filled; every other column is written blank, including
the auditee contact columns (names, emails, phones) that the pipeline must never ingest.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
from support.ipeds import write_csv

FEDERAL_AWARDS_CSV = "federal_awards.csv"
GENERAL_CSV = "general.csv"

# Bulk federal_awards.csv columns (subset, in FAC order).
FEDERAL_AWARDS_COLUMNS = [
    "report_id", "auditee_uei", "audit_year", "fac_accepted_date", "award_reference",
    "federal_agency_prefix", "federal_award_extension", "additional_award_identification",
    "federal_program_name", "amount_expended", "cluster_name", "federal_program_total", "cluster_total",
    "is_major", "is_loan", "is_direct", "findings_count", "is_passthrough_award", "passthrough_amount",
]

# Bulk general.csv columns (subset), including the contact PII the clean must drop.
GENERAL_COLUMNS = [
    "report_id", "auditee_uei", "auditee_ein", "auditee_name", "auditee_address_line_1", "auditee_city",
    "auditee_state", "auditee_zip", "auditee_contact_name", "auditee_email", "auditee_phone",
    "entity_type", "audit_year", "fy_start_date", "fy_end_date", "total_amount_expended", "is_public",
    "data_source",
]


def award_line(
    uei: str, audit_year: int, extension: str, amount: int, *, is_direct: str = "Y", prefix: str = "84",
    report_id: str | None = None, reference: str = "AWARD-0001",
) -> dict[str, str]:
    """One SEFA line of a FAC audit report."""
    return {
        "report_id": report_id or f"{audit_year}-06-GSAFAC-{uei}",
        "auditee_uei": uei,
        "audit_year": str(audit_year),
        "fac_accepted_date": f"{audit_year + 1}-03-01",
        "award_reference": reference,
        "federal_agency_prefix": prefix,
        "federal_award_extension": extension,
        "federal_program_name": "TRIO FIXTURE PROGRAM",
        "amount_expended": str(amount),
        "is_direct": is_direct,
    }


def audit(uei: str, audit_year: int, name: str, state: str = "FL", report_id: str | None = None) -> dict[str, str]:
    """One FAC audit report (general.csv row)."""
    return {
        "report_id": report_id or f"{audit_year}-06-GSAFAC-{uei}",
        "auditee_uei": uei,
        "auditee_ein": "123456789",
        "auditee_name": name,
        "auditee_city": "TAMPA",
        "auditee_state": state,
        "auditee_contact_name": "Pat Example",
        "auditee_email": "pat@example.edu",
        "auditee_phone": "8135550100",
        "entity_type": "higher-ed",
        "audit_year": str(audit_year),
        "fy_start_date": f"{audit_year - 1}-07-01",
        "fy_end_date": f"{audit_year}-06-30",
        "total_amount_expended": "90000000",
        "is_public": "true",
        "data_source": "GSAFAC",
    }


def write_fac(root: Path, pull_date: str, lines: list[dict[str, str]], audits: list[dict[str, str]] | None = None) -> Path:
    """Write both bulk CSVs into data/raw/fac/<Pull date>/; audits default to one per line's report."""
    folder = root / "data" / "raw" / "fac" / pull_date
    if audits is None:
        seen: dict[str, dict[str, str]] = {}
        for line in lines:
            seen.setdefault(line["report_id"], audit(line["auditee_uei"], int(line["audit_year"]), "FIXTURE AUDITEE",
                                                     report_id=line["report_id"]))
        audits = list(seen.values())
    write_csv(folder / FEDERAL_AWARDS_CSV, FEDERAL_AWARDS_COLUMNS, lines)
    write_csv(folder / GENERAL_CSV, GENERAL_COLUMNS, audits)
    return folder


def cleaned_audits(*auditees: tuple[str, str, str], audit_year: int = 2024) -> pl.DataFrame:
    """A cleaned `fac_audits` frame: one audit per (auditee UEI, auditee name, auditee state)."""
    return pl.DataFrame(
        [
            {"report_id": f"{audit_year}-06-GSAFAC-{uei}", "auditee_uei": uei, "auditee_name": name,
             "auditee_state": state, "entity_type": "higher-ed", "audit_year": audit_year,
             "fy_start_date": dt.date(audit_year - 1, 7, 1), "fy_end_date": dt.date(audit_year, 6, 30),
             "raw_file": "general.csv", "pull_date": dt.date(2026, 10, 7)}
            for uei, name, state in auditees
        ],
        schema={"report_id": pl.String, "auditee_uei": pl.String, "auditee_name": pl.String,
                "auditee_state": pl.String, "entity_type": pl.String, "audit_year": pl.Int64,
                "fy_start_date": pl.Date, "fy_end_date": pl.Date, "raw_file": pl.String, "pull_date": pl.Date},
    )
