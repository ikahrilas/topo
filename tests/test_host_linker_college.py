"""Seam 2b: the college side of the Host linker (#35), tested directly as a table of cases.

ED list name by exact FAIN, award-description phrases (IPEDS names, former names,
aliases, generated acronyms), campus words checked against sibling campuses only,
address as a tiebreak, IPEDS merges as of the Grant's start year, system offices
and UEI-less Grants. Recipients and campuses follow the prototype taxonomy
(prototypes/host-linking/README.md); UNITIDs and UEIs are fixture values.
"""

from __future__ import annotations

import pytest
from support.ipeds import directory, directory_row

from topo.domain.host_linking import GrantFacts, HostLookups, link_host

IHE = "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"
NONPROFIT = "NONPROFIT WITH 501C3 IRS STATUS (OTHER THAN AN INSTITUTION OF HIGHER EDUCATION)"

LOOKUPS = HostLookups.from_directory(directory(
    # Los Rios CCD: no IPEDS unit carries the district's UEI; ED names the college
    directory_row("109208", "American River College", "CA", city="SACRAMENTO", zip="95841"),
    directory_row("122180", "Sacramento City College", "CA", city="SACRAMENTO", zip="95822"),
    # University of Cincinnati: the UEI points at the main campus; Clermont is a sibling campus
    directory_row("201885", "University of Cincinnati-Main Campus", "OH", ueis=("UCUEI0000001",), city="CINCINNATI"),
    directory_row("201867", "University of Cincinnati-Clermont College", "OH", city="BATAVIA"),
    # Ohio State's UEI; Columbus State is another college in the same city, not a sibling
    directory_row("204796", "Ohio State University-Main Campus", "OH", ueis=("OSUUEI000001",), city="COLUMBUS"),
    directory_row("201645", "Columbus State Community College", "OH", city="COLUMBUS"),
    # UNM Gallup holds its own UEI; the Recipient name is the main campus's
    directory_row("187985", "University of New Mexico-Main Campus", "NM", ueis=("UNMUEI000001",)),
    directory_row("187994", "University of New Mexico-Gallup Campus", "NM", ueis=("UNMGALLUPUEI",)),
    # Wallace: the UEI names Selma, the Recipient name names Dothan
    directory_row("101301", "George C Wallace State Community College-Selma", "AL", ueis=("WALLACEUEI01",),
                  city="SELMA", zip="36702"),
    directory_row("101295", "George Corley Wallace State Community College", "AL", city="DOTHAN", zip="36303"),
    # Minnesota: one UEI covers Twin Cities and Duluth
    directory_row("174066", "University of Minnesota-Twin Cities", "MN", ueis=("UMNUEI000001",), city="MINNEAPOLIS"),
    directory_row("174233", "University of Minnesota-Duluth", "MN", ueis=("UMNUEI000001",), city="DULUTH"),
    # CUNY: the system office carries the Research Foundation's UEI and name
    directory_row("190035", "CUNY System Office", "NY", sector=0, ueis=("CUNYRFUEI001",),
                  alias="Research Foundation of the City University of New York"),
    directory_row("190594", "CUNY City College", "NY", city="NEW YORK"),
    # PennWest: California University of Pennsylvania merged into Pennsylvania Western University in 2022
    *[directory_row("211431", "California University of Pennsylvania", "PA", year=y, ueis=("CALUUEI00001",),
                    newid="482680") for y in range(2015, 2022)],
    *[directory_row("482680", "Pennsylvania Western University", "PA", year=y, ueis=("PENNWESTUEI1",))
      for y in range(2022, 2025)],
    # Mills College merged into Northeastern University (Massachusetts): a survivor across a state line
    *[directory_row("118888", "Mills College", "CA", year=y, ueis=("MILLSUEI0001",), newid="167358")
      for y in range(2015, 2022)],
    directory_row("167358", "Northeastern University", "MA", ueis=("NEUUEI000001",)),
    # Description phrases: a former name, an alias, a generated acronym
    directory_row("120971", "West Hills College Lemoore", "CA", year=2016),
    directory_row("120971", "West Hills Community College-Lemoore", "CA", year=2024, city="LEMOORE"),
    directory_row("202134", "Cuyahoga Community College District", "OH", alias="Tri-C"),
    directory_row("218441", "Horry-Georgetown Technical College", "SC"),
))


def grant(fain, name, state, uei=None, *, ed=None, desc=None, city=None, zip=None, start_year=2022,
          business_types=IHE):
    ed_campus = (ed.partition("/")[2].strip() or None) if ed else None
    return GrantFacts(
        fain=fain, recipient_name=name, recipient_uei=uei, recipient_state=state, business_types=business_types,
        recipient_city=city, recipient_zip=zip, description=desc, ed_recipient_campus=ed, ed_campus=ed_campus,
        start_year=start_year,
    )


