# Founder questionnaire — proxy answers

**Status: ASSUMPTIONS, not facts.** The real founder of Elevated Minds has not been asked. These answers are a best guess written by Claude playing the role of the company's CEO, at the project owner's request, so planning can move forward without involving him yet. Every answer here should be checked with him before it drives a major decision.

**What the guesses are based on:** only what the project brief says about the company: a 35+ year education-services firm offering test prep, tutoring, enrichment workshops, curriculum development, educator PD, and workforce/reentry programs; it serves schools, colleges, nonprofits, and TRIO/GEAR UP programs nationally, is present in 46 states, has corrections contracts for AI literacy and workforce programs, and is building a high school AI literacy program with micro-certificates. Anything beyond that is general reasoning about how a company like this probably works, and it's labeled that way.

Process: draft answers (this section) → critique by an evaluator playing a different education-services CEO → final review and revised answers.

---

## Draft answers (round 1)

### Q1. When you decide which schools, colleges, or programs to contact next, what do you go on today?

**Answer (as CEO):** Mostly relationships. After 35 years, a large share of our work comes from repeat clients and from program directors who already know us — including directors who move to a new institution and bring us with them. We meet new programs at TRIO conferences (the national COE conference and the regional associations). We hear about new grants by word of mouth, usually after the money has already landed. We don't have a systematic list of every grantee and when their grant runs out. We respond to district and college RFPs when we see them, but that's reactive.

**Rationale:** A firm this old, selling into a niche where the buyers (TRIO and GEAR UP directors) are a tight professional community, almost certainly grows mainly through referrals and conferences. The brief itself lists TRIO conference agendas and exhibitor lists as a source, which suggests conferences matter to the business. The fact that the project owner thinks a consolidated grantee table would be useful suggests the company doesn't already have one.

### Q2. Which matters most to you: a list of programs to contact, an early warning about upcoming grant competitions, or a sense of which programs and states are at risk from federal cuts?

**Answer (as CEO):** In order:
1. **The list of programs to contact**, especially programs that just got a new grant (they're setting up and buying) and programs whose grants are about to be re-competed (they're writing proposals and lining up partners).
2. **Early warning about funding outside TRIO**: reentry, workforce, and AI-in-education grants. I already hear about TRIO competitions through the TRIO community. I don't hear early enough about DOJ, DOL, or new ED priorities, and that's where our newer lines (corrections, AI literacy) need to grow.
3. **Risk exposure.** I care, especially after the 2025 cuts and two budgets that proposed zeroing out TRIO and GEAR UP. But I check this a few times a year to decide where to diversify. I don't act on it every week.

**Rationale:** The brief describes a sales-driven founder. A list turns directly into calls, so it's the most usable output. Alerts on TRIO competitions would partly duplicate what the TRIO community already spreads, but the company's growth bets (corrections, AI literacy) depend on funding streams it's less plugged into. Risk is real (see `docs/research/trio-gearup-funding-and-cycles.md`: FY2026 and FY2027 President's budgets proposed $0 for both), but it drives occasional strategy decisions, not daily sales activity.

### Q3. How far ahead do you need to know about a TRIO or GEAR UP program's grant renewal or competition to be useful to them? Weeks, months, a year?

**Answer (as CEO):**
- **New grantees:** within the first 1–3 months after the award. That's when they're hiring, planning their first year, and spending start-up money.
- **Re-competitions:** 6–12 months before the application is due. Applicants write partners and services into their proposals. If we're named in a winning proposal, we're in their budget for five years. If we hear about it once the notice is out, it's usually too late to get written in.
- **Existing grantees mid-grant:** a few months before their budget year starts, when they plan the year's services.

**Rationale:** Grant-funded buyers spend according to an approved budget, so the time to get in is when that budget is being written: at proposal time and at the start of each budget year. The 5-year TRIO project period (from the funding research) means getting written into a proposal is worth five years of revenue. The exact budget-year start dates per program are being researched (`program-services-and-incumbency.md`, pending).

