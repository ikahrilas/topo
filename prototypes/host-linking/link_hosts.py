"""PROTOTYPE (throwaway, #10): link FY2024 TRIO and GEAR UP Grants to a Host institution.

Answers one question: what does the Recipient -> Host institution match space look
like on real data? Which cases are easy, which need fuzzy matching, which need a
human, and what would a review queue hold? Not pipeline code: no tests, no error
handling, everything in memory, re-reads the big CSVs on every run.

Run (paths are arguments; nothing is read from the repo except the ED lists):

    python -I prototypes/host-linking/link_hosts.py \
        --archive /tmp/rvh_data/FY2024_091_Assistance_Full_20261007_1.csv \
        --ipeds /tmp/rvh_ref/ipeds_dir.csv --lea /tmp/rvh_ref/lea_dir.csv \
        --ed-dir data/raw/ed_grantee_lists --gold /tmp/topo_proto/rvh.md \
        --out /tmp/topo_proto/out

Needs polars, pdfplumber, rapidfuzz. See README.md for sources and findings.
"""

import argparse
import collections
import re
from pathlib import Path

import pdfplumber
import polars as pl
from rapidfuzz import fuzz, process

LISTINGS = ["84.042", "84.044", "84.047", "84.066", "84.217", "84.334"]
ED_PROGRAMS = ["ub_84047A", "ubms_84047M", "vub_84047V", "ts_84044", "sss_84042A", "eoc_84066A", "mcnair_84217A"]

# --------------------------------------------------------------------------- text


ABBREV = {
    "UNIV": "UNIVERSITY", "U": "UNIVERSITY", "COL": "COLLEGE", "COLL": "COLLEGE", "CC": "COMMUNITY COLLEGE",
    "CMTY": "COMMUNITY", "COMM": "COMMUNITY", "TECH": "TECHNICAL", "ST": "STATE", "INST": "INSTITUTE",
    "SAINT": "ST", "MT": "MOUNT", "CTR": "CENTER", "DIST": "DISTRICT",
}
DROP = {"THE", "INC", "INCORPORATED", "AND", "OF", "AT", "IN", "FOR", "ON", "A"}
# Tokens that are program words, not institution words. An acronym alias equal to one
# of these would light up on every description.
PROGRAM_WORDS = {
    "TRIO", "UB", "UBMS", "VUB", "SSS", "ETS", "TS", "EOC", "MCNAIR", "GEAR", "UP", "STEM", "MATH", "SCIENCE",
    "PROGRAM", "PROJECT", "UPWARD", "BOUND", "TALENT", "SEARCH", "STUDENT", "SUPPORT", "SERVICES",
    "EDUCATIONAL", "OPPORTUNITY", "CENTER", "VETERANS", "USA", "US", "THE", "ACE", "RISE", "SOAR", "CAP",
}


def norm(s):
    """Uppercase, ASCII-ish, punctuation to spaces, 'X UNIV OF' -> 'UNIVERSITY OF X'."""
    if not s:
        return ""
    s = s.upper().replace("&", " AND ").replace("'", "")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"^(.*) (UNIV|UNIVERSITY) OF$", s)
    if m:
        s = f"UNIVERSITY OF {m.group(1)}"
    return s


def tokens(s):
    """Normalized tokens with abbreviations expanded and filler words dropped (for phrase lookup)."""
    out = []
    for t in norm(s).split():
        t = ABBREV.get(t, t)
        out.extend(x for x in t.split() if x not in DROP)
    return out


def key(s):
    return " ".join(tokens(s))


def acronym(name):
    words = [w for w in norm(name).replace("-", " ").split() if w not in DROP]
    return "".join(w[0] for w in words) if len(words) >= 3 else ""


# ------------------------------------------------------------------------ sources


