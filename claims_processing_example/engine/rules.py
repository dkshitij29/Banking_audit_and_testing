"""Claim adjudication: adjudicate(policy, claim) -> Decision.

This docstring is the specification of how a claim is decided. The order of the
steps is part of it, because a different order gives a different answer. Never
reorder a step without updating this docstring and tests/test_order.py, which
locks it.

The engine is pure: no I/O, no clock, no randomness. Every product number and
list comes from policy.terms; this module holds none (tests/test_guards.py).

Stage 1: gates
==============
A gate that fires rejects the claim, and payable is 0.

  1. Policy in force: the admission date is within the policy period
     (6.1_policy_period). If not, stop; the other gates mean nothing.
  2. Every other gate is checked independently, and every one that fires is
     recorded, since each is a valid ground on its own:
       - initial waiting period (4.3_initial_waiting). An accident inside the
         wait fires 4.3_accident_exception instead, if the product exempts
         accidents from it.
       - specified disease waiting period (4.2_specific_disease_waiting), for a
         claim matching a listed condition group. A claim matching several
         groups waits for the longest. An accident fires 4.2_accident_exception
         instead, if the product exempts accidents from it.
       - pre-existing disease waiting period (4.1_ped_waiting), for a claim whose
         primary diagnosis matches a PED the member declared. The claim's own
         diagnoses never make a condition pre-existing. No accident exception.
         Where a condition is both listed and declared, both waits are checked,
         so the longer one decides.
       - permanent exclusions (4.4-4.18): each exclusion the claim matches fires.
       - AYUSH eligibility (3.4_ayush), for AYUSH treatment only: fires if the
         product does not cover it, or covers it only in an AYUSH hospital and
         this hospital is not one.
       - minimum stay (2.1_min_hospitalisation). A shorter stay fires
         2.2_day_care instead if a procedure is on the day-care list.

Stage 2: escalation
===================
Checked after the gates, and escalates only when a gap could change the outcome.
An escalated claim has payable 0.

  - A required discharge summary is missing (7.1_missing_documents): escalate.
    It is the source of the diagnosis, dates and cause every gate needs, so no
    gate is checked.
  - A required bill or claim form is missing (7.1), or the claimed amount
    differs from the bill total (7.2_document_mismatch): escalate, unless a
    gate already rejects the claim, since no gate depends on either.
  - The claim form's admission or discharge time differs from the hospital's
    (7.2): decide the claim on each set of dates. Escalate if the verdict or
    payable differ; otherwise decide on the hospital's dates.

Stage 3: amount
===============
Each step works on the output of the step before it.

Amount order:
  1. pre_post_window   drop pre/post-hospitalisation lines dated outside their windows
  2. line_exclusions   remove excluded bill lines, one rule at a time in the
                       product's order; a line goes to the first rule listing it
  3. room_rent         if the daily room rate is above the cap, multiply the room
                       line, the charges counted in the room rate and the
                       room-associated lines by cap / rate
  4. icu               the same, with the ICU cap and the ICU-associated lines
  5. disease_sublimit  cap the running amount at the matching sub-limit, per
                       unit (eye, joint) of the matching procedures
  6. ayush_cap         cap the running amount of an AYUSH claim at the AYUSH limit
  7. deductible        subtract, floor at 0
  8. copay             subtract copay_bp of the running amount
  9. sum_insured       cap at sum insured + cumulative bonus

Because the sum insured cap comes after co-pay, co-pay stops mattering once a
claim is far enough above the sum insured. ₹6,00,000 admissible with 10% co-pay
and a ₹5,00,000 sum insured pays ₹5,00,000 (6,00,000 - 60,000 = 5,40,000, then
capped), not ₹4,50,000. This follows CLAUDE.md; check it against each wording.

Conventions
===========
- Matching is by code, never by text (schema.Match): the primary diagnosis's
  ICD-10 code against listed prefixes (H25 matches H25.1), and procedure codes
  against listed codes. Secondary diagnoses never match any rule.
- The decision uses the hospital's records (discharge summary and bill) for
  its facts. The claim form matters only to stage 2.
- Rounding: a step computes its deduction exactly, then rounds the deduction
  (not the remaining amount) to the nearest rupee, halves up. Every amount in
  the trace is a whole number of rupees.
- Waiting periods count from the member's first_inception. A claim is inside a
  wait if the admission date is before first_inception + the wait's duration
  (Duration.add_to). The first 100 days from 1 Apr are 1 Apr to 9 Jul.
- A cap (schema.Cap) is a rupee amount, a share of the base sum insured, or the
  lower of the two. Cumulative bonus never raises a cap.
- The daily room rate is the room line's amount, plus the inpatient charges in
  terms.room_rate_includes (a wording that caps "room, boarding and nursing"
  together), divided by the room line's days. The daily ICU rate is the ICU
  line's own.
- The room line and the charges counted in its rate are always scaled with the
  room rate, and the ICU line with the ICU rate; terms.room_associated and
  terms.icu_associated list which other charges are scaled with them. No charge
  is in two of these lists. Only inpatient lines are ever counted or scaled:
  pre/post-hospitalisation bills never are.
- A pre-hospitalisation line is covered if dated no more than
  pre_hospitalisation_days before the admission date; a post-hospitalisation
  line if dated no more than post_hospitalisation_days after the discharge date.
  Both ends are included. Every pre/post bill is taken to relate to the
  condition treated; unrelated bills are not modelled.
- A disease-wise sub-limit caps the whole claim, pre/post bills included (a
  placeholder reading; check it against each wording). If two sub-limits apply,
  the engine refuses the case.
- The deductible applies per claim.
- A clause fires when it rejects the claim, escalates it, reduces the payable by
  more than ₹0, or is an exception that stopped a gate from rejecting.
- A rule appears in the trace only when it has something to check for this
  policy and claim: no co-pay or deductible step when they are 0, no room or
  ICU step without that bill line and a cap, no PED step when the member
  declared none, no specified-disease, exclusion or sub-limit step when the
  product lists none, no pre/post step without pre/post bills, no AYUSH step
  for allopathic treatment, and no claim-form comparison without a claim form.

Verdict
=======
- ESCALATE: stage 2 fired.
- REJECT: a gate fired, or nothing is left to pay after the amount steps.
- PARTIAL: something is paid, and a limit or exclusion cut part of the claim:
  any amount step that fired other than non-payable items (A1), deductible
  (5.1) and co-pay (5.2).
- APPROVE: something is paid, and nothing but non-payables, deductible or
  co-pay reduced it. Those are cost sharing the policyholder agreed to, not a
  disallowance.

Answer key (Decision.clauses)
=============================
- Escalated: the escalation clauses that fired, and nothing else.
- A gate rejected: every gate that fired, and nothing else.
- Otherwise: the exceptions that fired, plus every amount step that reduced
  the payable.
Decision.checks lists every rule that was checked, fired or not.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction

from engine import clauses as C
from engine.schema import (
    BP_SCALE,
    BillCategory,
    BillLine,
    Cap,
    Cause,
    Claim,
    Decision,
    DocType,
    Effect,
    FactValue,
    Match,
    Member,
    Phase,
    Policy,
    ProductTerms,
    TraceStep,
    TreatmentSystem,
    UnsupportedCase,
    Verdict,
    format_percent,
    format_rupees,
    format_stay,
)

ENGINE_VERSION = "0.4.0"

AMOUNT_ORDER: tuple[str, ...] = (
    "pre_post_window",
    "line_exclusions",
    "room_rent",
    "icu",
    "disease_sublimit",
    "ayush_cap",
    "deductible",
    "copay",
    "sum_insured",
)
"""The amount steps that run, in order. tests/test_order.py checks it against the docstring."""

_COST_SHARING = frozenset({C.NON_PAYABLE, C.DEDUCTIBLE, C.COPAY})
"""Amount steps that leave a claim APPROVE when they fire."""

_HALF = Fraction(1, 2)


@dataclass(frozen=True)
class Context:
    """The inputs every rule sees."""

    policy: Policy
    claim: Claim
    member: Member

    @classmethod
    def of(cls, policy: Policy, claim: Claim) -> Context:
        for member in policy.members:
            if member.member_id == claim.member_id:
                return cls(policy, claim, member)
        raise ValueError(
            f"claim is for member {claim.member_id!r}, who is not on policy {policy.policy_number}"
        )

    @property
    def terms(self) -> ProductTerms:
        return self.policy.terms

    def with_stay(self, admitted_at: datetime, discharged_at: datetime) -> Context:
        """The same claim, with other admission and discharge times (stage 2's what-if)."""
        claim = self.claim.model_copy(update={"admitted_at": admitted_at, "discharged_at": discharged_at})
        return Context(self.policy, claim, self.member)


@dataclass(frozen=True)
class Outcome:
    """What one rule saw and did. Becomes a numbered TraceStep in the Decision."""

    check: str
    fired_clause: str | None
    effect: Effect
    facts: dict[str, FactValue]
    note: str
    before: int | None = None
    after: int | None = None

    def __post_init__(self) -> None:
        if (self.effect is Effect.PASS) != (self.fired_clause is None):
            raise RuntimeError(f"{self.check}: effect {self.effect} with fired clause {self.fired_clause}")


@dataclass(frozen=True)
class Running:
    """What the amount steps pass along."""

    lines: tuple[BillLine, ...]
    """Bill lines still payable."""
    total: int
    """Payable so far, in whole rupees."""


AmountStep = Callable[[Context, Running], tuple[Running, list[Outcome]]]


@dataclass(frozen=True)
class _Core:
    """Stages 1 and 3 for one set of facts."""

    gates: list[Outcome]
    amounts: list[Outcome]
    payable: int

    @property
    def rejected(self) -> bool:
        return any(outcome.effect is Effect.REJECT for outcome in self.gates)

    def result(self) -> tuple[Verdict, int]:
        verdict, payable, _ = _verdict(self.gates + self.amounts, self.payable)
        return verdict, payable


def adjudicate(policy: Policy, claim: Claim) -> Decision:
    """Decide one claim. Pure: the same inputs always give the same Decision."""
    ctx = Context.of(policy, claim)
    missing = tuple(doc for doc in ctx.terms.required_documents if doc not in claim.documents_submitted)
    if DocType.DISCHARGE_SUMMARY in missing:
        return _decision([missing_documents(ctx, missing, gate_rejected=False)], payable=0)

    core = _core(ctx)
    escalation = [missing_documents(ctx, missing, gate_rejected=core.rejected)]
    mismatch = document_mismatch(ctx, core)
    if mismatch is not None:
        escalation.append(mismatch)
    if any(outcome.effect is Effect.ESCALATE for outcome in escalation):
        return _decision(core.gates + escalation, payable=0)
    return _decision(core.gates + escalation + core.amounts, payable=core.payable)


def _core(ctx: Context) -> _Core:
    gates = [policy_in_force(ctx)]
    if gates[0].effect is Effect.PASS:
        for gate in (initial_waiting, specific_waiting, ped_waiting):
            outcome = gate(ctx)
            if outcome is not None:
                gates.append(outcome)
        gates += permanent_exclusions(ctx)
        ayush = ayush_eligibility(ctx)
        if ayush is not None:
            gates.append(ayush)
        gates.append(min_stay(ctx))
    if any(outcome.effect is Effect.REJECT for outcome in gates):
        return _Core(gates, [], 0)

    running = Running(ctx.claim.bill, sum(line.amount for line in ctx.claim.bill))
    amounts: list[Outcome] = []
    for name in AMOUNT_ORDER:
        running, step_outcomes = _AMOUNT_STEPS[name](ctx, running)
        amounts += step_outcomes
    return _Core(gates, amounts, running.total)


# ---------------------------------------------------------------- stage 1: gates


def policy_in_force(ctx: Context) -> Outcome:
    """6.1: the admission date is within the policy period, both ends included."""
    policy, admitted = ctx.policy, ctx.claim.admitted_at.date()
    facts: dict[str, FactValue] = {
        "admission_date": admitted.isoformat(),
        "period_start": policy.period_start.isoformat(),
        "period_end": policy.period_end.isoformat(),
    }
    period = f"the policy period {policy.period_start} to {policy.period_end}"
    if policy.period_start <= admitted <= policy.period_end:
        return Outcome(C.POLICY_PERIOD, None, Effect.PASS, facts, f"Admitted {admitted}, within {period}.")
    return Outcome(
        C.POLICY_PERIOD, C.POLICY_PERIOD, Effect.REJECT, facts, f"Admitted {admitted}, outside {period}."
    )


def initial_waiting(ctx: Context) -> Outcome:
    """4.3: illness early in the cover is excluded; the product may exempt accidents."""
    wait = ctx.terms.initial_wait
    inception, admitted = ctx.member.first_inception, ctx.claim.admitted_at.date()
    over_on = wait.duration.add_to(inception)
    facts: dict[str, FactValue] = {
        "first_inception": inception.isoformat(),
        "wait": wait.duration.describe(),
        "wait_over_on": over_on.isoformat(),
        "admission_date": admitted.isoformat(),
        "cause": ctx.claim.cause.value,
        "accident_exempt": wait.accident_exempt,
    }
    the_wait = f"the {wait.duration.adjective()} initial wait from {inception}"
    if admitted >= over_on:
        return Outcome(
            C.INITIAL_WAITING, None, Effect.PASS, facts,
            f"Admitted {admitted}; {the_wait} was over on {over_on}.",
        )
    inside = f"Admitted {admitted}, inside {the_wait} (over on {over_on})"
    if ctx.claim.cause is Cause.ACCIDENT and wait.accident_exempt:
        return Outcome(
            C.INITIAL_WAITING, C.INITIAL_WAITING_ACCIDENT, Effect.EXCEPTION, facts,
            f"{inside}, but the cause is an accident, which the wait does not apply to.",
        )
    if ctx.claim.cause is Cause.ACCIDENT:
        inside += "; this product does not exempt accidents"
    return Outcome(C.INITIAL_WAITING, C.INITIAL_WAITING, Effect.REJECT, facts, f"{inside}.")


def specific_waiting(ctx: Context) -> Outcome | None:
    """4.2: listed conditions and procedures wait longer; the product may exempt accidents."""
    spec = ctx.terms.specific_wait
    if not spec.groups:
        return None
    claim, inception = ctx.claim, ctx.member.first_inception
    admitted = claim.admitted_at.date()
    matched = [(group, _matched_by(group.match, claim)) for group in spec.groups]
    matched = [(group, reasons) for group, reasons in matched if reasons]
    if not matched:
        return Outcome(
            C.SPECIFIC_WAITING, None, Effect.PASS, {"groups_matched": ()},
            f"Diagnosis {claim.primary_dx.icd10} and the procedures are not on the specified disease list.",
        )

    over_on = max(group.duration.add_to(inception) for group, _ in matched)
    names = ", ".join(group.name for group, _ in matched)
    facts: dict[str, FactValue] = {
        "groups_matched": tuple(group.name for group, _ in matched),
        "matched_by": tuple(sorted({reason for _, reasons in matched for reason in reasons})),
        "first_inception": inception.isoformat(),
        "wait_over_on": over_on.isoformat(),
        "admission_date": admitted.isoformat(),
        "cause": claim.cause.value,
        "accident_exempt": spec.accident_exempt,
    }
    if admitted >= over_on:
        return Outcome(
            C.SPECIFIC_WAITING, None, Effect.PASS, facts,
            f"Listed ({names}), but the wait from {inception} was over on {over_on}.",
        )
    inside = f"Listed ({names}); admitted {admitted}, inside the wait from {inception} (over on {over_on})"
    if claim.cause is Cause.ACCIDENT and spec.accident_exempt:
        return Outcome(
            C.SPECIFIC_WAITING, C.SPECIFIC_WAITING_ACCIDENT, Effect.EXCEPTION, facts,
            f"{inside}, but the cause is an accident, which the wait does not apply to.",
        )
    if claim.cause is Cause.ACCIDENT:
        inside += "; this product does not exempt accidents"
    return Outcome(C.SPECIFIC_WAITING, C.SPECIFIC_WAITING, Effect.REJECT, facts, f"{inside}.")


def ped_waiting(ctx: Context) -> Outcome | None:
    """4.1: a declared pre-existing disease waits longer. Keys off the member's declarations."""
    declared = ctx.member.declared_peds
    if not declared:
        return None
    code, admitted = ctx.claim.primary_dx.icd10, ctx.claim.admitted_at.date()
    related = [ped for ped in declared if any(code.startswith(prefix) for prefix in ped.icd10_prefixes)]
    facts: dict[str, FactValue] = {
        "declared_peds": tuple(ped.name for ped in declared),
        "primary_diagnosis": code,
        "related_to": tuple(ped.name for ped in related),
    }
    if not related:
        names = ", ".join(ped.name for ped in declared)
        return Outcome(
            C.PED_WAITING, None, Effect.PASS, facts,
            f"Primary diagnosis {code} is not related to a declared pre-existing disease ({names}).",
        )

    wait, inception = ctx.terms.ped_wait, ctx.member.first_inception
    over_on = wait.add_to(inception)
    facts |= {
        "first_inception": inception.isoformat(),
        "wait": wait.describe(),
        "wait_over_on": over_on.isoformat(),
        "admission_date": admitted.isoformat(),
    }
    names = ", ".join(ped.name for ped in related)
    the_wait = f"the {wait.adjective()} wait from {inception}"
    if admitted >= over_on:
        return Outcome(
            C.PED_WAITING, None, Effect.PASS, facts,
            f"{code} is related to declared {names}, but {the_wait} was over on {over_on}.",
        )
    return Outcome(
        C.PED_WAITING, C.PED_WAITING, Effect.REJECT, facts,
        f"{code} is related to declared {names}; admitted {admitted}, inside {the_wait} (over on {over_on}).",
    )


def permanent_exclusions(ctx: Context) -> list[Outcome]:
    """4.4-4.18: treatment this product never covers. Every matching exclusion fires."""
    outcomes = []
    for exclusion in ctx.terms.exclusions:
        reasons = _matched_by(exclusion.match, ctx.claim)
        title = C.REGISTRY[exclusion.clause_id].description
        facts: dict[str, FactValue] = {"matched_by": reasons}
        if reasons:
            outcomes.append(Outcome(
                exclusion.clause_id, exclusion.clause_id, Effect.REJECT, facts,
                f"Excluded ({title}): {', '.join(reasons)}.",
            ))
        else:
            note = f"Not excluded as {title[:1].lower()}{title[1:]}."
            outcomes.append(Outcome(exclusion.clause_id, None, Effect.PASS, facts, note))
    return outcomes


def ayush_eligibility(ctx: Context) -> Outcome | None:
    """3.4: AYUSH treatment is covered only as far as the product covers it."""
    system = ctx.claim.treatment_system
    if system is TreatmentSystem.ALLOPATHY:
        return None
    ayush, hospital = ctx.terms.ayush, ctx.claim.hospital
    facts: dict[str, FactValue] = {
        "treatment_system": system.value,
        "covered": ayush.covered,
        "requires_ayush_hospital": ayush.requires_ayush_hospital,
        "ayush_hospital": hospital.ayush_hospital,
    }
    treatment = f"{system.value.replace('_', ' ').capitalize()} treatment"
    if not ayush.covered:
        return Outcome(C.AYUSH, C.AYUSH, Effect.REJECT, facts, f"{treatment} is not covered by this product.")
    if ayush.requires_ayush_hospital and not hospital.ayush_hospital:
        return Outcome(
            C.AYUSH, C.AYUSH, Effect.REJECT, facts,
            f"{treatment} is covered only in an AYUSH hospital, and {hospital.name} is not one.",
        )
    return Outcome(C.AYUSH, None, Effect.PASS, facts, f"{treatment} at {hospital.name} is covered.")


def min_stay(ctx: Context) -> Outcome:
    """2.1 / 2.2: the stay meets the minimum, unless a procedure is on the day-care list."""
    claim, terms = ctx.claim, ctx.terms
    stay = claim.discharged_at - claim.admitted_at
    facts: dict[str, FactValue] = {
        "admitted_at": claim.admitted_at.isoformat(timespec="minutes"),
        "discharged_at": claim.discharged_at.isoformat(timespec="minutes"),
        "stay_minutes": stay // timedelta(minutes=1),
        "min_stay_hours": terms.min_stay_hours,
    }
    minimum = f"the {terms.min_stay_hours}-hour minimum"
    if stay >= timedelta(hours=terms.min_stay_hours):
        return Outcome(
            C.MIN_HOSPITALISATION, None, Effect.PASS, facts, f"Stay of {format_stay(stay)} meets {minimum}."
        )
    short = f"Stay of {format_stay(stay)} is under {minimum}"
    day_care = tuple(sorted({p.code for p in claim.procedures} & set(terms.day_care_procedures)))
    if day_care:
        facts["day_care_procedures"] = day_care
        verb = "is" if len(day_care) == 1 else "are"
        return Outcome(
            C.MIN_HOSPITALISATION, C.DAY_CARE, Effect.EXCEPTION, facts,
            f"{short}, but {', '.join(day_care)} {verb} on the day-care list.",
        )
    return Outcome(
        C.MIN_HOSPITALISATION, C.MIN_HOSPITALISATION, Effect.REJECT, facts,
        f"{short} and no procedure is on the day-care list.",
    )


# ---------------------------------------------------------------- stage 2: escalation


def missing_documents(ctx: Context, missing: tuple[DocType, ...], gate_rejected: bool) -> Outcome:
    """7.1: a required document is missing, and the gap could change the outcome."""
    facts: dict[str, FactValue] = {"missing": tuple(doc.value for doc in missing)}
    if not missing:
        return Outcome(C.MISSING_DOCUMENTS, None, Effect.PASS, facts, "All required documents are present.")
    names = ", ".join(doc.value.replace("_", " ").lower() for doc in missing)
    if DocType.DISCHARGE_SUMMARY in missing:
        return Outcome(
            C.MISSING_DOCUMENTS, C.MISSING_DOCUMENTS, Effect.ESCALATE, facts,
            f"Missing: {names}. Without the discharge summary the diagnosis, dates and cause cannot be checked.",
        )
    if gate_rejected:
        return Outcome(
            C.MISSING_DOCUMENTS, None, Effect.PASS, facts,
            f"Missing: {names}. A gate rejects the claim on the documents present, so the gap cannot change the outcome.",
        )
    return Outcome(
        C.MISSING_DOCUMENTS, C.MISSING_DOCUMENTS, Effect.ESCALATE, facts,
        f"Missing: {names}. No gate rejects the claim, so it cannot be settled without it.",
    )


def document_mismatch(ctx: Context, core: _Core) -> Outcome | None:
    """7.2: the claim form contradicts the hospital's records, and it could change the outcome."""
    claim, form = ctx.claim, ctx.claim.claim_form
    if form is None:
        return None
    bill_submitted = DocType.HOSPITAL_BILL in claim.documents_submitted
    bill_total = sum(line.amount for line in claim.bill)
    amount_differs = bill_submitted and form.claimed_amount != bill_total
    dates_differ = (form.admitted_at, form.discharged_at) != (claim.admitted_at, claim.discharged_at)
    facts: dict[str, FactValue] = {
        "claimed_amount": form.claimed_amount,
        "bill_total": bill_total if bill_submitted else None,
        "amount_differs": amount_differs,
        "dates_differ": dates_differ,
    }
    if not amount_differs and not dates_differ:
        return Outcome(C.DOCUMENT_MISMATCH, None, Effect.PASS, facts, "The claim form agrees with the hospital's records.")

    material, immaterial = [], []
    if amount_differs:
        difference = (
            f"the claim form claims {format_rupees(form.claimed_amount)} against a bill total of "
            f"{format_rupees(bill_total)}"
        )
        if core.rejected:
            immaterial.append(f"{difference}, but a gate rejects the claim anyway")
        else:
            material.append(f"{difference}, and the claim would otherwise be paid")
    if dates_differ:
        facts |= {
            "claim_form_admitted_at": form.admitted_at.isoformat(timespec="minutes"),
            "claim_form_discharged_at": form.discharged_at.isoformat(timespec="minutes"),
        }
        hospital_result = core.result()
        form_result = _core(ctx.with_stay(form.admitted_at, form.discharged_at)).result()
        on_form = f"{form_result[0]} {format_rupees(form_result[1])}"
        on_hospital = f"{hospital_result[0]} {format_rupees(hospital_result[1])}"
        facts |= {"result_on_hospital_dates": on_hospital, "result_on_claim_form_dates": on_form}
        if form_result != hospital_result:
            material.append(f"on the claim form's dates the claim would be {on_form}, not {on_hospital}")
        else:
            immaterial.append(
                f"the claim form's dates differ from the hospital's, but the result is {on_hospital} either way"
            )

    facts["material"] = bool(material)
    if material:
        return Outcome(
            C.DOCUMENT_MISMATCH, C.DOCUMENT_MISMATCH, Effect.ESCALATE, facts,
            f"The claim form contradicts the hospital's records: {'; '.join(material)}.",
        )
    text = "; ".join(immaterial)
    return Outcome(
        C.DOCUMENT_MISMATCH, None, Effect.PASS, facts,
        f"{text[:1].upper()}{text[1:]}. Decided on the hospital's records.",
    )


# ---------------------------------------------------------------- stage 3: amount


def pre_post_window(ctx: Context, running: Running) -> tuple[Running, list[Outcome]]:
    """3.5 / 3.6: drop pre- and post-hospitalisation lines dated outside their windows."""
    claim, terms = ctx.claim, ctx.terms
    admitted, discharged = claim.admitted_at.date(), claim.discharged_at.date()
    windows = (
        (Phase.PRE, C.PRE_HOSPITALISATION, terms.pre_hospitalisation_days, "before admission",
         admitted - timedelta(days=terms.pre_hospitalisation_days), admitted),
        (Phase.POST, C.POST_HOSPITALISATION, terms.post_hospitalisation_days, "after discharge",
         discharged, discharged + timedelta(days=terms.post_hospitalisation_days)),
    )
    lines, total, outcomes = running.lines, running.total, []
    for phase, clause, window_days, when, start, end in windows:
        in_phase = [line for line in lines if line.phase is phase]
        if not in_phase:
            continue
        outside = tuple(line for line in in_phase if not start <= line.date <= end)
        amount = sum(line.amount for line in outside)
        facts: dict[str, FactValue] = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "lines_outside": tuple(line.line_id for line in outside),
            "amount_removed": amount,
        }
        window = f"{start} to {end} ({window_days} days {when})"
        if outside:
            items = ", ".join(f"{line.line_id} ({line.description}, {line.date})" for line in outside)
            note = f"Covered: bills from {window}. Dropped {items}: {format_rupees(amount)}."
        else:
            note = f"Every {phase.value.lower()}-hospitalisation bill falls within {window}."
        effect, fired = (Effect.REDUCE, clause) if amount else (Effect.PASS, None)
        outcomes.append(Outcome(clause, fired, effect, facts, note, total, total - amount))
        dropped = {line.line_id for line in outside}
        lines = tuple(line for line in lines if line.line_id not in dropped)
        total -= amount
    return Running(lines, total), outcomes


