"""Host linking: a deterministic rule cascade from a Grant to its Host institution (ADR 0002).

`link_host(grant, lookups)` is pure: one Grant's facts plus lookup tables in,
one HostLink out. The outcome is one of

    matched          one Host (UNITID or LEAID)
    no_single_host   decided by rule to have no one Host (GEAR UP State, a
                     statewide agency, a nonprofit naming no site)
    review           candidates found; a person must choose
    unmatched        no candidate found (carries no candidates)

and the Case label names the rule that decided it. No numeric score.

Rules in this module (#32): Recipient UEI -> IPEDS `ueis` and Recipient name ->
IPEDS names (every name since `directory_from_year`, plus `inst_alias`), both
restricted to the Recipient's state; IPEDS system offices (sector 0) never beat
a real campus; the No single Host rules. Later tickets add the ED list name,
award-description phrases, campus words, address tiebreaks, IPEDS merges
(#35) and districts from CCD (#36). Case labels follow the prototype taxonomy
(prototypes/host-linking/README.md).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

import polars as pl

MATCHED = "matched"
NO_SINGLE_HOST = "no_single_host"
REVIEW = "review"
UNMATCHED = "unmatched"

# The target list's Host confidence column, by outcome.
HOST_CONFIDENCE = {
    MATCHED: "matched",
    NO_SINGLE_HOST: "lower-confidence: no single Host",
    REVIEW: "in review",
    UNMATCHED: "unmatched",
}

UNITID = "UNITID"
LEAID = "LEAID"
SYSTEM_OFFICE_SECTOR = 0
GEAR_UP_STATE_PREFIX = "P334S"
GEAR_UP_PARTNERSHIP_PREFIX = "P334A"

# Recipient kinds (from USAspending business types, then the name).
IHE, AUX, LEA, STATE, NONPROFIT = "IHE", "AUX", "LEA", "STATE", "NP"

# ------------------------------------------------------------------- text

_ABBREV = {
    "UNIV": "UNIVERSITY", "U": "UNIVERSITY", "COL": "COLLEGE", "COLL": "COLLEGE", "CC": "COMMUNITY COLLEGE",
    "CMTY": "COMMUNITY", "COMM": "COMMUNITY", "TECH": "TECHNICAL", "ST": "STATE", "INST": "INSTITUTE",
    "SAINT": "ST", "MT": "MOUNT", "CTR": "CENTER", "DIST": "DISTRICT",
}
_DROP = {"THE", "INC", "INCORPORATED", "AND", "OF", "AT", "IN", "FOR", "ON", "A"}


def _norm(text: str | None) -> str:
    """Uppercase, punctuation to spaces, 'X UNIV OF' -> 'UNIVERSITY OF X'."""
    if not text:
        return ""
    s = text.upper().replace("&", " AND ").replace("'", "")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"^(.*) (UNIV|UNIVERSITY) OF$", s)
    return f"UNIVERSITY OF {m.group(1)}" if m else s


def name_key(text: str | None) -> str:
    """Comparable form of an institution name: abbreviations expanded, filler words dropped."""
    out: list[str] = []
    for token in _norm(text).split():
        out.extend(t for t in _ABBREV.get(token, token).split() if t not in _DROP)
    return " ".join(out)


_COLLEGEY = re.compile(r"\b(COLLEGE|UNIVERSITY|UNIV|INSTITUTE OF TECHNOLOGY|COMMUNITY COLLEGE|REGENTS|POLYTECHNIC|SEMINARY)\b")
_AUX = re.compile(r"\b(FOUNDATION|RESEARCH CORPORATION|RESEARCH FOUNDATION|CORPORATION|CENTER FOR RESEARCH|AUXILIARY)\b")
_LEAY = re.compile(
    r"\b(SCHOOL DISTRICT|PUBLIC SCHOOLS|SCHOOL BOARD|BOARD OF EDUCATION|ISD|USD|CITY SCHOOLS|COUNTY SCHOOLS|"
    r"SCHOOL CORP|COMMUNITY SCHOOLS|INTERMEDIATE UNIT|EDUCATION SERVICE|EDUCATION SRV|EDUCATIONAL SERVICE|"
    r"COUNTY OFFICE OF EDUCATION|DEPARTMENT OF EDUCATION|COOPERATIVE EDUCATIONAL|COLLEGE PREP)\b"
)


def recipient_kind(business_types: str | None, recipient_name: str | None) -> str:
    """College, college auxiliary, district, state agency or nonprofit (prototype rules)."""
    bt, name = (business_types or "").upper(), _norm(recipient_name)
    if "INSTITUTION OF HIGHER EDUCATION" in bt and "OTHER THAN" not in bt:
        return IHE
    if "NONPROFIT" in bt or "PROFIT" in bt or "SMALL BUSINESS" in bt:
        # 'College Now' and 'University Settlement' are nonprofits; a college's foundation is an auxiliary
        return AUX if _AUX.search(name) and _COLLEGEY.search(name) else NONPROFIT
    if _LEAY.search(name):
        return LEA
    if _COLLEGEY.search(name):  # SAM registers many community college districts as school districts
        return AUX if _AUX.search(name) else IHE
    if "SCHOOL DISTRICT" in bt:
        return LEA
    if "STATE GOVERNMENT" in bt:
        return STATE
    return NONPROFIT


# ---------------------------------------------------------------- lookups


@dataclass(frozen=True)
class IpedsUnit:
    unitid: str
    name: str  # latest name
    state: str | None
    sector: int | None
    names: frozenset[str]  # name keys: every name since directory_from_year, plus aliases
    ueis: frozenset[str]

    @property
    def is_system_office(self) -> bool:
        return self.sector == SYSTEM_OFFICE_SECTOR


def _split(values: str | None) -> list[str]:
    return [v.strip() for v in (values or "").split("|") if v.strip()]


@dataclass(frozen=True)
class HostLookups:
    """Lookup tables the linker reads, indexed by state so no signal crosses a state line."""

    units: dict[str, IpedsUnit]
    _by_uei: dict[tuple[str, str], frozenset[str]] = field(repr=False)
    _by_name: dict[tuple[str, str], frozenset[str]] = field(repr=False)

    @classmethod
    def from_directory(cls, directory: pl.DataFrame) -> "HostLookups":
        """Build from the cleaned IPEDS directory history (topo.sources.ipeds)."""
        rows = directory.sort("unitid", "year").iter_rows(named=True)
        latest: dict[str, dict] = {}
        names: dict[str, set[str]] = defaultdict(set)
        ueis: dict[str, set[str]] = defaultdict(set)
        for r in rows:
            uid = r["unitid"]
            latest[uid] = r
            names[uid] |= {name_key(n) for n in [r["inst_name"], *_split(r["inst_alias"])] if name_key(n)}
            ueis[uid] |= set(_split(r["ueis"]))
        units = {
            uid: IpedsUnit(uid, r["inst_name"], r["state_abbr"], r["sector"], frozenset(names[uid]), frozenset(ueis[uid]))
            for uid, r in latest.items()
        }
        by_uei: dict[tuple[str, str], set[str]] = defaultdict(set)
        by_name: dict[tuple[str, str], set[str]] = defaultdict(set)
        for uid, unit in units.items():
            if unit.state is None:
                continue
            for uei in unit.ueis:
                by_uei[(unit.state, uei)].add(uid)
            for key in unit.names:
                by_name[(unit.state, key)].add(uid)
        return cls(
            units,
            {k: frozenset(v) for k, v in by_uei.items()},
            {k: frozenset(v) for k, v in by_name.items()},
        )

    def units_by_uei(self, state: str, uei: str | None) -> frozenset[str]:
        return self._by_uei.get((state, uei), frozenset()) if uei else frozenset()

    def units_by_name(self, state: str, name: str | None) -> frozenset[str]:
        key = name_key(name)
        return self._by_name.get((state, key), frozenset()) if key else frozenset()


# ----------------------------------------------------------------- linker


@dataclass(frozen=True)
class GrantFacts:
    """What the linker knows about one Grant (from its latest USAspending action)."""

    fain: str
    recipient_name: str | None
    recipient_uei: str | None
    recipient_state: str | None
    business_types: str | None = None

    @property
    def fain_prefix(self) -> str:
        return self.fain[:5]


@dataclass(frozen=True)
class Candidate:
    host_kind: str  # UNITID or LEAID
    host_id: str
    host_name: str
    signals: tuple[str, ...]  # sorted signal names, e.g. ("name", "uei")


@dataclass(frozen=True)
class HostLink:
    fain: str
    outcome: str
    case_label: str
    host_kind: str | None = None
    host_id: str | None = None
    host_name: str | None = None
    candidates: tuple[Candidate, ...] = ()

    @property
    def host_confidence(self) -> str:
        return HOST_CONFIDENCE[self.outcome]


def _college_signals(grant: GrantFacts, lookups: HostLookups) -> dict[str, set[str]]:
    """UNITID -> signals, same state only. A Grant with no state has no candidates."""
    state = grant.recipient_state
    signals: dict[str, set[str]] = defaultdict(set)
    if not state:
        return signals
    for uid in lookups.units_by_uei(state, grant.recipient_uei):
        signals[uid].add("uei")
    for uid in lookups.units_by_name(state, grant.recipient_name):
        signals[uid].add("name")
    if any(not lookups.units[uid].is_system_office for uid in signals):
        for uid in [uid for uid in signals if lookups.units[uid].is_system_office]:
            del signals[uid]
    return signals


def link_host(grant: GrantFacts, lookups: HostLookups) -> HostLink:
    """Link one Grant to its Host institution. Pure: no I/O, no clock."""
    kind = recipient_kind(grant.business_types, grant.recipient_name)
    colleges = _college_signals(grant, lookups)
    if grant.fain_prefix == GEAR_UP_PARTNERSHIP_PREFIX:
        colleges = {}  # partnerships serve district cohorts; the college partner is never the Host

    candidates = tuple(
        Candidate(UNITID, uid, lookups.units[uid].name, tuple(sorted(sig)))
        for uid, sig in sorted(colleges.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    def result(outcome: str, case_label: str, pick: str | None = None) -> HostLink:
        return HostLink(
            fain=grant.fain,
            outcome=outcome,
            case_label=case_label,
            host_kind=UNITID if pick else None,
            host_id=pick,
            host_name=lookups.units[pick].name if pick else None,
            candidates=() if outcome == UNMATCHED else candidates,
        )

    if grant.fain_prefix == GEAR_UP_STATE_PREFIX:
        return result(NO_SINGLE_HOST, "gearup_state")
    if kind == STATE:
        return result(NO_SINGLE_HOST, "state_agency_no_site_named")

    if len(colleges) == 1:
        ((uid, sig),) = colleges.items()
        if sig == {"uei", "name"}:
            return result(MATCHED, "uei_confirmed", uid)
        if lookups.units[uid].is_system_office:
            return result(REVIEW, "only_candidate_is_system_office", uid)
        if sig == {"uei"}:
            if kind in (IHE, AUX):
                return result(MATCHED, "uei_only", uid)
            return result(REVIEW, "uei_only_non_college", uid)
        return result(REVIEW, "single_weak_signal:" + "+".join(sorted(sig)), uid)
    if colleges:
        by_uei = [uid for uid, sig in colleges.items() if "uei" in sig]
        if len(by_uei) == 1:
            return result(REVIEW, "uei_vs_name_conflict", by_uei[0])
        return result(REVIEW, "system_campus_not_stated")

    if grant.fain_prefix == GEAR_UP_PARTNERSHIP_PREFIX:
        # Districts are not looked up yet (#36), so "names no district" can't be decided here.
        return result(UNMATCHED, "no_candidate_gearup_partnership")
    if kind == NONPROFIT:
        return result(NO_SINGLE_HOST, "nonprofit_no_site_named")
    return result(UNMATCHED, f"no_candidate_{kind.lower()}")
