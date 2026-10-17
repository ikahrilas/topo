"""TRIO and GEAR UP Programs, identified by assistance listing number plus FAIN prefix.

A Program is never identified by awarding agency: an ED Grant that DOL
administers carries the same listing and FAIN prefix and stays in.
Sub-programs that share a listing (Upward Bound, UBMS, VUB on 84.047; GEAR UP
partnership vs state on 84.334) are told apart only by the FAIN prefix.

DOL-style FAINs. Since the Nov. 2025 ED-DOL agreement, DOL ETA runs some TRIO
competitions for ED (FY2026 Talent Search and EOC). For ED programs it
administers, DOL reports as awarding agency under its own FAIN format (e.g.
`25E55EP000074` on 84.048), which carries no ED prefix. Such an action is
still a Grant of its listing's Program when the listing names exactly one
Program (84.042, 84.044, 84.066, 84.217). On a shared listing (84.047, 84.334)
a DOL FAIN can't name the sub-program, so it stays a visible exception. The
awarding agency only ever admits an action here; it never drops one.
Sources: docs/research/usaspending-trio-gearup.md (listings, prefixes),
docs/research/apr-data-and-fy2026-awards.md §2c (DOL FAINs and `_1601` awards).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TRIO = "TRIO"
GEAR_UP = "GEAR UP"


@dataclass(frozen=True)
class Program:
    name: str
    family: str  # TRIO or GEAR UP
    listing: str  # assistance listing number, e.g. "84.047"
    fain_prefix: str  # first five FAIN characters, e.g. "P047M"


PROGRAMS: tuple[Program, ...] = (
    Program("Student Support Services", TRIO, "84.042", "P042A"),
    Program("Talent Search", TRIO, "84.044", "P044A"),
    Program("Upward Bound", TRIO, "84.047", "P047A"),
    Program("Upward Bound Math and Science", TRIO, "84.047", "P047M"),
    Program("Veterans Upward Bound", TRIO, "84.047", "P047V"),
    Program("Educational Opportunity Centers", TRIO, "84.066", "P066A"),
    Program("McNair", TRIO, "84.217", "P217A"),
    Program("GEAR UP partnership", GEAR_UP, "84.334", "P334A"),
    Program("GEAR UP state", GEAR_UP, "84.334", "P334S"),
)

LISTINGS: tuple[str, ...] = tuple(sorted({p.listing for p in PROGRAMS}))
FAIN_PREFIX_LENGTH = 5
DOL_AGENCY_CODE = "1601"  # USAspending toptier code of the Department of Labor
# ED FAINs open with an office letter, the 3-digit listing and a sub-program letter (P047M...).
ED_FAIN_PATTERN = r"^[A-Z][0-9]{3}[A-Z]"
# Listings that name exactly one Program: listing -> Program.
SOLE_PROGRAM_OF_LISTING: dict[str, Program] = {
    listing: matches[0]
    for listing in LISTINGS
    if len(matches := [p for p in PROGRAMS if p.listing == listing]) == 1
}


def is_dol_style(fain: str, awarding_agency_code: str | None) -> bool:
    """A FAIN DOL issued (DOL awarding, no ED FAIN format)."""
    return awarding_agency_code == DOL_AGENCY_CODE and re.match(ED_FAIN_PATTERN, fain.upper()) is None


def program_for(listing: str, fain: str, awarding_agency_code: str | None = None) -> Program | None:
    """The Program of a funding action, or None when listing and FAIN don't name one."""
    prefix = fain[:FAIN_PREFIX_LENGTH].upper()
    for program in PROGRAMS:
        if program.listing == listing and program.fain_prefix == prefix:
            return program
    if is_dol_style(fain, awarding_agency_code):
        return SOLE_PROGRAM_OF_LISTING.get(listing)
    return None