def line_exclusions(ctx: Context, running: Running) -> tuple[Running, list[Outcome]]:
    """A1 and line-level exclusions: remove listed items, one rule at a time in product order."""
    lines, total, outcomes = running.lines, running.total, []
    for rule in ctx.terms.line_exclusions:
        listed = set(rule.item_codes)
        removed = tuple(line for line in lines if line.item_code in listed)
        amount = sum(line.amount for line in removed)
        facts: dict[str, FactValue] = {
            "lines_removed": tuple(line.line_id for line in removed),
            "amount_removed": amount,
        }
        if removed:
            items = ", ".join(f"{line.line_id} ({line.description})" for line in removed)
            note = f"Removed {items}: {format_rupees(amount)}."
        else:
            note = "No bill line is on this list."
        effect, fired = (Effect.REDUCE, rule.clause_id) if amount else (Effect.PASS, None)
        outcomes.append(Outcome(rule.clause_id, fired, effect, facts, note, total, total - amount))
        lines = tuple(line for line in lines if line.item_code not in listed)
        total -= amount
    return Running(lines, total), outcomes


def room_rent(ctx: Context, running: Running) -> tuple[Running, list[Outcome]]:
    """3.1: a room above the cap scales the room line, the charges counted in the room
    rate and the room-associated lines by cap / rate."""
    terms = ctx.terms
    return _scale_to_cap(
        ctx, running, BillCategory.ROOM, terms.room_cap, terms.room_rate_includes, terms.room_associated,
        C.ROOM_RENT, "room",
    )