def load_grants(archive):
    """One row per FAIN with an FY2024 action, highest modification_number wins.

    All FY2024 transaction descriptions for the FAIN are kept (joined with ' || ')."""
    cols = [
        "award_id_fain", "modification_number", "recipient_uei", "recipient_name", "recipient_name_raw",
        "recipient_city_name", "recipient_state_code", "recipient_zip_code", "recipient_address_line_1",
        "transaction_description", "prime_award_base_transaction_description", "business_types_description",
        "cfda_number", "awarding_agency_code",
    ]
    tx = (
        pl.scan_csv(archive, infer_schema_length=0)
        .select(cols)
        .filter(pl.col("awarding_agency_code") == "091", pl.col("cfda_number").is_in(LISTINGS))
        .collect()
    )
    descs = tx.group_by("award_id_fain").agg(
        pl.concat_str(["transaction_description", "prime_award_base_transaction_description"], separator=" || ")
        .unique()
        .str.join(" || ")
        .alias("desc_all")
    )
    g = (
        tx.with_columns(pl.col("modification_number").cast(pl.Int64, strict=False).alias("_m"))
        .sort("_m", descending=True)
        .unique("award_id_fain", keep="first")
        .drop("_m")
        .join(descs, on="award_id_fain")
        .rename({"award_id_fain": "fain", "recipient_state_code": "state"})
        .with_columns(pl.col("recipient_zip_code").str.slice(0, 5).alias("zip5"), pl.col("fain").str.slice(0, 5).alias("fain_prefix"))
    )
    return tx.height, g.sort("fain")


def load_ipeds(path):
    """Per UNITID reported in 2022 or later: every name and alias seen 2015-2025 (former
    names such as 'West Hills College Lemoore'), UEIs seen 2022-2025, state, city, zip5, sector."""
    d = (
        pl.read_csv(path, infer_schema_length=0)
        .filter(pl.col("year").cast(pl.Int32) >= 2015)
        .select("unitid", "year", "inst_name", "inst_alias", "ueis", "state_abbr", "city", "zip", "inst_system_name", "sector", "newid")
    )
    alive = set(d.filter(pl.col("year").cast(pl.Int32) >= 2022)["unitid"])  # keeps colleges that closed recently (Holy Names, 2023)
    # units merged away before 2022 lend their names to the unit that absorbed them (North Lake College -> Dallas College)
    merged = dict(d.filter(~pl.col("unitid").is_in(alive), ~pl.col("newid").is_in(["-1", "-2", "-3"]), pl.col("newid").is_not_null())
                  .select("unitid", "newid").unique("unitid").iter_rows())
    former = collections.defaultdict(set)
    for old, new in merged.items():
        seen = {old}
        while new in merged and new not in seen:
            seen.add(new)
            new = merged[new]
        if new in alive:
            former[new] |= set(d.filter(pl.col("unitid") == old)["inst_name"])
    units = {}
    for r in d.filter(pl.col("unitid").is_in(alive)).sort("year").iter_rows(named=True):
        u = units.setdefault(r["unitid"], {"names": set(), "aliases": set(), "ueis": set()})
        u.update(name=r["inst_name"], state=r["state_abbr"], city=norm(r["city"]), zip5=(r["zip"] or "")[:5],
                 system=r["inst_system_name"], sector=r["sector"])
        if r["newid"] and r["newid"] not in ("-1", "-2", "-3"):
            u["merged_into"] = r["newid"]
        u["names"].add(r["inst_name"])
        u["names"] |= former.get(r["unitid"], set())
        for a in (r["inst_alias"] or "").split("|"):
            a = a.strip()
            if a and a not in ("-1", "-2", "-3"):
                u["aliases"].add(a)
        for e in (r["ueis"] or "").split("|") if r["year"] >= "2022" else []:
            e = e.strip()
            if e and e not in ("-1", "-2", "-3"):
                u["ueis"].add(e)
    return units


LEA_SUFFIX = r"(INDEPENDENT SCHOOL DISTRICT|UNIFIED SCHOOL DISTRICT|CONSOLIDATED SCHOOL DISTRICT|SCHOOL DISTRICT|PUBLIC SCHOOLS|CITY SCHOOLS|COUNTY SCHOOLS|SCHOOLS|SCHOOL CORPORATION|DISTRICT|ISD|USD|CISD|CSD|SD)( NO \d+| \d+)?$"
LEA_PREFIX = r"^(BOARD OF EDUCATION OF (THE )?|SCHOOL DISTRICT OF (THE )?|SCHOOL BOARD OF )"
LEA_TAIL = r" (BOARD OF EDUCATION|SCHOOL BOARD|CITY SCHOOL BOARD|COUNTY SCHOOL BOARD)$"


def lea_core(name):
    """'BOARD OF EDUCATION OF OGDEN CITY' -> 'OGDEN', 'Philadelphia City SD' -> 'PHILADELPHIA'."""
    s = norm(name).replace("METRO ", "METROPOLITAN ")
    s = re.sub(LEA_PREFIX, "", s)
    s = re.sub(LEA_TAIL, "", s)
    s = re.sub(LEA_SUFFIX, "", s).strip()
    s = re.sub(r" (CITY|COUNTY|AREA|COMMUNITY|PUBLIC|MUNICIPAL|UNIFIED|JOINT|CONSOLIDATED)$", "", s).strip()
    return s