### Q4. Which programs buy from you most: Upward Bound, Talent Search, Student Support Services, GEAR UP, or others? What do they usually buy?

**Answer (as CEO):** My best guess at the order:
1. **Upward Bound and Upward Bound Math-Science:** test prep, tutoring, Saturday and summer enrichment. They serve high schoolers intensively and run summer programs, so they need lots of instruction.
2. **GEAR UP:** the biggest grants, serving whole school cohorts. They buy college-readiness workshops, test prep, and teacher PD.
3. **Talent Search:** workshops and test prep across many schools, lighter-touch per student.
4. **Educational Opportunity Centers:** adult learners, where our workforce programs fit.
5. **Student Support Services and McNair:** less. Colleges mostly do SSS tutoring in-house, and McNair is small (some graduate-exam prep).

**Rationale:** This is the least certain answer. It's based on what each program serves (high schoolers vs. college students vs. adults) and how that lines up with the company's offerings, not on any knowledge of the company's actual sales. Whether the regulations require services like exam prep for some programs is being researched (`program-services-and-incumbency.md`, pending). If they do, that would support this ranking.

### Q5. If I showed you a list of grantees in a state you know well, would you be willing to tell me who's missing or wrong?

**Answer (as CEO):** Yes, for 2 or 3 states where we're strongest, if it takes 30 minutes or less, comes as a spreadsheet I can mark up, and I don't have to hand over any client information.

**Rationale:** It's a low-effort ask that directly benefits him, and spotting gaps in a market he knows is something a founder would find easy and interesting. Keeping it to a few states and a short time respects that this is an unsolicited side project.

---

## What these draft answers imply for the build

- v1's main output is a **target list at the project level** (one row per grant), sorted by "just awarded" and "re-competing within 12 months".
- **Renewal timing** must be estimated at least 6–12 months ahead of competitions, so the backtest of renewal inference is a v1 requirement, not a nice-to-have.
- **Funding alerts** should focus on non-TRIO streams (DOJ Second Chance, DOL reentry/workforce, ED AI priorities). This moves Grants.gov and the Federal Register closer to v1.
- **Risk exposure** can be a simple quarterly summary, not a dashboard.
- **Validation:** plan for a founder review of 2–3 states as the check on whether the list is complete.

---

## Evaluator critique (round 1)

*Written by Claude playing the CEO of a different, comparable education-services company. Market claims marked "from experience (unverified)" are one operator's view, not checked data. Nothing here is known about Elevated Minds specifically.*

### Q1. How targets are chosen today

**Plausible:** Relationships, directors who change jobs and bring you along, and COE/regional conferences really do drive this niche. **Wrong or naive:** "No systematic list of grantees" is hard to believe for a 35-year firm in 46 states. ED publishes grantee lists on its program pages (see the GEAR UP grant-award pages cited in `trio-gearup-funding-and-cycles.md` §1c), and any sales lead in this space has pulled them. What's probably missing is everything *around* the list: which grants are new vs. continuing, when they end, who was non-continued in 2025, and which institution's procurement office actually issues the PO. **Rationale overreach:** "The project owner thinks a table would be useful, so the company lacks one" is circular. **Revision:** "We have spreadsheets of grantees, probably out of date, kept per salesperson. What we lack is one maintained view with cohort, end date, 2025 status, and how we're tied to each grant." **Confidence: medium.**

### Q2. List vs. early warning vs. risk

