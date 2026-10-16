"""Seam 2b: the Host linker, tested directly as a table of cases.

Cases are drawn from the host-linking prototype taxonomy
(prototypes/host-linking/README.md, links.csv): real Recipients and UNITIDs,
with a fixture IPEDS directory standing in for Urban's bulk CSV.
"""

from __future__ import annotations

import pytest
from support.ccd import lea_directory, lea_row
from support.fac import cleaned_audits
from support.ipeds import directory, directory_row

from topo.domain.host_linking import GrantFacts, HostLookups, link_host

IHE_PUBLIC = "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"
NONPROFIT = "NONPROFIT WITH 501C3 IRS STATUS (OTHER THAN AN INSTITUTION OF HIGHER EDUCATION)"
STATE_GOV = "STATE GOVERNMENT"

LOOKUPS = HostLookups.from_directory(directory(
    # Rocky Mountain College, MT: one UEI, one campus (uei_confirmed)
    directory_row("180595", "Rocky Mountain College", "MT", ueis=("RMCUEI000001",)),
    # NC A&T: the IPEDS name differs from the Recipient's legal name (uei_only)
    directory_row("199102", "North Carolina A & T State University", "NC", ueis=("NCATUEI00001",)),
    # Regents of the University of Minnesota: one UEI covers Twin Cities and Duluth
    directory_row("174066", "University of Minnesota-Twin Cities", "MN", ueis=("UMNUEI000001",)),
    directory_row("174233", "University of Minnesota-Duluth", "MN", ueis=("UMNUEI000001",)),
    # Wallace State-Selma has the UEI; the Recipient's name is a different Wallace campus
    directory_row("101301", "George C Wallace State Community College-Selma", "AL", ueis=("WALLACEUEI01",)),
    directory_row("101295", "George Corley Wallace State Community College", "AL", ueis=("OTHERUEI0001",)),
    # Chico State Enterprises (a nonprofit) shares CSU Chico's UEI
    directory_row("110538", "California State University-Chico", "CA", ueis=("CHICOUEI0001",)),
    # CUNY System Office (sector 0) is the only name candidate
    directory_row("190035", "CUNY System Office", "NY", sector=0, alias="Research Foundation of the City University of New York"),
    # A UEI registered to a Texas campus: a Recipient in Oklahoma with that UEI must never link to it
    directory_row("228778", "The University of Texas at Austin", "TX", ueis=("CROSSSTATE01",)),
    # PASSHE's UEI points at a campus, but GEAR UP State has no single Host
    directory_row("214661", "Kutztown University of Pennsylvania", "PA", ueis=("PASSHEUEI001",)),
    # A former name: the unit was renamed after 2015
    directory_row("120971", "West Hills College Lemoore", "CA", year=2016, ueis=()),
    directory_row("120971", "West Hills Community College-Lemoore", "CA", year=2024, ueis=("WHCLUEI00001",)),
))


def grant(fain, name, state, uei=None, business_types=IHE_PUBLIC):
    return GrantFacts(fain=fain, recipient_name=name, recipient_uei=uei, recipient_state=state,
                      business_types=business_types)


