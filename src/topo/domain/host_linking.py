"""Host linking: a deterministic rule cascade from a Grant to its Host institution (ADR 0002).

`link_host(grant, lookups)` is pure: one Grant's facts plus lookup tables in,
one HostLink out. The outcome is one of

    matched          one Host (UNITID or LEAID)
    no_single_host   decided by rule to have no one Host (GEAR UP State, a
                     statewide agency, a nonprofit naming no site)
    review           candidates found; a person must choose
    unmatched        no candidate found (carries no candidates)

and the Case label names the rule that decided it. No numeric score.

College signals, every one restricted to the Recipient's state (#32, #35):
Recipient UEI -> IPEDS `ueis`; Recipient name -> IPEDS names (every name since
`directory_from_year`, plus `inst_alias`); the ED list "Recipient/ campus" text
(by exact FAIN) and award-description phrases -> IPEDS names, former names,
aliases and generated acronyms; campus words, checked only against sibling
campuses; and address (city or ZIP), which only tags candidates already found.
ED text outranks the description. IPEDS merges resolve to the unit as of the
Grant's start year, else the same-state surviving unit. IPEDS system offices
(sector 0) never beat a real campus and alone go to review. The No single Host
rules. GEAR UP partnerships (#36) link only to districts (CCD LEAIDs) named by
the Recipient itself or the award descriptions, never to the college partner.
Case labels follow the prototype taxonomy (prototypes/host-linking/README.md),
with notes appended after "+": `followed_ipeds_merge`,
`ipeds_unit_as_of_start_year`, `no_uei`.
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

# Program words, not institution words: an acronym equal to one would light up on every description.
PROGRAM_WORDS = {
    "TRIO", "UB", "UBMS", "VUB", "SSS", "ETS", "TS", "EOC", "MCNAIR", "GEAR", "UP", "STEM", "MATH", "SCIENCE",
    "PROGRAM", "PROJECT", "UPWARD", "BOUND", "TALENT", "SEARCH", "STUDENT", "SUPPORT", "SERVICES",
    "EDUCATIONAL", "OPPORTUNITY", "CENTER", "VETERANS", "USA", "US", "THE", "ACE", "RISE", "SOAR", "CAP",
}
# Words that never tell one sibling campus from another.
GENERIC = {
    "UNIVERSITY", "COLLEGE", "CAMPUS", "MAIN", "COMMUNITY", "TECHNICAL", "BRANCH", "SCHOOL", "STATE",
    "SYSTEM", "OFFICE", "CENTRAL", "CENTER", "CITY", "INSTITUTE", "ONLINE", "GLOBAL", "COUNTY",
}
_CAMPUS_SUFFIX = re.compile(r"([- ]+Main Campus| District)$", re.IGNORECASE)
_ALIAS_ACRONYM = re.compile(r"[A-Z]{2,6}")

# Notes appended to a Case label ("uei_confirmed+followed_ipeds_merge").
FOLLOWED_IPEDS_MERGE = "followed_ipeds_merge"  # no record at the start year: linked to the same-state survivor
UNIT_AS_OF_START_YEAR = "ipeds_unit_as_of_start_year"  # merged later: kept as the unit it was at the start year
NO_UEI = "no_uei"  # no Recipient UEI: decided on name, ED list text and description only


def _tokens(text: str | None) -> list[str]:
    return name_key(text).split()


def acronym(name: str | None) -> str:
    """Generated acronym of a name of three or more words ('Horry-Georgetown Technical College' -> 'HGTC')."""
    words = [w for w in _norm(name).split() if w not in _DROP]
    return "".join(w[0] for w in words) if len(words) >= 3 else ""


def base_key(name: str | None) -> str:
    """A name before its campus suffix: 'University of Cincinnati-Clermont College' -> 'UNIVERSITY CINCINNATI'."""
    return name_key(re.split(r"[-,]", name or "")[0])


@dataclass(frozen=True)
class IpedsUnit:
    unitid: str
    name: str  # latest name
    state: str | None
    sector: int | None
    names: frozenset[str]  # name keys: every name since directory_from_year, plus aliases
    ueis: frozenset[str]
    city: str = ""  # latest city, normalized
    zip5: str = ""
    newid: str | None = None  # the UNITID this unit merged into
    years: frozenset[int] = frozenset()  # directory years the unit reported

    @property
    def is_system_office(self) -> bool:
        return self.sector == SYSTEM_OFFICE_SECTOR


def _split(values: str | None) -> list[str]:
    return [v.strip() for v in (values or "").split("|") if v.strip()]


def _frozen(index: dict) -> dict:
    return {k: frozenset(v) for k, v in index.items()}


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
    _by_phrase: dict[tuple[str, tuple[str, ...]], frozenset[str]] = field(default_factory=dict, repr=False)
    _by_acronym: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict, repr=False)
    _by_base: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict, repr=False)
    _years: tuple[int, int] | None = None  # first and last IPEDS directory year

    @classmethod
    def from_directory(cls, directory: pl.DataFrame, lea_directory: pl.DataFrame | None = None) -> "HostLookups":
        """Build from the cleaned IPEDS directory history (topo.sources.ipeds) and, for
        district Hosts, the cleaned CCD LEA directory history (topo.sources.ccd)."""
        latest: dict[str, dict] = {}
        texts: dict[str, set[str]] = defaultdict(set)  # every name and non-acronym alias
        acronyms: dict[str, set[str]] = defaultdict(set)
        ueis: dict[str, set[str]] = defaultdict(set)
        years: dict[str, set[int]] = defaultdict(set)
        newids: dict[str, str] = {}
        for r in directory.sort("unitid", "year").iter_rows(named=True):
            uid = r["unitid"]
            latest[uid] = r
            years[uid].add(r["year"])
            if r["newid"]:
                newids[uid] = r["newid"]
            texts[uid] |= {n for n in (r["inst_name"], _CAMPUS_SUFFIX.sub("", r["inst_name"] or "")) if n}
            for alias in _split(r["inst_alias"]):
                (acronyms if _ALIAS_ACRONYM.fullmatch(alias) else texts)[uid].add(alias)
            ueis[uid] |= set(_split(r["ueis"]))
        units = {}
        for uid, r in latest.items():
            generated = acronym(r["inst_name"])
            if len(generated) >= 4:
                acronyms[uid].add(generated)
            units[uid] = IpedsUnit(
                uid, r["inst_name"], r["state_abbr"], r["sector"],
                frozenset(k for k in map(name_key, texts[uid] | acronyms[uid]) if k), frozenset(ueis[uid]),
                city=_norm(r["city"]), zip5=(r["zip"] or "")[:5], newid=newids.get(uid),
                years=frozenset(years[uid]),
            )
        by_uei, by_name, by_unit_phrase, by_acronym, by_base = (defaultdict(set) for _ in range(5))
        for uid, unit in units.items():
            state = unit.state
            if state is None:
                continue
            for uei in unit.ueis:
                by_uei[(state, uei)].add(uid)
            for key in unit.names:
                by_name[(state, key)].add(uid)
            for text in texts[uid]:
                phrase = tuple(_tokens(text))
                if len(phrase) >= 2:  # single plain words ("PACIFIC", "MARSHALL") are too loose
                    by_unit_phrase[(state, phrase)].add(uid)
            for acr in map(_norm, acronyms[uid]):
                if len(acr) >= 3 and acr not in PROGRAM_WORDS:
                    by_acronym[(state, acr)].add(uid)
            by_base[(state, base_key(unit.name))].add(uid)
        all_years = [y for ys in years.values() for y in ys]
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
            _frozen(by_uei),
            _frozen(by_name),
            districts,
            _frozen(by_phrase),
            _frozen(by_core),
            _by_phrase=_frozen(by_unit_phrase),
            _by_acronym=_frozen(by_acronym),
            _by_base=_frozen(by_base),
            _years=(min(all_years), max(all_years)) if all_years else None,
        )

    def units_by_uei(self, state: str, uei: str | None) -> frozenset[str]:
        return self._by_uei.get((state, uei), frozenset()) if uei else frozenset()

    def units_by_name(self, state: str, name: str | None) -> frozenset[str]:
        key = name_key(name)
        return self._by_name.get((state, key), frozenset()) if key else frozenset()

    def units_by_phrase(self, state: str, text: str | None) -> frozenset[str]:
        """Units whose name, former name, alias or generated acronym appears in the text. A phrase
        nested in a longer matching phrase is dropped ('University of Cincinnati' inside
        'University of Cincinnati Clermont College')."""
        tokens = _tokens(text)
        longest = max((len(p) for _, p in self._by_phrase), default=0)
        spans = []
        for i in range(len(tokens)):
            for n in range(min(longest, len(tokens) - i), 1, -1):
                hit = self._by_phrase.get((state, tuple(tokens[i:i + n])))
                if hit:
                    spans.append((i, i + n, hit))
        found: set[str] = set()
        for start, end, hit in spans:
            if not any(s <= start and end <= e and (e - s) > (end - start) for s, e, _ in spans):
                found |= hit
        for word in _norm(text).split():
            found |= self._by_acronym.get((state, word), frozenset())
        return frozenset(found)

    def siblings(self, state: str, uids: list[str]) -> frozenset[str]:
        """Same-state campus families of the units: units sharing a base name with at least one
        other unit. Not the IPEDS system name, which whole state community-college systems share.
        A unit with no sibling is in no family."""
        family: set[str] = set()
        for uid in uids:
            group = self._by_base.get((state, base_key(self.units[uid].name)), frozenset())
            if len(group) >= 2:
                family |= group
        return frozenset(family)

    def as_of_start_year(self, uid: str, start_year: int | None, state: str) -> tuple[str | None, str | None]:
        """The unit to link for a Grant starting in `start_year`, and its merge note.

        A unit that later merged is kept when it reported in the start year (clamped to the
        directory's years). Otherwise its surviving unit is linked, same state only: an
        out-of-state survivor gives None."""
        unit = self.units[uid]
        if unit.newid is None or self._years is None:
            return uid, None
        first, last = self._years
        year = min(max(start_year if start_year is not None else last, first), last)
        if year in unit.years:
            return uid, UNIT_AS_OF_START_YEAR
        seen, current = {uid}, unit
        while current.newid and current.newid not in seen and current.newid in self.units:
            seen.add(current.newid)
            current = self.units[current.newid]
        if current.unitid == uid:
            return uid, None  # the survivor is not in the directory: nothing better to link
        if current.state != state:
            return None, None
        return current.unitid, FOLLOWED_IPEDS_MERGE

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
    """What the linker knows about one Grant: its Recipient (latest USAspending action), its
    award descriptions, the ED list "Recipient/ campus" text (by exact FAIN) and its start year."""

    fain: str
    recipient_name: str | None
    recipient_uei: str | None
    recipient_state: str | None
    business_types: str | None = None
    recipient_city: str | None = None
    recipient_zip: str | None = None
    descriptions: tuple[str, ...] = ()  # the Grant's distinct award descriptions
    ed_recipient_campus: str | None = None
    ed_campus: str | None = None  # the ED text after "/"
    start_year: int | None = None

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


# Signals, best first: uei, name, ED list text, then description phrases and campus words.
# "address" only breaks ties.
ED_TEXT = {"ed_list", "ed_campus"}
DESC_TEXT = {"desc", "desc_campus"}
SPECIFIC = ED_TEXT | DESC_TEXT
SEEDS = {"uei", "name", "ed_list"}  # the units whose sibling campuses are checked for campus words


def _college_signals(grant: GrantFacts, lookups: HostLookups) -> tuple[dict[str, set[str]], dict[str, str]]:
    """UNITID -> signals, same state only, and UNITID -> merge note. A Grant with no state has no candidates."""
    state = grant.recipient_state
    signals: dict[str, set[str]] = defaultdict(set)
    if not state:
        return signals, {}
    for uid in lookups.units_by_uei(state, grant.recipient_uei):
        signals[uid].add("uei")
    for uid in lookups.units_by_name(state, grant.recipient_name):
        signals[uid].add("name")
    for uid in lookups.units_by_phrase(state, (grant.ed_recipient_campus or "").replace("/", " ")):
        signals[uid].add("ed_list")
    for description in grant.descriptions:
        for uid in lookups.units_by_phrase(state, description):
            signals[uid].add("desc")
    _add_campus_words(grant, lookups, signals)
    signals, merges = _resolve_merges(grant, lookups, signals)
    if any(not lookups.units[uid].is_system_office for uid in signals):
        for uid in [uid for uid in signals if lookups.units[uid].is_system_office]:
            del signals[uid]
    _add_address(grant, lookups, signals)
    return signals, merges


def _add_campus_words(grant: GrantFacts, lookups: HostLookups, signals: dict[str, set[str]]) -> None:
    """Campus words: a sibling campus whose distinguishing words (or their initials) appear in the
    ED campus text or the description ('UC CLERMONT', 'OHIO STATE ATI'). Only siblings of the units
    found by UEI, name or ED list are checked, so campus words never reach another college."""
    seeds = sorted(uid for uid, sig in signals.items() if sig & SEEDS)
    if not seeds:
        return
    common = set.intersection(*(set(_tokens(lookups.units[uid].name)) for uid in seeds))
    texts = {"ed_campus": grant.ed_campus, "desc_campus": " || ".join(grant.descriptions)}
    for uid in sorted(lookups.siblings(grant.recipient_state, seeds)):
        if uid in seeds and len(seeds) == 1:
            continue
        rest = [t for t in _tokens(lookups.units[uid].name) if t not in common]
        distinct = {t for t in rest if t not in GENERIC}
        initials = "".join(t[0] for t in rest) if len(rest) >= 2 else ""
        for signal, text in texts.items():
            words = set(_tokens(text)) | set(_norm(text).split())
            if distinct and (distinct <= words or (len(initials) >= 3 and initials in words)):
                signals[uid].add(signal)


def _resolve_merges(
    grant: GrantFacts, lookups: HostLookups, signals: dict[str, set[str]]
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Move each candidate to its unit as of the Grant's start year (ADR 0002 merge policy)."""
    resolved: dict[str, set[str]] = defaultdict(set)
    notes: dict[str, str | None] = {}
    for uid, sig in signals.items():
        target, note = lookups.as_of_start_year(uid, grant.start_year, grant.recipient_state)
        if target is None:
            continue
        resolved[target] |= sig
        if target == uid:
            notes[target] = note  # a unit found directly keeps its own note
        else:
            notes.setdefault(target, note)
    return resolved, {uid: note for uid, note in notes.items() if note}


def _add_address(grant: GrantFacts, lookups: HostLookups, signals: dict[str, set[str]]) -> None:
    """Address agreement (city or ZIP) on a candidate already found. Never a source of candidates:
    it is the Recipient's SAM address, not where the project runs."""
    city, zip5 = _norm(grant.recipient_city), (grant.recipient_zip or "")[:5]
    for uid, sig in signals.items():
        unit = lookups.units[uid]
        if (zip5 and unit.zip5 == zip5) or (city and unit.city == city):
            sig.add("address")


def _with(colleges: dict[str, set[str]], wanted: set[str]) -> list[str]:
    return sorted(uid for uid, sig in colleges.items() if sig & wanted)


def _decide_college(
    colleges: dict[str, set[str]], kind: str, lookups: HostLookups
) -> tuple[str, str, str | None]:
    """(outcome, Case label, UNITID or None) for one or more college candidates."""
    if len(colleges) == 1:
        ((uid, with_address),) = colleges.items()
        sig = with_address - {"address"}
        if lookups.units[uid].is_system_office:
            return REVIEW, "only_candidate_is_system_office", uid
        if "uei" in sig and len(sig) >= 2:
            return MATCHED, "uei_confirmed", uid
        if sig & SPECIFIC and (sig & {"uei", "name"} or "address" in with_address):
            return MATCHED, "campus_text_confirmed", uid
        if sig == {"uei"}:
            return (MATCHED, "uei_only", uid) if kind in (IHE, AUX) else (REVIEW, "uei_only_non_college", uid)
        if sig == {"name"} and "address" in with_address:
            return MATCHED, "name_and_address", uid
        return REVIEW, "single_weak_signal:" + "+".join(sorted(sig)), uid

    uei = _with(colleges, {"uei"})

    def overrides_uei(pick: str) -> bool:
        return bool(uei) and pick not in uei

    # Campus words pick one sibling campus; ED campus text outranks the description's.
    campus = _with(colleges, {"ed_campus"}) or _with(colleges, {"desc_campus"})
    if len(campus) == 1:
        pick = campus[0]
        contradicted = "ed_campus" in colleges[pick] and any(
            "desc_campus" in sig for uid, sig in colleges.items() if uid != pick
        )
        if not contradicted:
            return MATCHED, "campus_named_overrides" if overrides_uei(pick) else "campus_named", pick
        if not overrides_uei(pick):
            return MATCHED, "ed_list_outranks_desc", pick
        return REVIEW, "several_campuses_named", None

    # Names from the ED list or the description; ED text outranks the description.
    specific = _with(colleges, SPECIFIC)
    if len(specific) == 1:
        pick = specific[0]
        if overrides_uei(pick):
            return REVIEW, "campus_text_overrides_uei", pick
        return MATCHED, "campus_text_picks_one", pick
    if len(specific) > 1:
        both = [uid for uid in specific if {"ed_list", "desc"} <= colleges[uid]]
        if len(both) == 1:
            return MATCHED, "ed_list_and_desc_agree", both[0]
        ed = _with(colleges, ED_TEXT)
        if len(ed) == 1 and not overrides_uei(ed[0]):
            return MATCHED, "ed_list_outranks_desc", ed[0]
        return REVIEW, "several_campuses_named", None

    # Only UEI and name: the address breaks the tie.
    if len(uei) == 1:
        pick = uei[0]
        return (MATCHED if "address" in colleges[pick] else REVIEW), "uei_vs_name_conflict", pick
    by_address = _with(colleges, {"address"})
    if len(by_address) == 1:
        return REVIEW, "system_campus_by_address", by_address[0]
    return REVIEW, "system_campus_not_stated", None


def link_host(grant: GrantFacts, lookups: HostLookups) -> HostLink:
    """Link one Grant to its Host institution. Pure: no I/O, no clock."""
    kind = recipient_kind(grant.business_types, grant.recipient_name)
    if grant.fain_prefix == GEAR_UP_PARTNERSHIP_PREFIX:
        return _link_gear_up_partnership(grant, kind, lookups)
    colleges, merges = _college_signals(grant, lookups)

    candidates = tuple(
        Candidate(UNITID, uid, lookups.units[uid].name, tuple(sorted(sig)))
        for uid, sig in sorted(colleges.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )

    def result(outcome: str, case_label: str, pick: str | None = None) -> HostLink:
        notes = [merges[pick]] if pick in merges else []
        if outcome != NO_SINGLE_HOST and not grant.recipient_uei:
            notes.append(NO_UEI)
        return HostLink(
            fain=grant.fain,
            outcome=outcome,
            case_label="+".join([case_label, *notes]),
            host_kind=UNITID if pick else None,
            host_id=pick,
            host_name=lookups.units[pick].name if pick else None,
            candidates=() if outcome == UNMATCHED else candidates,
        )

    if grant.fain_prefix == GEAR_UP_STATE_PREFIX:
        return result(NO_SINGLE_HOST, "gearup_state")
    if kind == STATE:
        return result(NO_SINGLE_HOST, "state_agency_no_site_named")

    if colleges:
        return result(*_decide_college(colleges, kind, lookups))

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


def grant_facts(
    grants: pl.DataFrame, actions: pl.DataFrame, ed_list_rows: pl.DataFrame | None = None
) -> list[GrantFacts]:
    """Linker input per Grant: Recipient and start year from the Grant table; business types,
    city and ZIP from its latest action; its distinct award descriptions; and the "Recipient/
    campus" text of its latest ED TRIO list row (cleaned `ed_trio_list_rows`), by exact FAIN."""
    latest = (
        actions.sort(
            "action_date", pl.col("modification_number").cast(pl.Int64, strict=False),
            descending=True, nulls_last=True,
        )
        .group_by("fain", maintain_order=True)
        .agg(
            pl.col("business_types").drop_nulls().first(),
            pl.col("recipient_city").drop_nulls().first(),
            pl.col("recipient_zip").drop_nulls().first(),
        )
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
        grants.select(
            "fain", "recipient_name", "recipient_uei", "recipient_state",
            pl.col("project_start").dt.year().alias("start_year"),
        )
        .join(latest, on="fain", how="left")
        .join(descriptions, on="fain", how="left")
    )
    if ed_list_rows is not None and ed_list_rows.height:
        ed = (
            ed_list_rows.sort("fiscal_year", "list_row_id", descending=True)
            .group_by("fain", maintain_order=True)
            .agg(pl.col("recipient_campus").first().alias("ed_recipient_campus"), pl.col("ed_campus").first())
        )
        rows = rows.join(ed, on="fain", how="left")
    return [
        GrantFacts(**{k: v for k, v in r.items() if k != "description"}, descriptions=tuple(r["description"] or ()))
        for r in rows.iter_rows(named=True)
    ]


def build_host_links(
    grants: pl.DataFrame, actions: pl.DataFrame, lookups: HostLookups, ed_list_rows: pl.DataFrame | None = None
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Link every Grant; returns (host_links, host_link_candidates). One link per Grant-table row."""
    links = [link_host(facts, lookups) for facts in grant_facts(grants, actions, ed_list_rows)]
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