def icu(ctx: Context, running: Running) -> tuple[Running, list[Outcome]]:
    """3.2: an ICU above its cap scales the ICU line and ICU-associated lines by cap / rate."""
    terms = ctx.terms
    return _scale_to_cap(
        ctx, running, BillCategory.ICU, terms.icu_cap, (), terms.icu_associated, C.ICU_LIMIT, "ICU"
    )


def disease_sublimit(ctx: Context, running: Running) -> tuple[Running, list[Outcome]]:
    """3.3: cap the running amount at the matching sub-limit, per unit of the matching procedures."""
    if not ctx.terms.sublimits:
        return running, []
    claim, total = ctx.claim, running.total
    matched = [(sublimit, _matched_by(sublimit.match, claim)) for sublimit in ctx.terms.sublimits]
    matched = [(sublimit, reasons) for sublimit, reasons in matched if reasons]
    if not matched:
        note = "No disease-wise sub-limit applies to this claim."
        return running, [Outcome(C.DISEASE_SUBLIMIT, None, Effect.PASS, {"sublimit": None}, note, total, total)]
    if len(matched) > 1:
        raise UnsupportedCase("more than one disease-wise sub-limit applies to this claim")

    sublimit, reasons = matched[0]
    units = sum(p.units for p in claim.procedures if p.code in sublimit.match.procedure_codes) or 1
    per_unit = cap_amount(sublimit.cap_per_unit, ctx.policy.sum_insured)
    limit = per_unit * units
    facts: dict[str, FactValue] = {
        "sublimit": sublimit.name,
        "matched_by": reasons,
        "cap_per_unit": _exact(per_unit),
        "units": units,
        "cap": _exact(limit),
    }
    what = (
        f"the {format_rupees(limit)} sub-limit ({sublimit.name}: "
        f"{_describe_cap(sublimit.cap_per_unit, ctx.policy.sum_insured)} x {units})"
    )
    return _cap_running(running, limit, C.DISEASE_SUBLIMIT, facts, what)


