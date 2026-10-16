"""Answer-key gating and overrides: what happens to Host links after the rules (ADR 0002).

The rule cascade (`topo.domain.host_linking`) decides each Grant and names the
deciding rule in its Case label. Two steps follow, in this order:

1. **Gating.** Each Case label is scored against the frozen answer key: a check
   is an answer-key FAIN the label decided in this run, and it is correct when the
   rule's decision (its Host, or "no single Host") equals the key's. A label that
   decides automatically (outcome `matched` or `no_single_host`) is

       auto-accepted       accuracy >= the bar with >= the minimum checks
       demoted to review   >= the minimum checks, accuracy below the bar
       unverified          fewer checks than the minimum; the rule's outcome stands
                           (ASSUMPTION: an empty key must not empty the target list)

   Every label under the minimum reports "unverified". Review and unmatched labels
   decide nothing automatically, so with enough checks they are scored but "not gated". The bar and the minimum come from `[host_linking]` in config.
   Only the answer key is scored here; the tuning set never is.

2. **Overrides.** A reviewer's decision (FAIN -> Host, reviewer, date, note) wins
   over the rules and the gating. The latest-dated override for a FAIN applies.
   An overridden link has outcome `matched` (or `no_single_host`) and Case label
   `override`; the rule's outcome and label are kept beside it.

Both steps are pure: frames in, frames out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

import pandera.polars as pa
import polars as pl

from topo.domain.host_linking import HOST_CONFIDENCE, LEAID, MATCHED, NO_SINGLE_HOST, REVIEW, UNITID
from topo.guards import StructuralBreak, check_schema

AUTO_ACCEPTED = "auto-accepted"
DEMOTED = "demoted to review"
UNVERIFIED = "unverified"
NOT_GATED = "not gated"
OVERRIDDEN = "override"
GATING = (AUTO_ACCEPTED, DEMOTED, UNVERIFIED, NOT_GATED, OVERRIDDEN)

OVERRIDE_CASE_LABEL = "override"
NO_SINGLE_HOST_VALUE = "no single Host"  # the curated-file spelling of "no single Host"
GATED_OUTCOMES = (MATCHED, NO_SINGLE_HOST)  # outcomes a rule reaches without a person

# "UNITID 180595", "LEAID 0100005" or "no single Host", as the target list shows Hosts.
HOST_VALUE = re.compile(rf"^(({UNITID}|{LEAID}) [0-9A-Za-z]+|{NO_SINGLE_HOST_VALUE})$")


@dataclass(frozen=True)
class Gate:
    """The auto-accept bar: accuracy at least `accuracy` with at least `min_checks` checks."""

    accuracy: float
    min_checks: int

    @classmethod
    def from_section(cls, section: Mapping) -> "Gate":
        return cls(float(section["auto_accept_accuracy"]), int(section["auto_accept_min_checks"]))

    def judge(self, rule_outcome: str, checks: int, accuracy: float | None) -> str:
        if checks < self.min_checks or accuracy is None:
            return UNVERIFIED
        if rule_outcome not in GATED_OUTCOMES:
            return NOT_GATED
        return AUTO_ACCEPTED if accuracy >= self.accuracy else DEMOTED


# ------------------------------------------------------------ curated frames


class HostAnswerKey(pa.DataFrameModel):
    """The frozen answer key, or the separate tuning set (same format): one true Host per FAIN.

    `host` is the primary label, the only one scored. A double-labelled row also carries a
    second reviewer's `second_host`, read only to report inter-rater agreement.
    """

    fain: str = pa.Field(unique=True)
    host: str = pa.Field(str_matches=HOST_VALUE.pattern)
    reviewer: str
    labelled_on: str = pa.Field(str_matches=r"^\d{4}-\d{2}-\d{2}$")
    note: str = pa.Field(nullable=True)
    second_host: str = pa.Field(nullable=True, str_matches=HOST_VALUE.pattern)
    second_reviewer: str = pa.Field(nullable=True)

    class Config:
        strict = True

    @pa.dataframe_check
    def second_label_names_its_reviewer(cls, data) -> pl.LazyFrame:
        return data.lazyframe.select(pl.col("second_host").is_null() | pl.col("second_reviewer").is_not_null())


class HostOverrides(pa.DataFrameModel):
    """Reviewed decisions, FAIN -> Host. A FAIN may have several dated rows; the latest wins."""

    fain: str
    host: str = pa.Field(str_matches=HOST_VALUE.pattern)
    reviewer: str
    date: str = pa.Field(str_matches=r"^\d{4}-\d{2}-\d{2}$")
    note: str = pa.Field(nullable=True)

    class Config:
        strict = True
        unique = ["fain", "date"]


# ------------------------------------------------------------- joined frames


class CaseLabelAccuracy(pa.DataFrameModel):
    """One row per Case label: how often it decides, how it scored on the answer key, and its gating."""

    case_label: str = pa.Field(unique=True)
    rule_outcome: str = pa.Field(isin=list(HOST_CONFIDENCE))
    links: int  # Grants this label decided in the run
    checks: int  # of those, answer-key FAINs
    correct: int
    accuracy: float = pa.Field(nullable=True)
    gating: str = pa.Field(isin=list(GATING))

    class Config:
        strict = True


class GatedHostLinks(pa.DataFrameModel):
    """Host links after gating and overrides: one per FAIN, with the rule's own decision kept."""

    fain: str = pa.Field(unique=True)
    outcome: str = pa.Field(isin=list(HOST_CONFIDENCE))
    case_label: str
    host_kind: str = pa.Field(nullable=True, isin=[UNITID, LEAID])
    host_id: str = pa.Field(nullable=True)
    host_name: str = pa.Field(nullable=True)
    host_confidence: str = pa.Field(isin=list(HOST_CONFIDENCE.values()))
    followed_ipeds_merge: bool
    unit_as_of_start_year: bool
    no_uei: bool
    rule_outcome: str = pa.Field(isin=list(HOST_CONFIDENCE))
    rule_case_label: str
    gating: str = pa.Field(isin=list(GATING))
    override_reviewer: str = pa.Field(nullable=True)
    override_date: str = pa.Field(nullable=True)
    override_note: str = pa.Field(nullable=True)

    class Config:
        strict = True