CASES = {
    "uei_confirmed": (
        grant("P042A150321", "ROCKY MOUNTAIN COLLEGE", "MT", "RMCUEI000001"),
        ("matched", "uei_confirmed", "UNITID", "180595"),
    ),
    "uei_confirmed_by_a_former_name": (
        grant("P042A200001", "WEST HILLS COLLEGE LEMOORE", "CA", "WHCLUEI00001"),
        ("matched", "uei_confirmed", "UNITID", "120971"),
    ),
    "uei_only": (
        grant("P042A200479", "NORTH CAROLINA AGRICULTURAL AND TECHNICAL STATE UNIVERSITY", "NC", "NCATUEI00001"),
        ("matched", "uei_only", "UNITID", "199102"),
    ),
    "uei_only_non_college": (
        grant("P047M170193", "CHICO STATE ENTERPRISES", "CA", "CHICOUEI0001", NONPROFIT),
        ("review", "uei_only_non_college", "UNITID", "110538"),
    ),
    "system_campus_not_stated": (
        grant("P042A160173", "REGENTS OF THE UNIVERSITY OF MINNESOTA", "MN", "UMNUEI000001"),
        ("review", "system_campus_not_stated", None, None),
    ),
    "uei_vs_name_conflict": (
        grant("P044A160594", "GEORGE CORLEY WALLACE STATE COMMUNITY COLLEGE", "AL", "WALLACEUEI01"),
        ("review", "uei_vs_name_conflict", "UNITID", "101301"),
    ),
    "only_candidate_is_system_office": (
        grant("P047A170566", "RESEARCH FOUNDATION OF THE CITY UNIVERSITY OF NEW YORK", "NY", "CUNYRFUEI001"),
        ("review", "only_candidate_is_system_office", "UNITID", "190035"),
    ),
    "single_weak_signal_name": (
        grant("P042A200002", "GEORGE CORLEY WALLACE STATE COMMUNITY COLLEGE", "AL", None),
        ("review", "single_weak_signal:name", "UNITID", "101295"),
    ),
    "gearup_state": (
        grant("P334S140007", "PENNSYLVANIA STATE SYSTEM OF HIGHER EDUCATION", "PA", "PASSHEUEI001", STATE_GOV),
        ("no_single_host", "gearup_state", None, None),
    ),
    "state_agency_no_site_named": (
        grant("P044A220078", "VERMONT STUDENT ASSISTANCE CORPORATION", "VT", "VSACUEI00001", STATE_GOV),
        ("no_single_host", "state_agency_no_site_named", None, None),
    ),
    "nonprofit_no_site_named": (
        grant("P044A170183", "MASSACHUSETTS HIGHER EDUCATION ASSISTANCE CORPORATION", "MA", "MHEACUEI0001", NONPROFIT),
        ("no_single_host", "nonprofit_no_site_named", None, None),
    ),
    "unmatched_college": (
        grant("P042A201159", "PALO VERDE COMMUNITY COLLEGE DISTRICT FINANCING CORPORATION", "CA", "PVUEI0000001",
              "PUBLIC/STATE CONTROLLED INSTITUTION OF HIGHER EDUCATION"),
        ("unmatched", "no_candidate_ihe", None, None),
    ),
    "unmatched_district": (
        grant("P044A210178", "NORTHWEST TRI COUNTY INTERMEDIATE UNIT", "PA", "NWTCIUUEI001", "INDEPENDENT SCHOOL DISTRICT"),
        ("unmatched", "no_candidate_lea", None, None),
    ),
    "cross_state_uei_never_links": (
        grant("P042A200003", "OKLAHOMA COLLEGE", "OK", "CROSSSTATE01"),
        ("unmatched", "no_candidate_ihe", None, None),
    ),
    "gearup_partnership_college_partner_is_never_the_host": (
        grant("P334A180001", "ROCKY MOUNTAIN COLLEGE", "MT", "RMCUEI000001"),
        ("no_single_host", "gearup_partnership_no_district_named", None, None),
    ),
}


@pytest.mark.parametrize("case", list(CASES))
def test_linker_case_table(case):
    facts, (outcome, case_label, host_kind, host_id) = CASES[case]

    link = link_host(facts, LOOKUPS)

    assert (link.outcome, link.case_label, link.host_kind, link.host_id) == (outcome, case_label, host_kind, host_id)
    assert link.fain == facts.fain


def test_a_match_names_its_host():
    link = link_host(CASES["uei_confirmed"][0], LOOKUPS)
    assert link.host_name == "Rocky Mountain College"
    assert [(c.host_kind, c.host_id, c.signals) for c in link.candidates] == [("UNITID", "180595", ("name", "uei"))]