def ayush_cap(ctx: Context, running: Running) -> tuple[Running, list[Outcome]]:
    """3.4: cap an AYUSH claim at the product's AYUSH limit."""
    cap = ctx.terms.ayush.cap
    if ctx.claim.treatment_system is TreatmentSystem.ALLOPATHY or cap is None:
        return running, []
    limit = cap_amount(cap, ctx.policy.sum_insured)
    facts: dict[str, FactValue] = {"cap": _exact(limit)}
    what = f"the AYUSH limit of {_describe_cap(cap, ctx.policy.sum_insured)}"
    return _cap_running(running, limit, C.AYUSH, facts, what)


def deductible(ctx: Context, running: Running) -> tuple[Running, list[Outcome]]:
    """5.1: the policyholder bears the first `deductible` rupees of the claim."""
    amount, total = ctx.policy.deductible, running.total
    if not amount:
        return running, []
    deduction = min(amount, total)
    facts: dict[str, FactValue] = {"deductible": amount, "base": total, "deduction": deduction}
    note = f"Deductible of {format_rupees(amount)} on {format_rupees(total)}: {format_rupees(deduction)} off."
    effect, fired = (Effect.REDUCE, C.DEDUCTIBLE) if deduction else (Effect.PASS, None)
    return Running(running.lines, total - deduction), [
        Outcome(C.DEDUCTIBLE, fired, effect, facts, note, total, total - deduction)
    ]