def _decision() -> pl.Expr:
    """A link's decision in curated spelling: its Host, "no single Host", or null (no decision)."""
    return (
        pl.when(pl.col("outcome") == NO_SINGLE_HOST)
        .then(pl.lit(NO_SINGLE_HOST_VALUE))
        .when(pl.col("host_id").is_not_null())
        .then(pl.concat_str("host_kind", pl.lit(" "), "host_id"))
        .otherwise(pl.lit(None, dtype=pl.String))
    )


def score_case_labels(rule_links: pl.DataFrame, answer_key: pl.DataFrame, gate: Gate) -> pl.DataFrame:
    """Accuracy and gating per Case label, from the rule links (before overrides) and the answer key."""
    scored = rule_links.with_columns(_decision().alias("decision")).join(
        answer_key.select("fain", pl.col("host").alias("key_host")), on="fain", how="left"
    )
    per_label = (
        scored.group_by("case_label")
        .agg(
            # A label that decides any row automatically is gated as such (per row, below);
            # each label should map to one outcome, but a mix must never slip past the gate.
            pl.col("outcome").filter(pl.col("outcome").is_in(GATED_OUTCOMES)).first()
            .fill_null(pl.col("outcome").first()).alias("rule_outcome"),
            pl.len().cast(pl.Int64).alias("links"),
            pl.col("key_host").is_not_null().sum().cast(pl.Int64).alias("checks"),
            (pl.col("key_host").is_not_null() & (pl.col("decision") == pl.col("key_host")).fill_null(False))
            .sum()
            .cast(pl.Int64)
            .alias("correct"),
        )
        .with_columns(
            pl.when(pl.col("checks") > 0).then(pl.col("correct") / pl.col("checks")).alias("accuracy")
        )
        .sort("case_label")
    )
    gating = [gate.judge(o, c, a) for o, c, a in per_label.select("rule_outcome", "checks", "accuracy").iter_rows()]
    frame = per_label.with_columns(pl.Series("gating", gating, dtype=pl.String)).select(
        list(CaseLabelAccuracy.to_schema().columns)
    )
    return check_schema(CaseLabelAccuracy, frame, "Case label accuracy")