def test_review_carries_every_candidate_with_its_signals():
    link = link_host(CASES["system_campus_not_stated"][0], LOOKUPS)
    assert {(c.host_id, c.host_name, c.signals) for c in link.candidates} == {
        ("174066", "University of Minnesota-Twin Cities", ("uei",)),
        ("174233", "University of Minnesota-Duluth", ("uei",)),
    }
    conflict = link_host(CASES["uei_vs_name_conflict"][0], LOOKUPS)
    assert {(c.host_id, c.signals) for c in conflict.candidates} == {("101301", ("uei",)), ("101295", ("name",))}


@pytest.mark.parametrize("case", [c for c, (_, expected) in CASES.items() if expected[0] == "unmatched"])
def test_unmatched_carries_no_candidates(case):
    link = link_host(CASES[case][0], LOOKUPS)
    assert link.candidates == ()
    assert link.host_id is None


def test_a_cross_state_candidate_is_never_a_candidate():
    # Same UEI and same name as UT Austin, but the Recipient is in Oklahoma.
    link = link_host(grant("P042A200004", "THE UNIVERSITY OF TEXAS AT AUSTIN", "OK", "CROSSSTATE01"), LOOKUPS)
    assert link.outcome == "unmatched"
    assert link.candidates == ()


def test_a_system_office_never_beats_a_real_campus():
    lookups = HostLookups.from_directory(directory(
        directory_row("190035", "CUNY System Office", "NY", sector=0, ueis=("CUNYUEI00001",)),
        directory_row("190594", "CUNY City College", "NY", ueis=("CUNYUEI00001",)),
    ))
    link = link_host(grant("P042A200005", "CUNY CITY COLLEGE", "NY", "CUNYUEI00001"), lookups)
    assert (link.outcome, link.case_label, link.host_id) == ("matched", "uei_confirmed", "190594")
    assert [c.host_id for c in link.candidates] == ["190594"]


def test_no_single_host_is_distinct_from_unmatched():
    outcomes = {link_host(facts, LOOKUPS).outcome for facts, _ in CASES.values()}
    assert {"matched", "review", "no_single_host", "unmatched"} <= outcomes


# ------------------------------------------------- GEAR UP partnership districts (#36)
# A partnership's Host is the district it serves, named in the award description or
# being the Recipient itself; never the college partner. CCD LEA directory fixtures.

DISTRICTS = HostLookups.from_directory(
    directory(
        directory_row("228796", "The University of Texas at El Paso", "TX", ueis=("UTEPUEI00001",)),
        directory_row("230038", "Weber State University", "UT", ueis=("WEBERUEI0001",)),
    ),
    lea_directory(
        lea_row("4840860", "Socorro Independent School District", "TX"),
        lea_row("4818300", "El Paso Independent School District", "TX"),
        lea_row("4900630", "Ogden City School District", "UT"),
        # A same-named district across a state line must never be a candidate
        lea_row("1600001", "Ogden School District", "ID"),
        # Two Utah districts share the core name "Jordan": one mention can't pick between them
        lea_row("4900420", "Jordan School District", "UT"),
        lea_row("4900421", "Jordan Public Schools", "UT"),
        # A renamed district: the 2016 name still finds it
        lea_row("4800002", "Ysleta ISD", "TX", year=2016),
        lea_row("4800002", "Ysleta Independent School District", "TX", year=2024),
    ),
)
SCHOOL_DISTRICT = "INDEPENDENT SCHOOL DISTRICT"


def partnership(fain, name, state, *descriptions, uei=None, business_types=IHE_PUBLIC):
    return GrantFacts(fain=fain, recipient_name=name, recipient_uei=uei, recipient_state=state,
                      business_types=business_types, descriptions=descriptions)