def copay(ctx: Context, running: Running) -> tuple[Running, list[Outcome]]:
    """5.2: the policyholder bears copay_bp of the running amount."""
    bp, total = ctx.policy.copay_bp, running.total
    if not bp:
        return running, []
    deduction = _round_half_up(Fraction(total * bp, BP_SCALE))
    facts: dict[str, FactValue] = {"copay_bp": bp, "base": total, "deduction": deduction}
    note = f"Co-pay of {format_percent(bp)} on {format_rupees(total)}: {format_rupees(deduction)} off."
    effect, fired = (Effect.REDUCE, C.COPAY) if deduction else (Effect.PASS, None)
    return Running(running.lines, total - deduction), [
        Outcome(C.COPAY, fired, effect, facts, note, total, total - deduction)
    ]


def sum_insured(ctx: Context, running: Running) -> tuple[Running, list[Outcome]]:
    """5.3: pay at most the sum insured plus cumulative bonus."""
    policy = ctx.policy
    limit = policy.sum_insured + policy.cumulative_bonus
    facts: dict[str, FactValue] = {
        "sum_insured": policy.sum_insured,
        "cumulative_bonus": policy.cumulative_bonus,
        "limit": limit,
    }
    what = (
        f"the {format_rupees(limit)} limit (sum insured {format_rupees(policy.sum_insured)} "
        f"+ bonus {format_rupees(policy.cumulative_bonus)})"
    )
    return _cap_running(running, Fraction(limit), C.SUM_INSURED, facts, what)