LOS_RIOS = "LOS RIOS COMMUNITY COLLEGE DISTRICT"

CASES = {
    # ED list name (exact FAIN) and award-description phrases
    "ed_list_outranks_desc": (
        grant("P042A220001", LOS_RIOS, "CA", "LOSRIOSUEI01",
              ed="American River College", desc="TRIO SSS AT SACRAMENTO CITY COLLEGE"),
        ("matched", "ed_list_outranks_desc", "UNITID", "109208"),
    ),
    "ed_list_and_desc_agree": (
        grant("P042A220002", LOS_RIOS, "CA", "LOSRIOSUEI01", ed="American River College",
              desc="AMERICAN RIVER COLLEGE AND SACRAMENTO CITY COLLEGE PARTNERSHIP"),
        ("matched", "ed_list_and_desc_agree", "UNITID", "109208"),
    ),
    "several_campuses_named": (
        grant("P042A220003", LOS_RIOS, "CA", "LOSRIOSUEI01",
              desc="AMERICAN RIVER COLLEGE AND SACRAMENTO CITY COLLEGE"),
        ("review", "several_campuses_named", None, None),
    ),
    "campus_text_picks_one": (
        grant("P042A220004", "SACRAMENTO CITY COLLEGE", "CA", "SCCUEI000001", ed="American River College"),
        ("matched", "campus_text_picks_one", "UNITID", "109208"),
    ),
    "campus_text_confirmed": (
        grant("P042A220005", LOS_RIOS, "CA", "LOSRIOSUEI01", ed="American River College",
              city="Sacramento", zip="95841-1234"),
        ("matched", "campus_text_confirmed", "UNITID", "109208"),
    ),
    "desc_alone_is_a_weak_signal": (
        grant("P042A220006", LOS_RIOS, "CA", "LOSRIOSUEI01", desc="UPWARD BOUND AT AMERICAN RIVER COLLEGE"),
        ("review", "single_weak_signal:desc", "UNITID", "109208"),
    ),
    # Campus words, checked only against the Recipient's sibling campuses
    "campus_named_overrides_by_ed_campus": (
        grant("P042A220011", "UNIVERSITY OF CINCINNATI", "OH", "UCUEI0000001",
              ed="University of Cincinnati/ Clermont College"),
        ("matched", "campus_named_overrides", "UNITID", "201867"),
    ),
    "campus_named_overrides_by_desc_campus_words": (
        grant("P047A220012", "UNIVERSITY OF CINCINNATI", "OH", "UCUEI0000001", desc="UC CLERMONT UPWARD BOUND"),
        ("matched", "campus_named_overrides", "UNITID", "201867"),
    ),
    "campus_named_where_the_uei_agrees": (
        grant("P047A220013", "UNIVERSITY OF NEW MEXICO", "NM", "UNMGALLUPUEI", desc="UNM GALLUP UPWARD BOUND"),
        ("matched", "campus_named", "UNITID", "187994"),
    ),
    "a_non_sibling_never_overrides_the_uei": (
        grant("P047A220014", "OHIO STATE UNIVERSITY", "OH", "OSUUEI000001",
              desc="UPWARD BOUND AT COLUMBUS STATE COMMUNITY COLLEGE"),
        ("review", "campus_text_overrides_uei", "UNITID", "201645"),
    ),
    # Address breaks ties
    "name_and_address": (
        grant("P042A220021", "SACRAMENTO CITY COLLEGE", "CA", "SCCUEI000001", zip="95822"),
        ("matched", "name_and_address", "UNITID", "122180"),
    ),
    "uei_vs_name_conflict_settled_by_address": (
        grant("P044A220022", "GEORGE CORLEY WALLACE STATE COMMUNITY COLLEGE", "AL", "WALLACEUEI01", city="SELMA"),
        ("matched", "uei_vs_name_conflict", "UNITID", "101301"),
    ),
    "system_campus_by_address": (
        grant("P042A220023", "REGENTS OF THE UNIVERSITY OF MINNESOTA", "MN", "UMNUEI000001", city="DULUTH"),
        ("review", "system_campus_by_address", "UNITID", "174233"),
    ),
    "address_never_finds_a_candidate": (
        grant("P042A220024", "SACRAMENTO STATE COLLEGE PROMISE", "CA", "NOTINIPEDS01", city="SACRAMENTO",
              zip="95822"),
        ("unmatched", "no_candidate_ihe", None, None),
    ),
    # IPEDS merges
    "merged_unit_as_of_the_start_year": (
        grant("P047A200031", "CALIFORNIA UNIVERSITY OF PENNSYLVANIA", "PA", "CALUUEI00001", start_year=2020),
        ("matched", "uei_confirmed+ipeds_unit_as_of_start_year", "UNITID", "211431"),
    ),
    "merged_unit_falls_back_to_the_same_state_survivor": (
        grant("P047A230032", "CALIFORNIA UNIVERSITY OF PENNSYLVANIA", "PA", "CALUUEI00001", start_year=2023),
        ("matched", "uei_confirmed+followed_ipeds_merge", "UNITID", "482680"),
    ),
    "merged_unit_never_follows_a_survivor_across_a_state_line": (
        grant("P042A230033", "MILLS COLLEGE", "CA", "MILLSUEI0001", start_year=2023),
        ("unmatched", "no_candidate_ihe", None, None),
    ),
    # System offices
    "system_office_only_candidate_goes_to_review_even_with_uei_and_name": (
        grant("P047A220041", "RESEARCH FOUNDATION OF THE CITY UNIVERSITY OF NEW YORK", "NY", "CUNYRFUEI001"),
        ("review", "only_candidate_is_system_office", "UNITID", "190035"),
    ),
    "system_office_never_beats_a_campus_named_by_ed": (
        grant("P047A220042", "RESEARCH FOUNDATION OF THE CITY UNIVERSITY OF NEW YORK", "NY", "CUNYRFUEI001",
              ed="CUNY City College", city="NEW YORK"),
        ("matched", "campus_text_confirmed", "UNITID", "190594"),
    ),
    # UEI-less Grants
    "uei_less_match_is_labelled": (
        grant("P042A220051", LOS_RIOS, "CA", None, ed="American River College", zip="95841"),
        ("matched", "campus_text_confirmed+no_uei", "UNITID", "109208"),
    ),
    "uei_less_unmatched_is_labelled": (
        grant("P042A220052", "PALO VERDE COLLEGE FINANCING CORPORATION", "CA", None),
        ("unmatched", "no_candidate_ihe+no_uei", None, None),
    ),
    "uei_less_no_single_host_keeps_its_rule_label": (
        grant("P044A220053", "COLLEGE ACCESS NOW", "CA", None, business_types=NONPROFIT),
        ("no_single_host", "nonprofit_no_site_named", None, None),
    ),
}