def gate_host_links(rule_links: pl.DataFrame, accuracy: pl.DataFrame) -> pl.DataFrame:
    """Apply each Case label's gating per row: every auto-accepted row (matched or no single
    Host) of a demoted label goes to review (its pick, if any, stays shown)."""
    # A label the accuracy table hasn't seen (on lookback Grants, say) has no checks: unverified.
    gated = rule_links.join(accuracy.select("case_label", "gating"), on="case_label", how="left").with_columns(
        pl.col("gating").fill_null(UNVERIFIED)
    )
    demoted = (pl.col("gating") == DEMOTED) & pl.col("outcome").is_in(GATED_OUTCOMES)
    outcome = pl.when(demoted).then(pl.lit(REVIEW)).otherwise(pl.col("outcome"))
    return gated.with_columns(
        pl.col("outcome").alias("rule_outcome"),
        pl.col("case_label").alias("rule_case_label"),
        outcome.alias("outcome"),
    ).with_columns(pl.col("outcome").replace_strict(HOST_CONFIDENCE).alias("host_confidence"))


def latest_overrides(overrides: pl.DataFrame) -> pl.DataFrame:
    """The override in force for each FAIN: its latest-dated row."""
    return overrides.sort("fain", "date").group_by("fain", maintain_order=True).last()


def apply_overrides(
    gated: pl.DataFrame, overrides: pl.DataFrame, host_names: Mapping[tuple[str, str], str]
) -> pl.DataFrame:
    """Overrides win after the rules and the gating. Unreviewed links are left as they are."""
    in_force = latest_overrides(overrides).select(
        "fain",
        pl.col("host").alias("override_host"),
        pl.col("reviewer").alias("override_reviewer"),
        pl.col("date").alias("override_date"),
        pl.col("note").alias("override_note"),
    )
    joined = gated.join(in_force, on="fain", how="left")
    has = pl.col("override_host").is_not_null()
    nsh = pl.col("override_host") == NO_SINGLE_HOST_VALUE
    kind = pl.col("override_host").str.split(" ").list.first()
    host_id = pl.col("override_host").str.split(" ").list.last()
    out = joined.with_columns(
        pl.when(has).then(pl.when(nsh).then(pl.lit(NO_SINGLE_HOST)).otherwise(pl.lit(MATCHED)))
        .otherwise(pl.col("outcome")).alias("outcome"),
        pl.when(has).then(pl.lit(OVERRIDE_CASE_LABEL)).otherwise(pl.col("case_label")).alias("case_label"),
        pl.when(has).then(pl.lit(OVERRIDDEN)).otherwise(pl.col("gating")).alias("gating"),
        pl.when(has).then(pl.when(nsh).then(None).otherwise(kind)).otherwise(pl.col("host_kind")).alias("host_kind"),
        pl.when(has).then(pl.when(nsh).then(None).otherwise(host_id)).otherwise(pl.col("host_id")).alias("host_id"),
    )
    names = [
        host_names.get((k, i)) if o is not None and k is not None else n
        for o, k, i, n in out.select("override_host", "host_kind", "host_id", "host_name").iter_rows()
    ]
    out = out.with_columns(
        pl.Series("host_name", names, dtype=pl.String),
        pl.col("outcome").replace_strict(HOST_CONFIDENCE).alias("host_confidence"),
    ).select(list(GatedHostLinks.to_schema().columns))
    return check_schema(GatedHostLinks, out.sort("fain"), "Gated Host links")


def check_separate(answer_key: pl.DataFrame, tuning_set: pl.DataFrame) -> None:
    """The answer key is never tuned against: no FAIN may sit in both it and the tuning set."""
    shared = sorted(set(answer_key["fain"]) & set(tuning_set["fain"]))
    if shared:
        raise StructuralBreak(
            f"{len(shared)} FAINs are in both the frozen answer key and the tuning set: {', '.join(shared[:10])}"
        )


def gate_and_override(
    rule_links: pl.DataFrame,
    answer_key: pl.DataFrame,
    overrides: pl.DataFrame,
    gate: Gate,
    host_names: Mapping[tuple[str, str], str],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Rule links -> (final Host links, Case label accuracy). Gating first, overrides last."""
    accuracy = score_case_labels(rule_links, answer_key, gate)
    links = apply_overrides(gate_host_links(rule_links, accuracy), overrides, host_names)
    if links.height != rule_links.height:
        raise StructuralBreak(f"gating changed the Host-link count: {rule_links.height} -> {links.height}")
    return links, accuracy