_AMOUNT_STEPS: dict[str, AmountStep] = {
    step.__name__: step
    for step in (
        pre_post_window,
        line_exclusions,
        room_rent,
        icu,
        disease_sublimit,
        ayush_cap,
        deductible,
        copay,
        sum_insured,
    )
}


# ---------------------------------------------------------------- shared rule shapes


def _scale_to_cap(
    ctx: Context,
    running: Running,
    category: BillCategory,
    cap: Cap | None,
    includes: tuple[BillCategory, ...],
    associated: tuple[BillCategory, ...],
    clause: str,
    label: str,
) -> tuple[Running, list[Outcome]]:
    """Room rent and ICU: if the daily rate is above the cap, pay the `category`
    line, the charges counted in its rate and the associated lines at cap / rate.

    The daily rate is the `category` line's amount plus the inpatient `includes`
    charges, divided by the `category` line's days (its qty)."""
    rated = [line for line in running.lines if line.category is category]
    if cap is None or not rated:
        return running, []
    if len(rated) > 1:
        raise UnsupportedCase(f"more than one {label} line (a mid-stay rate change) is not modelled")
    line = rated[0]
    inpatient = [other for other in running.lines if other.phase is Phase.INPATIENT]
    counted = [other for other in inpatient if other.category in includes]
    rate = Fraction(line.amount + sum(other.amount for other in counted), line.qty)
    cap_per_day = cap_amount(cap, ctx.policy.sum_insured)
    facts: dict[str, FactValue] = {
        f"{category.value.lower()}_line": line.line_id,
        "rate": _exact(rate),
        "days": line.qty,
        "cap_per_day": _exact(cap_per_day),
    }
    if includes:
        facts["rate_includes"] = tuple(other.line_id for other in counted)
    shown, total = f"{format_rupees(rate)}/day", running.total
    if counted:
        names = ", ".join(f"{other.line_id} ({other.description})" for other in counted)
        shown += f" (the {label} line's {format_rupees(line.unit_price)}/day, plus {names} counted in the rate)"
    limit = _describe_cap(cap, ctx.policy.sum_insured)
    title = label[:1].upper() + label[1:]
    if rate <= cap_per_day:
        note = f"{title} rate {shown} is within the cap of {limit}/day."
        return running, [Outcome(clause, None, Effect.PASS, facts, note, total, total)]

    ratio = cap_per_day / rate
    scaled = tuple(
        other for other in inpatient
        if other.category is category or other.category in includes or other.category in associated
    )
    base = sum(other.amount for other in scaled)
    deduction = _round_half_up(base * (1 - ratio))
    facts |= {
        "ratio": str(ratio),
        "lines_scaled": tuple(other.line_id for other in scaled),
        "amount_scaled": base,
        "deduction": deduction,
    }
    if len(scaled) == 1:
        what = f"the {label} line ({format_rupees(base)}) is paid"
    else:
        what = f"the {label} line and the charges scaled with it ({format_rupees(base)}) are paid"
    note = (
        f"{title} rate {shown} is above the cap of {limit}/day, so {what} at {ratio}: "
        f"{format_rupees(deduction)} off."
    )
    effect, fired = (Effect.REDUCE, clause) if deduction else (Effect.PASS, None)
    outcome = Outcome(clause, fired, effect, facts, note, total, total - deduction)
    return Running(running.lines, total - deduction), [outcome]