LEA_FORMS = ["SCHOOL DISTRICT", "SCHOOLS", "PUBLIC SCHOOLS", "INDEPENDENT SCHOOL DISTRICT", "ISD", "UNIFIED SCHOOL DISTRICT",
             "USD", "CITY SCHOOLS", "CITY SCHOOL DISTRICT", "COUNTY SCHOOLS", "COUNTY SCHOOL DISTRICT", "SCHOOL CORPORATION",
             "COMMUNITY SCHOOLS", "AREA SCHOOL DISTRICT", "SCHOOL BOARD", "BOARD OF EDUCATION"]


def load_leas(path):
    """Per LEAID (CCD 2024): name, state, city, zip5. Regular, component, and ESA agencies only."""
    d = (
        pl.read_csv(path, infer_schema_length=0)
        .filter(pl.col("year") == "2024", pl.col("agency_type").is_in(["1", "2", "4", "5", "7"]))
        .select("leaid", "lea_name", "state_location", "city_location", "zip_location", "agency_type")
    )
    return {
        r["leaid"]: {"name": r["lea_name"], "state": r["state_location"], "city": norm(r["city_location"]),
                     "zip5": (r["zip_location"] or "")[:5], "agency_type": r["agency_type"]}
        for r in d.iter_rows(named=True)
    }


FAIN_LINE = re.compile(r"^(P\d{3}[A-Z]\d{6})\s+(.*?)\s*\b([A-Z]{2})\s+([\d,]+)\s+\$([\d,]+)(?:\s+\S.*)?$")


def load_ed_lists(ed_dir):
    """FY2024 TRIO grantee lists: FAIN -> ED name and state. Rows look like
    'P047A221553 University of Alaska/ Anchorage AK 60 $309,505' (SSS adds a type column).
    When the name is wrapped off the row, the nearest non-row line above is used."""
    rows, misses = {}, []
    for prog in ED_PROGRAMS:
        pdf = next(Path(ed_dir).glob(f"{prog}__FY2024__*.pdf"))
        with pdfplumber.open(pdf) as p:
            lines = [ln.strip() for page in p.pages for ln in (page.extract_text() or "").splitlines()]
        prev_text = ""
        for ln in lines:
            m = FAIN_LINE.match(ln)
            if m:
                name = m.group(2) or prev_text
                rows[m.group(1)] = {"ed_name": name, "ed_state": m.group(3), "ed_program": prog}
                if not m.group(2):
                    misses.append(f"{m.group(1)}: name taken from line above: {prev_text!r}")
                prev_text = ""
            elif re.match(r"^P\d{3}[A-Z]\d{6}", ln):
                misses.append(f"unparsed: {ln}")
            else:
                prev_text = ln
    return rows, misses


def load_gold(md):
    """Appendix B of docs/research/recipient-vs-host-institution.md (branch research/recipient-vs-host)."""
    gold = {}
    for ln in Path(md).read_text().splitlines():
        c = [x.strip() for x in ln.split("|")]
        if len(c) > 13 and re.match(r"^P\d{3}[A-Z]\d{6}$", c[2]):
            host = c[6]
            if host in ("NONE", "MULTI"):
                g = ("NOHOST", {host})
            else:
                kind, ids = host.split(" ")
                g = (kind, set(ids.split("/")))
            gold[c[2]] = {"gold_kind": g[0], "gold_ids": g[1], "gold_type": c[5], "gold_conf": c[12]}
    return gold


# ------------------------------------------------------------------ phrase index