**Plausible:** Ranking the list first fits a sales-led founder. Wanting earlier signals on DOJ/DOL/AI money fits the growth bets. **Naive:** The answer treats risk as a strategy topic you check quarterly. After 2025 it's a sales-hygiene issue. The research file documents summer-2025 non-continuations, FY2025 SSS non-selections, falling FY2025 project counts in every TRIO program except SSS, and court-ordered reconsideration that is still disputed. A list that doesn't mark "non-continued / in litigation / reinstated" wastes calls and looks tone-deaf. From experience (unverified): in 2025–26, directors with live grants delayed or shrank discretionary contracts until their continuation award was in hand. Also, corrections work is mostly bought through **state DOC procurement** (state contracts, RFPs), not federal grant notices. Grants.gov alerts on DOJ Second Chance will catch only part of it. **Revision:** Keep the order, but add a per-grant status flag to item 1, and add "state corrections/workforce RFPs" to item 2. **Confidence: medium.**

### Q3. Lead time

**Plausible:** Starting outreach early in a new award, and planning before each budget year, is right. **Wrong or overstated:** "If we're named in a winning proposal, we're in their budget for five years." Two problems:
- **Procurement.** Federal awardees buy under their own documented procedures plus 2 CFR 200.317–.327. 2 CFR 200.320 allows noncompetitive (sole-source) purchases only in narrow cases: micro-purchases, a single source, a public emergency, written approval from the awarding agency, or too few bids after a solicitation. Being named in a proposal isn't one of those. EDGAR (34 CFR 75.135) addresses contractors named in applications. My understanding is that the exemption is narrow (unverified; read the text before relying on it). Many university procurement offices will make you compete once the award comes in, unless the purchase falls under their small-purchase threshold.
- **Peer review.** From experience (unverified): reviewers score the applicant's staff and plan. A named vendor helps mostly as a letter of support or MOU. The real routes into a proposal are helping write it and being the low-risk incumbent.

**Timing:** UB/UBMS/VUB/McNair FY2027 is *inferred*. The research found no notice as of 2026-10-14, and DOL now administers most HEA postsecondary programs, so a 6–12-month lead may not be computable. **Missing seasonality** (from experience, unverified): UB summer components get bought in late winter/spring. Institutions spend down before their own fiscal year closes (often June 30). **Revision:** "Re-competitions: as early as we can, so we can help the incumbent apply and get a letter of support in. After the award, expect to compete or quote under the institution's thresholds. New grantees: first 1–3 months. Continuing grantees: before the budget period starts and before summer." **Confidence: low-medium.**

### Q4. Which programs buy most

**Plausible:** UB/UBMS at the top and SSS/McNair at the bottom match what each program does. **Wrong or missing:**
- **Talent Search changed in FY2026.** The notice moved to governor-designated, state-level applicants with awards up to $10M, about 175 awards instead of about 545, administered by DOL ETA (research §2, caveat 5). That's fewer, much larger buyers, likely buying through state procurement or subawards. TS could become a top target or a lost one. Either way, "workshops across many schools" no longer describes the buyer. EOC (up to $3M, about 55 awards, under DOL) now sits next to workforce funding, which strengthens the fit with your workforce/reentry line.
- **Contract dollars.** Average awards run about $315K–$370K (ED FY2024 figures in the research). From experience (unverified): most of that is staff salaries, fringe and student costs, so contracted services are often a small share. A typical UB grant is a five-figure customer, not six.
- **Missing source.** The answer never uses the company's own invoices, which would settle this in an hour.

**Revision:** Label the ranking "hypothesis, to be replaced by revenue by program from our books." Move TS to "changed; re-evaluate after FY2026 awards post." **Confidence: low** (as the draft admits).

### Q5. Willingness to validate

**Plausible:** Yes, with tight scope. **Missing:** A founder will worry about the list leaving the building, since it's competitive intelligence. He'll also judge "who's missing" mainly against his own clients, so his review shows how well the list covers *his* clients, not the market. **Revision:** Add "and the list stays internal." Pair his review with a mechanical check against ED's published grantee lists. **Confidence: medium-high.**

### On "What these draft answers imply for the build"