def _cap_running(
    running: Running, limit: Fraction, clause: str, facts: dict[str, FactValue], what: str
) -> tuple[Running, list[Outcome]]:
    """Sub-limits, AYUSH and sum insured: pay at most `limit`; the excess is the deduction."""
    total = running.total
    if total <= limit:
        note = f"{format_rupees(total)} is within {what}."
        return running, [Outcome(clause, None, Effect.PASS, facts, note, total, total)]
    deduction = _round_half_up(total - limit)
    note = f"{format_rupees(total)} is above {what}: capped, {format_rupees(deduction)} off."
    effect, fired = (Effect.REDUCE, clause) if deduction else (Effect.PASS, None)
    return Running(running.lines, total - deduction), [
        Outcome(clause, fired, effect, facts, note, total, total - deduction)
    ]


def _matched_by(match: Match, claim: Claim) -> tuple[str, ...]:
    """Why a claim matches a code list, e.g. ('diagnosis H25.1', 'procedure PX-PHACO').
    Empty when it does not match."""
    reasons = []
    code = claim.primary_dx.icd10
    if any(code.startswith(prefix) for prefix in match.icd10_prefixes):
        reasons.append(f"diagnosis {code}")
    reasons += [f"procedure {p.code}" for p in claim.procedures if p.code in match.procedure_codes]
    return tuple(reasons)