class PhraseIndex:
    """State-scoped exact phrase lookup over normalized tokens, longest match wins."""

    def __init__(self):
        self.by_state = collections.defaultdict(lambda: collections.defaultdict(set))
        self.acr = collections.defaultdict(lambda: collections.defaultdict(set))
        self.maxlen = 1

    def add(self, state, phrase, ident, how):
        if how in ("acronym", "alias_acronym"):
            t = (norm(phrase),)
            if len(t[0]) < 3 or t[0] in PROGRAM_WORDS:
                return
            self.acr[state][t[0]].add((ident, how))
            return
        t = tuple(tokens(phrase))
        if not t:
            return
        if len(t) == 1:
            return  # single plain words ("PACIFIC", "MARSHALL") are too loose
        self.by_state[state][t].add((ident, how))
        self.maxlen = max(self.maxlen, len(t))

    def find(self, state, text):
        """Return {ident: best how} for phrases in text, dropping matches nested in a longer match."""
        tk = tokens(text)
        idx = self.by_state.get(state, {})
        spans = []
        for i in range(len(tk)):
            for n in range(min(self.maxlen, len(tk) - i), 0, -1):
                hit = idx.get(tuple(tk[i:i + n]))
                if hit:
                    spans.append((i, i + n, hit))
        keep = [s for s in spans if not any(o[0] <= s[0] and s[1] <= o[1] and (o[1] - o[0]) > (s[1] - s[0]) for o in spans)]
        for t in norm(text).split():
            hit = self.acr.get(state, {}).get(t)
            if hit:
                keep.append((0, 0, hit))
        out = {}
        for _, _, hit in keep:
            for ident, how in hit:
                out.setdefault(ident, how)
        return out


def build_indexes(units, leas):
    col = PhraseIndex()
    for uid, u in units.items():
        for n in u["names"]:
            col.add(u["state"], n, uid, "name")
            stripped = re.sub(r"([- ]+Main Campus| District)$", "", n)
            if stripped != n:
                col.add(u["state"], stripped, uid, "name")
        for a in u["aliases"]:
            col.add(u["state"], a, uid, "alias_acronym" if re.fullmatch(r"[A-Z]{2,6}", a) else "alias")
        ac = acronym(u["name"])
        if len(ac) >= 4:
            col.add(u["state"], ac, uid, "acronym")
    lea = PhraseIndex()
    for lid, l in leas.items():
        nm = norm(l["name"])
        core = re.sub(LEA_SUFFIX, "", nm).strip()
        lea.add(l["state"], nm, lid, "lea_name")
        if core and core != nm:
            for f in LEA_FORMS:
                lea.add(l["state"], f"{core} {f}", lid, "lea_form")
        elif core:
            for f in LEA_FORMS:
                lea.add(l["state"], f"{core} {f}", lid, "lea_form")
    return col, lea


# ------------------------------------------------------------------- matching

COLLEGEY = re.compile(r"\b(COLLEGE|UNIVERSITY|UNIV|INSTITUTE OF TECHNOLOGY|COMMUNITY COLLEGE|REGENTS|POLYTECHNIC|SEMINARY)\b")
AUX = re.compile(r"\b(FOUNDATION|RESEARCH CORPORATION|RESEARCH FOUNDATION|CORPORATION|CENTER FOR RESEARCH|AUXILIARY)\b")
LEAY = re.compile(r"\b(SCHOOL DISTRICT|PUBLIC SCHOOLS|SCHOOL BOARD|BOARD OF EDUCATION|ISD|USD|CITY SCHOOLS|COUNTY SCHOOLS|SCHOOL CORP|COMMUNITY SCHOOLS|INTERMEDIATE UNIT|EDUCATION SERVICE|EDUCATION SRV|EDUCATIONAL SERVICE|COUNTY OFFICE OF EDUCATION|DEPARTMENT OF EDUCATION|COOPERATIVE EDUCATIONAL|COLLEGE PREP)\b")
SCHOOL_NAMED = re.compile(r"\b[A-Z]+ (HIGH|MIDDLE|JUNIOR HIGH|ELEMENTARY) SCHOOLS?\b")


GENERIC = {"UNIVERSITY", "COLLEGE", "CAMPUS", "MAIN", "COMMUNITY", "TECHNICAL", "BRANCH", "SCHOOL", "STATE",
           "SYSTEM", "OFFICE", "CENTRAL", "CENTER", "CITY", "INSTITUTE", "ONLINE", "GLOBAL", "COUNTY"}


def base_key(name):
    return key(re.split(r"[-,]", name)[0])


def add_distinct(units):
    """Per unit: words that tell it apart from its system siblings, plus their acronym."""
    by_base = collections.defaultdict(set)
    for uid, u in units.items():
        by_base[(u["state"], base_key(u["name"]))].add(uid)
    for uid, u in units.items():
        u["base"] = base_key(u["name"])
        rest = [t for t in tokens(u["name"]) if t not in set(u["base"].split())]
        u["distinct"] = ({t for t in rest if t not in GENERIC}, "".join(t[0] for t in rest) if len(rest) >= 2 else "")
    return by_base


