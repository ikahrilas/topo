"""Seam 2c: answer-key gating, tested directly on rule links (frames in, frames out)."""

from __future__ import annotations

import polars as pl

from topo.domain.host_gating import Gate, gate_and_override

GATE = Gate(accuracy=0.95, min_checks=2)
EMPTY_OVERRIDES = pl.DataFrame(schema={c: pl.String for c in ("fain", "host", "reviewer", "date", "note")})


def link(fain: str, outcome: str, case_label: str, host_id: str | None) -> dict:
    return {
        "fain": fain, "outcome": outcome, "case_label": case_label,
        "host_kind": "UNITID" if host_id else None, "host_id": host_id, "host_name": "College" if host_id else None,
        "host_confidence": {"matched": "matched", "review": "in review"}[outcome],
    }


def key(*rows: tuple[str, str]) -> pl.DataFrame:
    return pl.DataFrame(
        [{"fain": f, "host": h, "reviewer": "owner", "labelled_on": "2026-09-01", "note": None}
         for f, h in rows],
        schema={c: pl.String for c in ("fain", "host", "reviewer", "labelled_on", "note")},
    )


def test_a_demoted_label_demotes_every_auto_accepted_row_even_when_some_rows_were_review():
    # One label that came out both review and matched: the review row must not hide the matched rows from gating.
    rules = pl.DataFrame([
        link("P042A250001", "review", "mixed_label", "100001"),
        link("P042A250002", "matched", "mixed_label", "100002"),
        link("P042A250003", "matched", "mixed_label", "100003"),
    ])
    answer_key = key(("P042A250002", "UNITID 999999"), ("P042A250003", "UNITID 999998"))

    links, accuracy = gate_and_override(rules, answer_key, EMPTY_OVERRIDES, GATE, {})

    assert accuracy.row(0, named=True)["gating"] == "demoted to review"
    assert dict(links.select("fain", "outcome").iter_rows()) == {
        "P042A250001": "review", "P042A250002": "review", "P042A250003": "review",
    }
