"""Seam 2b: the Host linker, tested directly as a table of cases.

Cases are drawn from the host-linking prototype taxonomy
(prototypes/host-linking/README.md, links.csv): real Recipients and UNITIDs,
with a fixture IPEDS directory standing in for Urban's bulk CSV.
"""

from __future__ import annotations

import pytest
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
        ("unmatched", "no_candidate_gearup_partnership", None, None),
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