@pytest.mark.parametrize("case", list(CASES))
def test_college_linker_case_table(case):
    facts, (outcome, case_label, host_kind, host_id) = CASES[case]

    link = link_host(facts, LOOKUPS)

    assert (link.outcome, link.case_label, link.host_kind, link.host_id) == (outcome, case_label, host_kind, host_id)


def candidates(link):
    return {(c.host_id, c.signals) for c in link.candidates}


def test_address_only_tags_candidates_already_found():
    link = link_host(CASES["name_and_address"][0], LOOKUPS)
    assert candidates(link) == {("122180", ("address", "name"))}
    assert link_host(CASES["address_never_finds_a_candidate"][0], LOOKUPS).candidates == ()


def test_ed_text_and_campus_words_are_signals_on_the_candidates():
    link = link_host(CASES["campus_named_overrides_by_ed_campus"][0], LOOKUPS)
    assert candidates(link) == {("201885", ("name", "uei")), ("201867", ("ed_campus", "ed_list"))}


def test_campus_words_never_reach_a_non_sibling():
    # 'CLERMONT' names a Cincinnati campus, but the Recipient is Ohio State: no campus signal.
    link = link_host(grant("P047A220015", "OHIO STATE UNIVERSITY", "OH", "OSUUEI000001",
                           desc="CLERMONT COUNTY UPWARD BOUND"), LOOKUPS)
    assert (link.outcome, link.case_label, link.host_id) == ("matched", "uei_confirmed", "204796")
    assert candidates(link) == {("204796", ("name", "uei"))}


@pytest.mark.parametrize("desc, state, unitid", [
    ("SSS AT WEST HILLS COLLEGE LEMOORE", "CA", "120971"),  # a former name
    ("TRI-C UPWARD BOUND", "OH", "202134"),  # an IPEDS alias
    ("HGTC TALENT SEARCH", "SC", "218441"),  # a generated acronym
])
def test_description_phrases_find_former_names_aliases_and_acronyms(desc, state, unitid):
    link = link_host(grant("P044A220061", "COLLEGE ACCESS NOW", state, None, desc=desc, business_types=NONPROFIT),
                     LOOKUPS)
    assert candidates(link) == {(unitid, ("desc",))}


def test_description_phrases_stay_in_the_recipient_state():
    link = link_host(grant("P044A220062", "COLLEGE ACCESS NOW", "NV", None, desc="HGTC TALENT SEARCH",
                           business_types=NONPROFIT), LOOKUPS)
    assert link.candidates == ()


def test_a_merge_survivor_carries_the_signals():
    link = link_host(CASES["merged_unit_falls_back_to_the_same_state_survivor"][0], LOOKUPS)
    assert link.host_name == "Pennsylvania Western University"
    assert candidates(link) == {("482680", ("name", "uei"))}