def family(seeds, units, state):
    """Seed units plus same-state units sharing a seed's base name ('University of Cincinnati'
    for '-Main Campus' and '-Clermont College'). Not IPEDS system name: whole state
    community-college systems share one, and their campuses' names collide with place words."""
    bases = {units[i]["base"] for i in seeds}
    return set(seeds) | {uid for uid, u in units.items() if u["state"] == state and u["base"] in bases} if seeds else set()


def recipient_kind(g):
    bt, nm = (g["business_types_description"] or "").upper(), norm(g["recipient_name"])
    ihe_bt = "INSTITUTION OF HIGHER EDUCATION" in bt and "OTHER THAN" not in bt
    if ihe_bt:
        return "IHE"
    if "NONPROFIT" in bt or "PROFIT" in bt or "SMALL BUSINESS" in bt:
        # 'College Now', 'University Settlement', 'College Entrance Examination Board' are nonprofits
        return "AUX" if AUX.search(nm) and COLLEGEY.search(nm) else "NP"
    if LEAY.search(nm):  # 'CLEVELAND HEIGHTS UNIVERSITY HEIGHTS CITY SCHOOL DISTRICT'
        return "LEA"
    if COLLEGEY.search(nm):  # before the business type: SAM registers many community college districts as school districts
        return "AUX" if AUX.search(nm) else "IHE"
    if "SCHOOL DISTRICT" in bt:
        return "LEA"
    if "STATE GOVERNMENT" in bt:
        return "STATE"
    return "NP"


def fuzzy_best(text, choices, cutoff):
    if not text or not choices:
        return None
    return process.extractOne(key(text), list(choices), scorer=fuzz.token_sort_ratio, score_cutoff=cutoff)


def link(g, units, leas, col, lea, uei_map, col_keys_by_state, lea_keys_by_state, ed, city_leas):
    st = g["state"]
    kind = recipient_kind(g)
    ev = collections.defaultdict(set)  # candidate id -> signals

    # signals for colleges
    for uid in uei_map.get(g["recipient_uei"], set()):
        if units[uid]["state"] == st:
            ev[("UNITID", uid)].add("uei")
    edrow = ed.get(g["fain"])
    ed_campus = None
    if edrow:
        ed_name = edrow["ed_name"]
        base, _, ed_campus = ed_name.partition("/")
        ed_campus = ed_campus.strip() or None
        for uid in col.find(st, ed_name.replace("/", " ")):
            ev[("UNITID", uid)].add("ed_list")
        if not any("ed_list" in s for s in ev.values()):
            hit = fuzzy_best(base, col_keys_by_state.get(st, {}), 90)
            if hit:
                for uid in col_keys_by_state[st][hit[0]]:
                    ev[("UNITID", uid)].add("ed_list_fuzzy")
        for lid in lea.find(st, ed_name):
            ev[("LEAID", lid)].add("ed_list")
    for uid, how in col.find(st, g["desc_all"]).items():
        ev[("UNITID", uid)].add("desc")
    for uid in col.find(st, g["recipient_name_raw"] or "") if g["recipient_name_raw"] != g["recipient_name"] else []:
        ev[("UNITID", uid)].add("raw_name")
    for uid in col.find(st, g["recipient_name"]):
        ev[("UNITID", uid)].add("name")
    if not any(("name" in s) for k, s in ev.items() if k[0] == "UNITID") and kind in ("IHE", "AUX"):
        hit = fuzzy_best(g["recipient_name"], col_keys_by_state.get(st, {}), 90)
        if hit:
            for uid in col_keys_by_state[st][hit[0]]:
                ev[("UNITID", uid)].add("name_fuzzy")

    # signals for districts
    for lid in lea.find(st, g["desc_all"]):
        ev[("LEAID", lid)].add("desc")
    for lid in lea.find(st, g["recipient_name"]):
        ev[("LEAID", lid)].add("name")
    if kind == "LEA" and not any(k[0] == "LEAID" and "name" in s for k, s in ev.items()):
        core = lea_core(g["recipient_name"])
        for lid in lea_keys_by_state.get(st, {}).get(core, ()):
            ev[("LEAID", lid)].add("name")
        if not any(k[0] == "LEAID" for k in ev):
            hit = process.extractOne(core, list(lea_keys_by_state.get(st, {})), scorer=fuzz.ratio, score_cutoff=90)
            if hit:
                for lid in lea_keys_by_state[st][hit[0]]:
                    ev[("LEAID", lid)].add("name_fuzzy")
    # a city named in the description that has exactly one regular district: a hint, never auto
    if kind in ("NP", "LEA", "STATE") and not any(k[0] == "LEAID" and "desc" in s for k, s in ev.items()):
        d = " " + norm(g["desc_all"]) + " "
        for (s2, city), lids in city_leas.items():
            if s2 == st and len(lids) == 1 and len(city) > 3 and f" {city} " in d \
                    and f" {city} COUNTY" not in d and f" {city} SECONDARY" not in d:
                ev[("LEAID", next(iter(lids)))].add("desc_city")

    # campus tokens: a candidate's sibling campus whose distinguishing words appear in the
    # ED campus text or the description ('UNM GALLUP' -> University of New Mexico-Gallup Campus,
    # 'OHIO STATE ATI' -> Ohio State University Agricultural Technical Institute)
    seeds = [i for (k, i), sg in ev.items() if k == "UNITID" and sg & {"uei", "name", "name_fuzzy", "ed_list", "raw_name"}]
    texts = {"ed_campus": ed_campus or "", "desc_campus": g["desc_all"]}
    common = set.intersection(*(set(tokens(units[i]["name"])) for i in seeds)) if seeds else set()
    for uid in family(seeds, units, st):
        if uid in seeds and len(seeds) == 1:
            continue
        rest = [t for t in tokens(units[uid]["name"]) if t not in common]
        dt, ac = {t for t in rest if t not in GENERIC}, ("".join(t[0] for t in rest) if len(rest) >= 2 else "")
        for sig, text in texts.items():
            tk = set(tokens(text)) | set(norm(text).split())
            if dt and (dt <= tk or (len(ac) >= 3 and ac in tk)):
                ev[("UNITID", uid)].add(sig)

    # address agreement is a tie-breaker, never a candidate source (PoP = recipient address)
    for (k, i), s in ev.items():
        ref = units[i] if k == "UNITID" else leas[i]
        if ref["zip5"] == g["zip5"] or ref["city"] == norm(g["recipient_city_name"]):
            s.add("address")

    real = {k for k in ev if k[0] == "UNITID" and units[k[1]]["sector"] != "0"}
    if real:
        for k in [k for k in ev if k[0] == "UNITID" and k not in real]:
            del ev[k]
    return kind, decide(g, kind, ev, ed_campus)


