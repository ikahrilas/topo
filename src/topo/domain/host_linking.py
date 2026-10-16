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
a real campus; the No single Host rules. GEAR UP partnerships (#36) link only
to districts (CCD LEAIDs) named by the Recipient itself or the award
descriptions, never to the college partner. Later tickets add the ED list
name, award-description phrases for colleges, campus words, address
tiebreaks and IPEDS merges (#35). Case labels follow the prototype taxonomy
(prototypes/host-linking/README.md).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

import pandera.polars as pa
import polars as pl

from topo.guards import StructuralBreak, check_schema

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


# District name forms (host-linking prototype): a district is named by its core
# name plus any of these forms ("SOCORRO ISD", "OGDEN CITY SCHOOL DISTRICT").
_LEA_SUFFIX = re.compile(
    r"\b(INDEPENDENT SCHOOL DISTRICT|UNIFIED SCHOOL DISTRICT|CONSOLIDATED SCHOOL DISTRICT|SCHOOL DISTRICT|"
    r"PUBLIC SCHOOLS|CITY SCHOOLS|COUNTY SCHOOLS|SCHOOLS|SCHOOL CORPORATION|DISTRICT|ISD|USD|CISD|CSD|SD)"
    r"( NO \d+| \d+)?$"
)
_LEA_PREFIX = re.compile(r"^(BOARD OF EDUCATION OF (THE )?|SCHOOL DISTRICT OF (THE )?|SCHOOL BOARD OF )")
_LEA_TAIL = re.compile(r" (BOARD OF EDUCATION|SCHOOL BOARD|CITY SCHOOL BOARD|COUNTY SCHOOL BOARD)$")
_LEA_PLACE_WORD = re.compile(r" (CITY|COUNTY|AREA|COMMUNITY|PUBLIC|MUNICIPAL|UNIFIED|JOINT|CONSOLIDATED)$")
LEA_FORMS = (
    "SCHOOL DISTRICT", "SCHOOLS", "PUBLIC SCHOOLS", "INDEPENDENT SCHOOL DISTRICT", "ISD", "UNIFIED SCHOOL DISTRICT",
    "USD", "CITY SCHOOLS", "CITY SCHOOL DISTRICT", "COUNTY SCHOOLS", "COUNTY SCHOOL DISTRICT", "SCHOOL CORPORATION",
    "COMMUNITY SCHOOLS", "AREA SCHOOL DISTRICT", "SCHOOL BOARD", "BOARD OF EDUCATION",
)


def lea_core(name: str | None) -> str:
    """A district's core name: 'BOARD OF EDUCATION OF OGDEN CITY' -> 'OGDEN', 'Socorro ISD' -> 'SOCORRO'."""
    s = _norm(name).replace("METRO ", "METROPOLITAN ")
    s = _LEA_PREFIX.sub("", s)
    s = _LEA_TAIL.sub("", s)
    s = _LEA_SUFFIX.sub("", s).strip()
    return _LEA_PLACE_WORD.sub("", s).strip()


def _phrase(text: str) -> tuple[str, ...]:
    return tuple(name_key(text).split())


@dataclass(frozen=True)
class District:
    leaid: str
    name: str  # latest name
    state: str | None
    phrases: frozenset[tuple[str, ...]]  # name-key token phrases that name it (two tokens or more)
    cores: frozenset[str]  # core names, for a Recipient that is the district itself


def _districts(lea_directory: pl.DataFrame) -> dict[str, District]:
    latest: dict[str, dict] = {}
    names: dict[str, set[str]] = defaultdict(set)
    for r in lea_directory.sort("leaid", "year").iter_rows(named=True):
        latest[r["leaid"]] = r
        names[r["leaid"]].add(r["lea_name"])
    districts = {}
    for leaid, r in latest.items():
        phrases: set[tuple[str, ...]] = set()
        cores = {lea_core(n) for n in names[leaid]} - {""}
        for n in names[leaid]:
            phrases.add(_phrase(n))
        for core in cores:
            phrases |= {_phrase(f"{core} {form}") for form in LEA_FORMS}
        districts[leaid] = District(
            leaid, r["lea_name"], r["state_location"],
            frozenset(p for p in phrases if len(p) >= 2), frozenset(cores),
        )
    return districts


@dataclass(frozen=True)
class HostLookups:
    """Lookup tables the linker reads, indexed by state so no signal crosses a state line."""

    units: dict[str, IpedsUnit]
    _by_uei: dict[tuple[str, str], frozenset[str]] = field(repr=False)
    _by_name: dict[tuple[str, str], frozenset[str]] = field(repr=False)
    districts: dict[str, District] = field(default_factory=dict)
    _district_by_phrase: dict[tuple[str, tuple[str, ...]], frozenset[str]] = field(default_factory=dict, repr=False)
    _district_by_core: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict, repr=False)

    @classmethod
    def from_directory(cls, directory: pl.DataFrame, lea_directory: pl.DataFrame | None = None) -> "HostLookups":
        """Build from the cleaned IPEDS directory history (topo.sources.ipeds) and, for
        district Hosts, the cleaned CCD LEA directory history (topo.sources.ccd)."""
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
        districts = _districts(lea_directory) if lea_directory is not None else {}
        by_phrase: dict[tuple[str, tuple[str, ...]], set[str]] = defaultdict(set)
        by_core: dict[tuple[str, str], set[str]] = defaultdict(set)
        for leaid, district in districts.items():
            if district.state is None:
                continue
            for phrase in district.phrases:
                by_phrase[(district.state, phrase)].add(leaid)
            for core in district.cores:
                by_core[(district.state, core)].add(leaid)
        return cls(
            units,
            {k: frozenset(v) for k, v in by_uei.items()},
            {k: frozenset(v) for k, v in by_name.items()},
            districts,
            {k: frozenset(v) for k, v in by_phrase.items()},
            {k: frozenset(v) for k, v in by_core.items()},
        )

    def units_by_uei(self, state: str, uei: str | None) -> frozenset[str]:
        return self._by_uei.get((state, uei), frozenset()) if uei else frozenset()

    def units_by_name(self, state: str, name: str | None) -> frozenset[str]:
        key = name_key(name)
        return self._by_name.get((state, key), frozenset()) if key else frozenset()

    def districts_by_core(self, state: str, recipient_name: str | None) -> frozenset[str]:
        """Districts whose core name equals the Recipient's (the Recipient is the district)."""
        core = lea_core(recipient_name)
        return self._district_by_core.get((state, core), frozenset()) if core else frozenset()

    def districts_named_in(self, state: str, text: str | None) -> list[frozenset[str]]:
        """Each district mention in the text: the same-state LEAIDs it names (more than one = ambiguous).

        A mention nested inside a longer mention is dropped ('KANSAS CITY PUBLIC SCHOOLS'
        is not also 'CITY PUBLIC SCHOOLS')."""
        tokens = _phrase(text or "")
        spans = []
        for i in range(len(tokens)):
            for j in range(len(tokens), i + 1, -1):
                hit = self._district_by_phrase.get((state, tokens[i:j]))
                if hit:
                    spans.append((i, j, hit))
                    break
        return [
            hit for i, j, hit in spans
            if not any(a <= i and j <= b and (b - a) > (j - i) for a, b, _ in spans)
        ]


# ----------------------------------------------------------------- linker


@dataclass(frozen=True)
class GrantFacts:
    """What the linker knows about one Grant (from its latest USAspending action)."""

    fain: str
    recipient_name: str | None
    recipient_uei: str | None
    recipient_state: str | None
    business_types: str | None = None
    descriptions: tuple[str, ...] = ()  # the Grant's distinct award descriptions

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
    if grant.fain_prefix == GEAR_UP_PARTNERSHIP_PREFIX:
        return _link_gear_up_partnership(grant, kind, lookups)
    colleges = _college_signals(grant, lookups)

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

    if kind == NONPROFIT:
        return result(NO_SINGLE_HOST, "nonprofit_no_site_named")
    return result(UNMATCHED, f"no_candidate_{kind.lower()}")


def _link_gear_up_partnership(grant: GrantFacts, kind: str, lookups: HostLookups) -> HostLink:
    """GEAR UP partnership (P334A): the Host is the district served, never the college partner.

    A district is named when the Recipient is the district itself (`name`: same core
    name, Recipient kind LEA) or an award description names it (`desc`). Same state only.
    One district named -> matched; several -> no single Host; none -> no single Host;
    a mention that fits several same-state districts -> review.
    """
    state = grant.recipient_state
    signals: dict[str, set[str]] = defaultdict(set)
    mentions: list[frozenset[str]] = []
    if state:
        if kind == LEA:
            named = lookups.districts_by_core(state, grant.recipient_name)
            if named:
                mentions.append(named)
            for leaid in named:
                signals[leaid].add("name")
        for description in grant.descriptions:
            for named in lookups.districts_named_in(state, description):
                mentions.append(named)
                for leaid in named:
                    signals[leaid].add("desc")

    candidates = tuple(
        Candidate(LEAID, leaid, lookups.districts[leaid].name, tuple(sorted(sig)))
        for leaid, sig in sorted(signals.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    def result(outcome: str, case_label: str, pick: str | None = None) -> HostLink:
        return HostLink(
            fain=grant.fain, outcome=outcome, case_label=case_label,
            host_kind=LEAID if pick else None, host_id=pick,
            host_name=lookups.districts[pick].name if pick else None,
            candidates=candidates,
        )

    if not mentions:
        return result(NO_SINGLE_HOST, "gearup_partnership_no_district_named")
    named_once = {leaid for named in mentions if len(named) == 1 for leaid in named}
    if len(named_once) > 1:
        return result(NO_SINGLE_HOST, "several_districts_named")
    if len(named_once) == 1:
        (leaid,) = named_once
        if all(leaid in named for named in mentions):
            label = "district_is_recipient" if "name" in signals[leaid] else "district_named_in_desc"
            return result(MATCHED, label, leaid)
    return result(REVIEW, "district_name_ambiguous")


# ------------------------------------------------------------ joined tables


class HostLinks(pa.DataFrameModel):
    """One Host link per Grant (FAIN): every outcome, none dropped."""

    fain: str = pa.Field(unique=True)
    outcome: str = pa.Field(isin=list(HOST_CONFIDENCE))
    case_label: str
    host_kind: str = pa.Field(nullable=True, isin=[UNITID, LEAID])
    host_id: str = pa.Field(nullable=True)
    host_name: str = pa.Field(nullable=True)
    host_confidence: str = pa.Field(isin=list(HOST_CONFIDENCE.values()))

    class Config:
        strict = True


class HostLinkCandidates(pa.DataFrameModel):
    """The candidates behind each link with their signals (`+`-joined); none for unmatched."""

    fain: str
    host_kind: str = pa.Field(isin=[UNITID, LEAID])
    host_id: str
    host_name: str
    signals: str

    class Config:
        strict = True
        unique = ["fain", "host_kind", "host_id"]


def grant_facts(grants: pl.DataFrame, actions: pl.DataFrame) -> list[GrantFacts]:
    """Linker input per Grant: Recipient from the Grant table, business types from its latest action."""
    business_types = (
        actions.sort(
            "action_date", pl.col("modification_number").cast(pl.Int64, strict=False),
            descending=True, nulls_last=True,
        )
        .group_by("fain", maintain_order=True)
        .agg(pl.col("business_types").drop_nulls().first())
    )
    descriptions = (
        actions.select("fain", description=pl.concat_list("transaction_description", "base_transaction_description"))
        .explode("description")
        .drop_nulls("description")
        .unique()
        .sort("fain", "description")
        .group_by("fain", maintain_order=True)
        .agg("description")
    )
    rows = (
        grants.select("fain", "recipient_name", "recipient_uei", "recipient_state")
        .join(business_types, on="fain", how="left")
        .join(descriptions, on="fain", how="left")
    )
    return [
        GrantFacts(**{k: v for k, v in r.items() if k != "description"}, descriptions=tuple(r["description"] or ()))
        for r in rows.iter_rows(named=True)
    ]


def build_host_links(
    grants: pl.DataFrame, actions: pl.DataFrame, lookups: HostLookups
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Link every Grant; returns (host_links, host_link_candidates). One link per Grant-table row."""
    links = [link_host(facts, lookups) for facts in grant_facts(grants, actions)]
    link_rows = pl.DataFrame(
        [
            {
                "fain": link.fain, "outcome": link.outcome, "case_label": link.case_label,
                "host_kind": link.host_kind, "host_id": link.host_id, "host_name": link.host_name,
                "host_confidence": link.host_confidence,
            }
            for link in links
        ],
        schema={c: pl.String for c in HostLinks.to_schema().columns},
    ).sort("fain")
    candidate_rows = pl.DataFrame(
        [
            {"fain": link.fain, "host_kind": c.host_kind, "host_id": c.host_id, "host_name": c.host_name,
             "signals": "+".join(c.signals)}
            for link in links
            for c in link.candidates
        ],
        schema={c: pl.String for c in HostLinkCandidates.to_schema().columns},
    ).sort("fain", "host_kind", "host_id")
    if link_rows.height != grants.height:
        raise StructuralBreak(f"Host links have {link_rows.height} rows for {grants.height} Grants")
    return (
        check_schema(HostLinks, link_rows, "Host links"),
        check_schema(HostLinkCandidates, candidate_rows, "Host link candidates"),
    )
