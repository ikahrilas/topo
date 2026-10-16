# Education Funding & Market Intelligence Hub

A public-data view of who holds federal TRIO and GEAR UP money, where, for how long, and in what local context, built for Elevated Minds to find and time its outreach. Organization-level only; no individuals.

## Grant structure

**Recipient**:
The legal entity a federal award is made to, identified by its UEI (e.g. a university system, a college, a nonprofit, a state agency).
_Avoid_: Grantee (as a precise term), awardee, vendor

**Grant**:
One funded project for one project period, identified by its FAIN; a renewal is a new Grant.
_Avoid_: Award (when meaning the whole project), contract, project

**Succession**:
The link from a Grant to the Grant that renewed it for the same Recipient, Program, and Host institution; a chain of successions is how renewal timing is read.
_Avoid_: Renewal chain, continuation (continuation means a yearly funding action within one Grant)

**Host institution**:
The college or school district a Grant's project runs at, identified by UNITID or NCES LEAID; may differ from the Recipient.
_Avoid_: Institution served, site, school

**Program**:
One federal grant program a Grant belongs to, such as Upward Bound or GEAR UP state grants; finer than an assistance listing where one listing covers several programs.
_Avoid_: CFDA, listing (those name the federal number, not the program)

**Continuation**:
A yearly funding action that extends an existing Grant into its next Budget period.
_Avoid_: Renewal

**Budget period**:
The stretch of a Grant, usually 12 months, that one Continuation (or the initial award) funds; it can start in a different fiscal year from the action that funds it.
_Avoid_: Award year, grant year

**Cohort**:
The Grants of one Program awarded in one competition.
_Avoid_: Class, slate (when meaning the Grants rather than the notice)

**No single Host**:
The outcome for a Grant decided by rule to have no one Host institution (GEAR UP State, a partnership naming no district, a statewide agency, a nonprofit naming no site); distinct from unmatched, where no candidate was found, and from review, where a person must choose.
_Avoid_: Unmatched (for this case), unknown Host

**Case label**:
The name of the rule that decided a Grant's Host link (e.g. `uei_confirmed`); accuracy is measured and reported per case label.
_Avoid_: Confidence, score

**Local context**:
The institution type, enrollment, and district child-poverty rate attached to a Grant through its Host institution, as one latest snapshot stamped with its data year; it describes where the Host sits, not who the project serves.
_Avoid_: Demographics, service area

**Campus district**:
The geographic school district a college Host's campus lies in; its poverty rate is shown for college-hosted Grants and labelled as the campus's district, never as the served schools'.
_Avoid_: Target district, service district

## Grant status

**Funding status**:
What happened to a Grant's funding for one Budget period, read from its funding actions; it describes the pattern, never the cause.
_Avoid_: Non-continued, terminated, reinstated (as status values; those name a cause)

**Lifecycle stage**:
Where a Grant sits in its project period: new, continuing, final Budget period, ended, or re-competing soon.
_Avoid_: Status (alone)

**Predicted due date**:
The expected application deadline of a Program's next competition: the prior Cohort's published deadline plus 60 months. Set per Cohort, never per Grant; tagged _notice published_ or _inferred_.
_Avoid_: Renewal date, end date (a Grant's end date is a separate fact)

**Re-competing soon**:
A Lifecycle stage for a Grant whose Cohort's Predicted due date is 12 months or less away and whose latest readable Funding status is continued or funded late. Not used for GEAR UP.
_Avoid_: At-risk, expiring

**2025–26 disruption**:
A Grant whose funding was missing, late, or reversed for a Budget period starting in the 2025–26 policy window, whether or not it was later restored; a pattern, not proof of a policy cut.
_Avoid_: Cut, at-risk (those imply a cause or a forecast)

## Reconciliation

**Reconciliation status**:
The outcome of one reconciliation row (a check for one Program and fiscal year): reconciled, a stated difference, or not comparable. It is set by a tolerance fixed before the first run and never adjusted to close a gap.
_Avoid_: Validated, matched (those name Host linking and FAIN joins)

**Gap reason code**:
The closed-vocabulary label on a reconciliation row that does not reconcile, such as `not_published`, `timing_difference`, `no_ed_list`, `provisional`, or `unexplained`; each carries a cited note.
_Avoid_: Error, discrepancy

## Provenance

**Pull date**:
The date a raw file or API response was fetched, recorded for every source.
_Avoid_: Download date, refresh date

**As-of date**:
The date a run reads the data as of. Funding status and "not yet readable" are judged against it, so every output states it.
_Avoid_: Run date, today

## Language notes

"Grantee" is fine in conversation and plain-language writing, where it loosely means the Recipient. In data, matching, and specs, use Recipient, Grant, or Host institution.