UNITS = {}
SPECIFIC = {"ed_list", "ed_list_fuzzy", "desc", "raw_name", "ed_campus", "desc_campus"}
CAMPUS = {"ed_campus", "desc_campus"}


def units_sector(k):
    return UNITS[k[1]]["sector"] if k[0] == "UNITID" else None


def decide(g, kind, ev, ed_campus):
    """Return (outcome, case, host_kind, host_id, candidates)."""
    cands = {k: s for k, s in ev.items()}
    cand_str = "; ".join(f"{k[0]} {k[1]}:{'+'.join(sorted(s))}" for k, s in sorted(cands.items(), key=lambda kv: -len(kv[1])))

    def res(outcome, case, pick=None):
        return outcome, case, (pick[0] if pick else None), (pick[1] if pick else None), cand_str

    prefix = g["fain_prefix"]
    if prefix == "P334S":
        return res("no_single_host", "gearup_state")
    if kind == "STATE" and not any((SPECIFIC | {"desc_city"}) & s for s in cands.values()):
        return res("no_single_host", "state_agency_no_site_named")

    colleges = {k: s for k, s in cands.items() if k[0] == "UNITID"}
    if prefix == "P334A":
        colleges = {}  # GEAR UP partnerships serve district cohorts; the college partner is not the Host
    districts = {k: s for k, s in cands.items() if k[0] == "LEAID"}
    specific = {k: s for k, s in colleges.items() if SPECIFIC & s}
    uei = {k for k, s in colleges.items() if "uei" in s}

    if colleges:
        # one college carries every non-address signal there is
        strong = {k for k, s in colleges.items() if (s - {"address"}) - {"name_fuzzy"}}
        if len(colleges) == 1:
            (k, s), = colleges.items()
            sig = s - {"address"}
            if "uei" in sig and len(sig) >= 2:
                return res("matched", "uei_confirmed", k)
            if sig & SPECIFIC and ("name" in sig or "uei" in sig or "address" in s):
                return res("matched", "campus_text_confirmed", k)
            if units_sector(k) == "0":
                return res("review", "only_candidate_is_system_office", k)
            if sig == {"uei"}:
                return res("matched", "uei_only", k) if kind in ("IHE", "AUX") else res("review", "uei_only_non_college", k)
            if sig == {"name"} and "address" in s:
                return res("matched", "name_and_address", k)
            return res("review", "single_weak_signal:" + "+".join(sorted(sig)), k)
        campus = {k for k, s in colleges.items() if CAMPUS & s}
        if len(campus) == 1:
            k = next(iter(campus))
            return res("matched", "campus_named_overrides" if uei and k not in uei else "campus_named", k)
        # several colleges: campus text decides
        if len(specific) == 1:
            k = next(iter(specific))
            if uei and k not in uei:
                return res("review", "campus_text_overrides_uei", k)
            return res("matched", "campus_text_picks_one", k)
        if len(specific) > 1:
            both = {k for k, s in specific.items() if {"ed_list", "ed_list_fuzzy"} & s and "desc" in s}
            if len(both) == 1:
                return res("matched", "ed_list_and_desc_agree", next(iter(both)))
            return res("review", "several_campuses_named", None)
        if len(uei) == 1:
            k = next(iter(uei))
            others = set(colleges) - {k}
            return res("matched", "uei_vs_name_conflict", k) if "address" in colleges[k] else res("review", "uei_vs_name_conflict", k)
        addr = [k for k, s in colleges.items() if "address" in s]
        if len(addr) == 1:
            return res("review", "system_campus_by_address", addr[0])
        return res("review", "system_campus_not_stated", None)

    if districts:
        named = {k: s for k, s in districts.items() if "name" in s or "name_fuzzy" in s}
        in_desc = {k: s for k, s in districts.items() if {"desc", "ed_list"} & s}
        if len(named) == 1 and kind in ("LEA", "STATE", "NP") and "address" in named[next(iter(named))] and "name" in named[next(iter(named))] and not in_desc:
            return res("matched", "district_is_recipient", next(iter(named)))
        if kind == "LEA" and len(named) == 1:
            k = next(iter(named))
            if in_desc and k not in in_desc:
                return res("review", "district_recipient_serves_other_district", None)
            return res("matched", "district_is_recipient", k) if ("address" in named[k] or "name" in named[k]) else res("review", "district_name_fuzzy", k)
        if len(in_desc) == 1:
            return res("matched", "district_named_in_desc", next(iter(in_desc)))
        city = {k for k, s in districts.items() if "desc_city" in s}
        if len(city) == 1 and not named:
            return res("review", "city_named_with_one_district", next(iter(city)))
        if len(in_desc) > 1:
            return res("no_single_host" if prefix == "P334A" else "review", "several_districts_named")
        return res("review", "district_weak_signal")

    if prefix == "P334A":
        return res("no_single_host", "gearup_partnership_no_district_named")
    if kind == "NP":
        if SCHOOL_NAMED.search(norm(g["desc_all"])):
            return res("review", "school_named_needs_school_lookup")
        return res("no_single_host", "nonprofit_no_site_named")
    if kind == "STATE":
        return res("no_single_host", "state_agency_no_site_named")
    return res("unmatched", f"no_candidate_{kind.lower()}")