DISTRICT_CASES = {
    "district_named_in_desc": (
        partnership("P334A210001", "UNIVERSITY OF TEXAS AT EL PASO", "TX",
                    "GEAR UP PARTNERSHIP SERVING SOCORRO INDEPENDENT SCHOOL DISTRICT", uei="UTEPUEI00001"),
        ("matched", "district_named_in_desc", "LEAID", "4840860"),
    ),
    "district_named_by_a_short_form": (
        partnership("P334A210002", "UNIVERSITY OF TEXAS AT EL PASO", "TX", "PROJECT ADVANCE - SOCORRO ISD COHORT"),
        ("matched", "district_named_in_desc", "LEAID", "4840860"),
    ),
    "district_named_by_a_former_name": (
        partnership("P334A210003", "UNIVERSITY OF TEXAS AT EL PASO", "TX", "GEAR UP YSLETA ISD"),
        ("matched", "district_named_in_desc", "LEAID", "4800002"),
    ),
    "district_is_recipient": (
        partnership("P334A210004", "BOARD OF EDUCATION OF OGDEN CITY", "UT", "GEAR UP PARTNERSHIP",
                    business_types=SCHOOL_DISTRICT),
        ("matched", "district_is_recipient", "LEAID", "4900630"),
    ),
    "district_recipient_named_again_in_desc": (
        partnership("P334A210005", "OGDEN CITY SCHOOL DISTRICT", "UT", "OGDEN SCHOOL DISTRICT GEAR UP",
                    business_types=SCHOOL_DISTRICT),
        ("matched", "district_is_recipient", "LEAID", "4900630"),
    ),
    "gearup_partnership_no_district_named": (
        partnership("P334A210006", "WEBER STATE UNIVERSITY", "UT", "GEAR UP PARTNERSHIP PROJECT", uei="WEBERUEI0001"),
        ("no_single_host", "gearup_partnership_no_district_named", None, None),
    ),
    "several_districts_named": (
        partnership("P334A210007", "UNIVERSITY OF TEXAS AT EL PASO", "TX",
                    "GEAR UP: SOCORRO ISD AND EL PASO INDEPENDENT SCHOOL DISTRICT"),
        ("no_single_host", "several_districts_named", None, None),
    ),
    "district_name_ambiguous": (
        partnership("P334A210008", "WEBER STATE UNIVERSITY", "UT", "GEAR UP JORDAN SCHOOLS"),
        ("review", "district_name_ambiguous", None, None),
    ),
    "cross_state_district_never_named": (
        partnership("P334A210009", "WEBER STATE UNIVERSITY", "ID", "GEAR UP SOCORRO INDEPENDENT SCHOOL DISTRICT"),
        ("no_single_host", "gearup_partnership_no_district_named", None, None),
    ),
}


@pytest.mark.parametrize("case", list(DISTRICT_CASES))
def test_gear_up_partnership_district_policy(case):
    facts, (outcome, case_label, host_kind, host_id) = DISTRICT_CASES[case]

    link = link_host(facts, DISTRICTS)

    assert (link.outcome, link.case_label, link.host_kind, link.host_id) == (outcome, case_label, host_kind, host_id)


@pytest.mark.parametrize("case", list(DISTRICT_CASES))
def test_a_partnerships_college_partner_is_never_a_candidate(case):
    link = link_host(DISTRICT_CASES[case][0], DISTRICTS)
    assert all(c.host_kind == "LEAID" for c in link.candidates)


def test_a_district_host_carries_its_name_and_signals():
    link = link_host(DISTRICT_CASES["district_named_in_desc"][0], DISTRICTS)
    assert link.host_name == "Socorro Independent School District"
    assert [(c.host_kind, c.host_id, c.signals) for c in link.candidates] == [("LEAID", "4840860", ("desc",))]
    recipient = link_host(DISTRICT_CASES["district_recipient_named_again_in_desc"][0], DISTRICTS)
    assert [(c.host_id, c.signals) for c in recipient.candidates] == [("4900630", ("desc", "name"))]


