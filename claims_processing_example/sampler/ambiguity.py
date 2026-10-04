"""Readings a policy wording leaves open, and the cases that would depend on them.

Where a wording can defensibly be read two ways, the engine implements one
reading (corpus/mapping.yaml records which) and the sampler discards any drawn
case whose answer the other reading could change. No case in a dataset then
depends on a contested reading, so an agent is never marked wrong for taking the
other one.

A guard looks at a drawn case and its decision and returns why the case must be
discarded, or None. GENERAL guards apply to every product. A product profile
lists the guards its own wording needs (ProductProfile.ambiguities); they are
written generically so another wording with the same gap can reuse them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from engine import adjudicate
from engine import clauses as C
from engine.schema import BillCategory, Claim, Decision, Phase, Policy, TreatmentSystem

Guard = Callable[[Policy, Claim, Decision], str | None]


def _fired(decision: Decision) -> set[str]:
    return {step.fired_clause for step in decision.reasoning_trace if step.fired_clause}


def _stays(claim: Claim) -> list[tuple[dt.datetime, dt.datetime]]:
    """The stays a decision can rest on: the hospital's, and the claim form's."""
    stays = [(claim.admitted_at, claim.discharged_at)]
    if claim.claim_form is not None:
        stays.append((claim.claim_form.admitted_at, claim.claim_form.discharged_at))
    return stays


def _has_pre_post_bills(claim: Claim) -> bool:
    return any(line.phase is not Phase.INPATIENT for line in claim.bill)


# ---------------------------------------------------------------- every product


def wait_ends_on_admission_day(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """Whether "30 days from 1 April" still covers 1 May depends on whether the
    first day is counted. A wait that ends on the day of admission is left alone."""
    ends = {step.facts["wait_over_on"] for step in decision.reasoning_trace if "wait_over_on" in step.facts}
    if any(admitted.date().isoformat() in ends for admitted, _ in _stays(claim)):
        return "a waiting period ends on the admission day"
    return None


def bill_on_last_day_of_window(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """Whether "30 days prior to admission" includes the 30th day before it is the
    same question. A pre/post bill dated on the last day of its window is left alone."""
    terms = policy.terms
    for admitted, discharged in _stays(claim):
        first_pre = admitted.date() - dt.timedelta(days=terms.pre_hospitalisation_days)
        last_post = discharged.date() + dt.timedelta(days=terms.post_hospitalisation_days)
        for line in claim.bill:
            if (line.phase is Phase.PRE and line.date == first_pre) or (
                line.phase is Phase.POST and line.date == last_post
            ):
                return "a pre/post-hospitalisation bill is dated on the last day of its window"
    return None


def stay_of_exactly_the_minimum(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """Wordings say both "a minimum of 24 consecutive hours" and "more than 24
    hours"; they disagree about a stay of exactly 24:00."""
    minimum = dt.timedelta(hours=policy.terms.min_stay_hours)
    if any(discharged - admitted == minimum for admitted, discharged in _stays(claim)):
        return "the stay is exactly the minimum length"
    return None


GENERAL: tuple[Guard, ...] = (wait_ends_on_admission_day, bill_on_last_day_of_window, stay_of_exactly_the_minimum)


# ---------------------------------------------------------------- wordings that need them


def bonus_in_percentage_limits(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """A wording whose definition of Sum Insured includes the cumulative bonus
    leaves open whether "2% of sum insured" counts the bonus. The engine does not
    count it; the case is kept only if counting it gives the same answer."""
    terms = policy.terms
    caps = [terms.room_cap, terms.icu_cap, terms.ayush.cap, *(s.cap_per_unit for s in terms.sublimits)]
    if not policy.cumulative_bonus or not any(cap is not None and cap.bp_of_si for cap in caps):
        return None
    counted = policy.model_copy(
        update={"sum_insured": policy.sum_insured + policy.cumulative_bonus, "cumulative_bonus": 0}
    )
    other = adjudicate(counted, claim)
    if (other.verdict, other.payable, other.clauses) != (decision.verdict, decision.payable, decision.clauses):
        return "the answer depends on whether percentage limits count the cumulative bonus"
    return None


def copay_after_sum_insured(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """A wording that applies co-pay to the amount "admissible and payable" leaves
    open whether co-pay comes before or after the sum insured limit. The engine
    applies it before; the two orders agree only if the limit is never reached."""
    limit = policy.sum_insured + policy.cumulative_bonus
    for step in decision.reasoning_trace:
        if step.check == C.COPAY and step.before is not None and step.before > limit:
            return "co-pay before or after the sum insured limit gives different answers"
    return None


def room_limit_with_icu_stay(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """A wording that scales "all other expenses" with room rent, and caps ICU
    charges on their own, leaves open whether ICU charges are scaled with the room."""
    if C.ROOM_RENT in _fired(decision) and any(line.category is BillCategory.ICU for line in claim.bill):
        return "whether ICU charges are scaled with room rent is open"
    return None


def room_limit_with_pre_post_bills(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """The same wording leaves open whether pre/post-hospitalisation bills are
    "expenses incurred at the Hospital" and so scaled with room rent. The engine
    never scales them."""
    if C.ROOM_RENT in _fired(decision) and _has_pre_post_bills(claim):
        return "whether pre/post bills are scaled with room rent is open"
    return None


def pre_post_with_day_care(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """A wording that covers pre/post-hospitalisation expenses only for a
    "hospitalization requiring inpatient care" leaves open whether day care qualifies."""
    if C.DAY_CARE in _fired(decision) and _has_pre_post_bills(claim):
        return "whether pre/post bills are covered for day care is open"
    return None


def sublimit_with_pre_post(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """A disease-wise limit on "expenses incurred for treatment of cataract" leaves
    open whether the pre/post bills count against it. The engine counts them."""
    matched = any(
        step.check == C.DISEASE_SUBLIMIT and step.facts.get("sublimit") for step in decision.reasoning_trace
    )
    if matched and _has_pre_post_bills(claim):
        return "whether pre/post bills count against the disease-wise limit is open"
    return None


def room_limit_on_ayush(policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """A wording that covers AYUSH treatment "up to the limit of sum insured" in a
    section of its own leaves open whether the room and ICU limits apply to it."""
    if claim.treatment_system is not TreatmentSystem.ALLOPATHY and {C.ROOM_RENT, C.ICU_LIMIT} & _fired(decision):
        return "whether room and ICU limits apply to AYUSH treatment is open"
    return None


def first_reason(guards: tuple[Guard, ...], policy: Policy, claim: Claim, decision: Decision) -> str | None:
    """The first guard's reason to discard the case, or None to keep it."""
    for guard in guards:
        reason = guard(policy, claim, decision)
        if reason is not None:
            return reason
    return None