# ------------------------------------------------------------------- scoring


def score(row, gold):
    """correct / wrong / no_answer for one linked Grant vs the hand label."""
    gk, gids = gold["gold_kind"], gold["gold_ids"]
    if row["outcome"] == "no_single_host":
        return "correct" if gk == "NOHOST" else "wrong"
    if row["host_id"] is None:
        return "no_answer"
    if gk == "NOHOST":
        return "wrong"
    return "correct" if (row["host_kind"] == gk and row["host_id"] in gids) else "wrong"


def main():
    ap = argparse.ArgumentParser()
    for a in ("archive", "ipeds", "lea", "ed_dir", "gold", "out"):
        ap.add_argument("--" + a.replace("_", "-"), dest=a, required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    n_tx, grants = load_grants(args.archive)
    units = load_ipeds(args.ipeds)
    add_distinct(units)
    global UNITS
    UNITS = units
    leas = load_leas(args.lea)
    ed, ed_misses = load_ed_lists(args.ed_dir)
    gold = load_gold(args.gold)
    print(f"transactions {n_tx}  grants {grants.height}  ipeds units {len(units)}  leas {len(leas)}  "
          f"ed rows {len(ed)}  gold {len(gold)}")

    for m in ed_misses:
        print("  ED list:", m)

    uei_map = collections.defaultdict(set)
    for uid, u in units.items():
        for e in u["ueis"]:
            uei_map[e].add(uid)
    col, lea = build_indexes(units, leas)
    col_keys = collections.defaultdict(lambda: collections.defaultdict(set))
    for uid, u in units.items():
        for n in u["names"]:
            col_keys[u["state"]][key(n)].add(uid)
    lea_keys = collections.defaultdict(lambda: collections.defaultdict(set))
    city_leas = collections.defaultdict(set)
    for lid, l in leas.items():
        lea_keys[l["state"]][lea_core(l["name"])].add(lid)
        if l["agency_type"] == "1":
            city_leas[(l["state"], l["city"])].add(lid)

    rows = []
    for g in grants.iter_rows(named=True):
        kind, (outcome, case, hk, hid, cands) = link(g, units, leas, col, lea, uei_map, col_keys, lea_keys, ed, city_leas)
        seen = set()
        # follow IPEDS merges, but only within the state (Mills College -> Northeastern would move the Host to Boston)
        while hk == "UNITID" and units.get(hid, {}).get("merged_into") in units and hid not in seen \
                and units[units[hid]["merged_into"]]["state"] == units[hid]["state"]:
            seen.add(hid)
            hid = units[hid]["merged_into"]
        if seen:
            case += "+followed_ipeds_merge"
        host_name = (units[hid]["name"] if hk == "UNITID" else leas[hid]["name"]) if hid else None
        r = {"fain": g["fain"], "listing": g["cfda_number"], "fain_prefix": g["fain_prefix"], "state": g["state"],
             "recipient_kind": kind, "recipient_name": g["recipient_name"], "ed_name": (ed.get(g["fain"]) or {}).get("ed_name"),
             "outcome": outcome, "case": case, "host_kind": hk, "host_id": hid, "host_name": host_name,
             "candidates": cands, "recipient_city": g["recipient_city_name"], "desc": g["desc_all"][:300]}
        if g["fain"] in gold:
            gd = gold[g["fain"]]
            r.update(gold_type=gd["gold_type"], gold_host=f"{gd['gold_kind']} {'/'.join(sorted(gd['gold_ids']))}",
                     gold_conf=gd["gold_conf"], verdict=score(r, gd))
        rows.append(r)
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_csv(out / "links.csv")
    df.filter(pl.col("outcome").is_in(["review", "unmatched"])).sort("case", "state", "fain").write_csv(out / "review_queue.csv")

    pl.Config.set_tbl_rows(80)
    pl.Config.set_fmt_str_lengths(60)
    print("\n== outcomes over all Grants")
    print(df.group_by("outcome").len().sort("len", descending=True).with_columns((pl.col("len") / df.height * 100).round(1).alias("pct")))
    print("\n== cases")
    print(df.group_by("outcome", "case").len().sort("outcome", "len", descending=[False, True]))
    print("\n== ED list coverage: TRIO Grants with an ED FY2024 row")
    trio = df.filter(pl.col("listing") != "84.334")
    print(f"{trio['ed_name'].is_not_null().sum()} of {trio.height}; ED rows not in USAspending FY2024: {len(set(ed) - set(df['fain']))}")

    gd = df.filter(pl.col("verdict").is_not_null())
    print(f"\n== vs hand labels (n={gd.height}, unweighted)")
    print(gd.group_by("outcome", "verdict").len().sort("outcome", "verdict"))
    print(gd.group_by("gold_type", "verdict").len().pivot(on="verdict", index="gold_type", values="len").fill_null(0).sort("gold_type"))
    bad = gd.filter(pl.col("verdict") == "wrong", pl.col("outcome").is_in(["matched", "no_single_host"]))
    print("\n== auto-accepted but wrong")
    print(bad.select("fain", "gold_type", "recipient_name", "case", "host_id", "host_name", "gold_host"))
    wrong_rev = gd.filter(pl.col("verdict") == "wrong", pl.col("outcome") == "review")
    print("\n== sent to review with a wrong suggestion")
    print(wrong_rev.select("fain", "gold_type", "recipient_name", "case", "host_id", "host_name", "gold_host"))


if __name__ == "__main__":
    main()
