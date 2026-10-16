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

## Grant status

**Funding status**:
What happened to a Grant's funding for one Budget period, read from its funding actions; it describes the pattern, never the cause.
_Avoid_: Non-continued, terminated, reinstated (as status values; those name a cause)

**Lifecycle stage**:
Where a Grant sits in its project period, such as its first or final Budget period.
_Avoid_: Status (alone)

**2025–26 disruption**:
A Grant whose funding was missing, late, or reversed for a Budget period starting in the 2025–26 policy window, whether or not it was later restored; a pattern, not proof of a policy cut.
_Avoid_: Cut, at-risk (those imply a cause or a forecast)

## Language notes

"Grantee" is fine in conversation and plain-language writing, where it loosely means the Recipient. In data, matching, and specs, use Recipient, Grant, or Host institution.