- **Project-level list:** Agree. Add columns for 2025 status (non-continued/litigated/reinstated), cohort, and the institution that holds the money, which is the procurement buyer, not the program office.
- **Backtest as v1:** Agree for TRIO. Caveat: the TS/EOC FY2026 redesign breaks comparability, and GEAR UP timing can't be inferred from end dates (research §2).
- **Non-TRIO alerts:** Fine, but state-level procurement portals likely matter more than Grants.gov for corrections.
- **Risk summary:** Demote the quarterly dashboard, but promote the per-row status flag to v1.
- **Validation:** Keep, but don't make it the *only* completeness check.

### Biggest blind spots

1. **Money and who signs.** Nobody asked what a TRIO/GEAR UP customer is worth (average contract, renewal rate, share of revenue), how much was lost in 2025–26, or who approves the purchase. In my experience (unverified), the project director picks the vendor, and the institution's procurement/grants office decides whether it's a PO, a quote, or an RFP. A target list without deal size and buying path can't be prioritized.
2. **TRIO tunnel vision.** The brief says the company serves districts, colleges and nonprofits, plus corrections. District money (Title I, Title IV-A, state funds, from experience, unverified) is likely a bigger, steadier pool than TRIO, and it isn't exposed to a $0 budget request two years running. The questionnaire never asks what share of revenue is TRIO/GEAR UP versus everything else. That answer should decide whether this hub is TRIO-first at all.

---

## Final review (round 2)

*Written by Claude after reading the evaluator's critique. For each question: the final proxy answer, what was taken from the critique and what wasn't (with reasons), a confidence level, and what would change the answer. These are still **assumptions** until the real founder confirms them.*

Two pending research files may change Q3 and Q4. When they're written, this section should be checked against them:
- `docs/research/program-services-and-incumbency.md`: required services per program, prior experience points, budget-period start dates, procurement rules for grantees
- `docs/research/apr-data-and-fy2026-awards.md`: how the FY2026 Talent Search/EOC awards show up

### Q1. How targets are chosen today: final

**Answer:** Relationships, repeat clients, directors who move and bring us along, and TRIO conferences. We probably have grantee spreadsheets that are out of date and scattered across people. What we don't have is one maintained view with each grant's cohort, end date, 2025 status (non-continued, in litigation, or reinstated), and the institution that actually holds the money.

**Taken from the critique:** the revision almost in full. ED publishes grantee lists (see `source-terms-and-cadence.md`), so "no list at all" was unlikely for a 35-year firm. The draft's rationale was also circular, as the evaluator said.

**Not taken:** nothing.

**Confidence:** medium. **Would change if:** the founder says the company already keeps a maintained grantee database. That would make the hub's value the added context, not the list itself.

### Q2. What matters most: final

**Answer:**
1. **A project-level target list** with a **status flag on every row**: active, new, re-competing soon, non-continued in 2025, in litigation, or reinstated.
2. **Early warning on funding outside TRIO:** DOJ, DOL, and ED AI priorities through Grants.gov and the Federal Register. **State corrections and workforce procurement** is a real channel but a later, messier source.
3. **A risk summary** for strategy, a few times a year.

**Taken from the critique:**
- The status flag, which moves part of "risk" into v1. The 2025 non-continuations and the court order are documented in `trio-gearup-funding-and-cycles.md`. Calling a program that just lost its grant would waste the call and hurt the relationship.
- The point that corrections work is mostly bought by states. The brief's own corrections contracts support this.

**Not taken:** adding state procurement portals to v1. There are 50 different systems, each with its own terms, which conflicts with the brief's "prefer APIs and bulk files" rule. It goes on the later list.

**Confidence:** medium. **Would change if:** the founder ranks risk or alerts first, for example if 2025–26 losses were severe enough that protecting existing revenue matters more than finding new clients.

### Q3. Lead time: final

**Answer:**
- **New grantees:** first 1–3 months after the award.
- **Continuing grantees:** before each budget period starts, and before summer, when summer components are planned.
- **Re-competitions:** as early as possible, so we can support the incumbent's application (letter of support, partnership, help with the plan). **This is not a five-year lock-in.** Once the award is made, expect to quote or compete under the institution's procurement rules.

