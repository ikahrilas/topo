"""TRIO and GEAR UP Programs, identified by assistance listing number plus FAIN prefix.

A Program is never identified by awarding agency: an ED Grant that DOL
administers carries the same listing and FAIN prefix and stays in.
Sub-programs that share a listing (Upward Bound, UBMS, VUB on 84.047; GEAR UP
partnership vs state on 84.334) are told apart only by the FAIN prefix.
Sources: docs/research/usaspending-trio-gearup.md (listings, prefixes).
"""

from __future__ import annotations

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


def program_for(listing: str, fain: str) -> Program | None:
    """The Program of a funding action, or None when listing and FAIN prefix don't name one."""
    prefix = fain[:FAIN_PREFIX_LENGTH].upper()
    for program in PROGRAMS:
        if program.listing == listing and program.fain_prefix == prefix:
            return program
    return None