# ---------------------------------------------------------------- verdict and answer key


def _verdict(outcomes: list[Outcome], payable: int) -> tuple[Verdict, int, tuple[str, ...]]:
    """(verdict, payable, answer-key clauses) for a list of outcomes."""
    escalating = {o.fired_clause for o in outcomes if o.effect is Effect.ESCALATE}
    if escalating:
        return Verdict.ESCALATE, 0, _sorted_clauses(escalating)
    rejecting = {o.fired_clause for o in outcomes if o.effect is Effect.REJECT}
    if rejecting:
        return Verdict.REJECT, 0, _sorted_clauses(rejecting)
    clauses = {o.fired_clause for o in outcomes if o.effect in (Effect.EXCEPTION, Effect.REDUCE)}
    limited = any(o.effect is Effect.REDUCE and o.fired_clause not in _COST_SHARING for o in outcomes)
    if not payable:
        return Verdict.REJECT, 0, _sorted_clauses(clauses)
    return (Verdict.PARTIAL if limited else Verdict.APPROVE), payable, _sorted_clauses(clauses)


def _decision(outcomes: list[Outcome], payable: int) -> Decision:
    verdict, payable, clauses = _verdict(outcomes, payable)
    return Decision(
        verdict=verdict,
        payable=payable,
        clauses=clauses,
        checks=tuple(sorted({o.check for o in outcomes})),
        reasoning_trace=tuple(
            TraceStep(
                seq=seq,
                check=o.check,
                fired_clause=o.fired_clause,
                effect=o.effect,
                facts=o.facts,
                note=o.note,
                before=o.before,
                after=o.after,
            )
            for seq, o in enumerate(outcomes, start=1)
        ),
    )


def _sorted_clauses(clauses: set[str | None]) -> tuple[str, ...]:
    return tuple(sorted(c for c in clauses if c is not None))


# ---------------------------------------------------------------- arithmetic


def cap_amount(cap: Cap, sum_insured: int) -> Fraction:
    """The cap in rupees: its fixed amount, its share of the base sum insured, or the lower."""
    options = []
    if cap.rupees is not None:
        options.append(Fraction(cap.rupees))
    if cap.bp_of_si is not None:
        options.append(Fraction(sum_insured * cap.bp_of_si, BP_SCALE))
    return min(options)


def _describe_cap(cap: Cap, sum_insured: int) -> str:
    """'₹5,000', or '₹3,500 (1% of sum insured)', or '₹5,000 (2% of sum insured, at most ₹5,000)'."""
    amount = format_rupees(cap_amount(cap, sum_insured))
    if cap.bp_of_si is None:
        return amount
    most = f", at most {format_rupees(cap.rupees)}" if cap.rupees is not None else ""
    return f"{amount} ({format_percent(cap.bp_of_si)} of sum insured{most})"


def _round_half_up(amount: Fraction) -> int:
    """Nearest whole rupee, halves up. Amounts here are never negative."""
    if amount < 0:
        raise ValueError(f"negative amount {amount}")
    return math.floor(amount + _HALF)


def _exact(amount: Fraction) -> FactValue:
    """A whole rupee amount as int; anything finer as an exact fraction string."""
    return amount.numerator if amount.denominator == 1 else str(amount)