def test_several_named_districts_are_all_kept_as_candidates():
    link = link_host(DISTRICT_CASES["several_districts_named"][0], DISTRICTS)
    assert {c.host_id for c in link.candidates} == {"4840860", "4818300"}
    ambiguous = link_host(DISTRICT_CASES["district_name_ambiguous"][0], DISTRICTS)
    assert {c.host_id for c in ambiguous.candidates} == {"4900420", "4900421"}


def test_a_district_in_another_state_is_never_a_candidate():
    # "Ogden School District" exists in Idaho; the Utah Recipient's description names Ogden.
    link = link_host(partnership("P334A210010", "WEBER STATE UNIVERSITY", "UT", "GEAR UP OGDEN SCHOOL DISTRICT"),
                     DISTRICTS)
    assert (link.outcome, link.host_id) == ("matched", "4900630")
    assert {c.host_id for c in link.candidates} == {"4900630"}


def test_districts_are_looked_up_only_for_gear_up_partnerships():
    # A TRIO Grant whose description names a district still links by college rules.
    link = link_host(partnership("P042A210011", "WEBER STATE UNIVERSITY", "UT", "OGDEN CITY SCHOOL DISTRICT",
                                 uei="WEBERUEI0001"), DISTRICTS)
    assert (link.outcome, link.case_label, link.host_kind, link.host_id) == (
        "matched", "uei_confirmed", "UNITID", "230038",
    )


# ------------------------------------------------- FAC auditee UEIs (spec #28: "IPEDS UEIs plus FAC")
# A Recipient UEI that no same-state IPEDS unit lists may be a FAC auditee UEI; the auditee's name
# then names a same-state IPEDS unit. A modest signal: it never overrides an IPEDS UEI and never
# crosses a state line.

FAC_LOOKUPS = HostLookups.from_directory(
    directory(
        directory_row("145600", "Northeastern Illinois University", "IL", ueis=("NEIUIPEDS001",)),
        directory_row("145619", "Chicago State University", "IL"),
        directory_row("228778", "The University of Texas at Austin", "TX"),
    ),
    fac_audits=cleaned_audits(
        ("CSUFACUEI001", "Chicago State University", "IL"),
        ("NEIUIPEDS001", "Chicago State University", "IL"),  # contradicts IPEDS: IPEDS wins
        ("UTFACUEI0001", "The University of Texas at Austin", "TX"),
    ),
)


def test_a_fac_auditee_uei_names_a_same_state_unit_and_confirms_the_recipient_name():
    link = link_host(grant("P042A220101", "CHICAGO STATE UNIVERSITY", "IL", "CSUFACUEI001"), FAC_LOOKUPS)
    assert (link.outcome, link.case_label, link.host_id) == ("matched", "fac_uei_confirmed", "145619")
    assert [c.signals for c in link.candidates] == [("fac_uei", "name")]


def test_a_fac_auditee_uei_alone_is_a_weak_signal():
    link = link_host(grant("P042A220102", "BOARD OF TRUSTEES CSU", "IL", "CSUFACUEI001"), FAC_LOOKUPS)
    assert (link.outcome, link.case_label, link.host_id) == ("review", "single_weak_signal:fac_uei", "145619")


def test_a_fac_auditee_uei_never_overrides_an_ipeds_uei():
    link = link_host(grant("P042A220103", "NORTHEASTERN ILLINOIS UNIVERSITY", "IL", "NEIUIPEDS001"), FAC_LOOKUPS)
    assert (link.outcome, link.case_label, link.host_id) == ("matched", "uei_confirmed", "145600")
    assert {c.host_id for c in link.candidates} == {"145600"}


def test_a_fac_auditee_in_another_state_is_never_a_signal():
    link = link_host(grant("P042A220104", "UT AUSTIN TRIO", "OK", "UTFACUEI0001"), FAC_LOOKUPS)
    assert (link.outcome, link.candidates) == ("unmatched", ())