**Taken from the critique:**
- The procurement correction. 2 CFR 200.320 allows noncompetitive purchases only in narrow cases, and being named in a proposal isn't clearly one of them. The draft overstated it. The precise rule, including what 34 CFR 75.135 says about contractors named in applications, is UNVERIFIED and pending the regulations research.
- The seasonality points (summer purchasing, institutional fiscal-year spend-down), kept as UNVERIFIED experience claims.
- The timing caveat: the next Upward Bound/McNair competition date is inferred, and the move of grant administration to DOL makes it less predictable.

**Not taken:** nothing. The core point stays: earlier is better, because the incumbent's application is where relationships get built.

**Confidence:** low-medium. **Would change if:** the regulations research shows a clear route for named contractors, or the founder says how deals with grantees actually get done.

### Q4. Which programs buy most: final

**Answer (hypothesis only):** Upward Bound and UB Math-Science, then GEAR UP, then EOC, then SSS and McNair. **Talent Search is marked "changed; re-evaluate."** Its FY2026 redesign (about 175 state-level awards of up to $10M, run by DOL) means the buyer is now a much bigger, state-level organization. EOC's move toward DOL and workforce funding may make it a better fit for the company's workforce and reentry line than the draft assumed. *Update from `apr-data-and-fy2026-awards.md`:* the ~175 figure was the notice's estimate. A COE press release (secondary, UNVERIFIED) reports 326 Talent Search and 102 EOC grants in a first slate, and none of them appear in USAspending yet. So the size and number of the new Talent Search buyers is still unknown.

**Taken from the critique:**
- The Talent Search and EOC changes, from facts already in `trio-gearup-funding-and-cycles.md`.
- The point that contracted services are probably a small share of an average award of roughly $315K–$370K. That makes deal size an important missing piece.
- The note that the company's own sales records would settle this.

**Not taken:** the evaluator's "five-figure customer" estimate, as a figure. It's one operator's unverified experience, and the brief says never to invent numbers. It stays only as a question for the founder.

**Confidence:** low. **Would change if:** the founder shares revenue by program, even rough percentages. That should replace this answer entirely.

### Q5. Willingness to check a list: final

**Answer:** Yes, for 2–3 strong states, in under 30 minutes, as a spreadsheet he can mark up, with no client data shared **and the list staying internal**.

**Taken from the critique:**
- "Stays internal."
- The point that his review mainly shows how well the list covers *his* clients. It will be paired with mechanical checks: ED's published award counts per program, and ED's grantee lists (hand-downloaded).

**Confidence:** medium-high.

### Blind spots raised by the evaluator: decisions

1. **Deal size, revenue mix, 2025–26 losses, who signs.** *Accepted as questions for the real founder.* We won't guess numbers. For the data model, the target list will have a column for the institution holding the grant (the buyer) next to the program project.
2. **TRIO tunnel vision.** *Accepted as a valid risk, not acted on for v1.* District funding (Title I, Title IV-A, state money) may well be a bigger and steadier market. But the brief defines v1 as TRIO/GEAR UP, the federal award data for those programs is the cleanest available (`usaspending-trio-gearup.md`), and Title I/IV-A allocations are already on the brief's "later" list. v1 stays TRIO-first, and the share of revenue from TRIO/GEAR UP is the **top question for the real founder**. If it's small, the roadmap after v1 should shift toward district funding.

### What this means for the build (replaces the round-1 section)

- **v1 main output:** a project-level target list (one row per grant), with: program, holding institution, cohort/start year, projected end, **2025–26 status flag**, award amounts by year, and location context.
- **Renewal-timing backtest:** v1 for TRIO, excluding Talent Search/EOC FY2026 (the redesign breaks comparability). No end-date-based timing for GEAR UP.
- **Status data:** the 2025 non-continuation and litigation status needs a source. It probably can't be fully derived from USAspending. That's a decision ticket for wayfinder.
- **Alerts:** Grants.gov and the Federal Register for DOJ, DOL, and ED AI priorities in v1.5. State corrections procurement later.
- **Risk:** a simple summary in the one-pager, not a dashboard.
- **Completeness checks:** ED award counts per program, ED grantee lists, the founder's 2–3-state review.

### Questions only the real founder can answer

1. Roughly what share of revenue comes from TRIO/GEAR UP vs. districts, colleges, nonprofits, and corrections?
2. What's a typical TRIO/GEAR UP contract worth, and how often do clients renew?
3. How much did 2025–26 federal changes cost the business, if anything?
4. Who signs off at a typical client: the program director, or the institution's procurement office? How do you usually get paid (PO, quote, RFP, sub-award)?
5. Do you already keep a grantee list? How current is it?
6. Which 2–3 states would you be willing to check a list for?

---

## Addendum: checked against program rules research (2026-10-14)

*After the final review, `docs/research/program-services-and-incumbency.md` came back. It's based on statute (Cornell LII), eCFR current to 2026-10-13, and the Federal Register. These changes override the round-2 text where they conflict.*

### Q3. Lead time: revised

- **Small purchases are easier than round 2 said.** Under the 2 CFR 200 thresholds cited in the research file, purchases up to **$15K** are micro-purchases and need no competition; a grantee can self-certify up to $50K. Up to **$350K** they need quotes, not a formal RFP. Many TRIO-sized contracts may therefore not need a bid. That makes the relationship with the program director matter more, partly bringing back the draft's point, but without the "five-year lock-in." Whether the institution uses lower internal thresholds is unknown and varies by institution.
- **Why supporting incumbents matters:** incumbents get up to **15 prior-experience points** on top of a 100-point peer-review score (HEA §402A(c)(2)(A)), and, in the notices, a no-gap start date and higher award ceilings. Helping an incumbent apply is a good bet. GEAR UP has no prior-experience points.
- **Buying windows:** no statute, regulation, or notice sets project start dates. USAspending award records show **Sept. 1** for most TRIO programs, **June 1** for some Upward Bound projects, **Oct. 1** for McNair, and **Sept. 1 or Oct. 1** for GEAR UP depending on the group of grants. The pipeline should **derive start dates from the data**, not hard-code them.
- 34 CFR 75.135 (contractors named in applications) wasn't covered and is still UNVERIFIED.

**Confidence:** medium (was low-medium).

### Q4. Which programs buy most: revised

The rules now inform the ranking. The ranking itself is still a hypothesis.

| Program | What the rules say (from research file) | Effect on ranking |
|---|---|---|
| Talent Search | Statute requires help preparing for college entrance exams, plus tutoring; regs list "purchase of testing materials and test preparation programs" as allowable (34 CFR 643.30(b)) | **Up**: an explicitly allowed purchase. FY2026 redesign still to be evaluated |
| EOC | Same allowable test-prep purchase line (34 CFR 644.30(b)) | **Up**, plus the workforce fit |
| Upward Bound / UBMS / VUB | Statute requires exam prep and tutoring, but the cost rules have no test-prep line. Whether they can *buy* test prep is an open question | Stays high, with a caveat |
| GEAR UP | Broadest menu: exam prep, tutoring, curriculum, summer programs, staff PD. Businesses are named providers for state grants. In-kind or discounted services count toward the 1:1 match. State grants spend only 25–50% on services | High; discounted services may be a selling point because they help meet the match |
| SSS | Must provide tutoring | Low-middle |
| McNair | **Test prep is unallowable** (34 CFR 647.31(a)); whether GRE prep counts is an open question | **Bottom**: rules out the draft's "some graduate-exam prep" guess |

**Confidence:** low-medium (was low). Revenue by program from the founder would still replace this.

### New question for the real founder
7. Do you ever offer discounted or in-kind services to GEAR UP grantees to help them meet their match?
