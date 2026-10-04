"""Runs the golden cases in tests/golden_cases.py against the engine."""

import pytest

from engine import adjudicate
from engine import clauses as C
from engine.schema import Effect
from tests.golden_cases import (
    GOLDEN,
    g10_admitted_after_policy_ended,
    g13_day_care_cataract,
    g16_accident_exception_but_short_stay,
    g17_cataract_inside_specified_disease_wait,
    g32_discharge_summary_missing,
    g36_claim_form_dates_differ_but_cannot_matter,
)


@pytest.mark.parametrize("build", GOLDEN, ids=lambda build: build.__name__)
def test_golden_case(build):
    case = build()
    decision = adjudicate(case.policy, case.claim)
    got = (decision.verdict, decision.payable, decision.clauses)
    assert got == (case.expected.verdict, case.expected.payable, case.expected.clauses)


def test_every_golden_case_shows_its_working():
    for build in GOLDEN:
        assert build.__doc__ and "Working" in build.__doc__ and "Expected:" in build.__doc__, build.__name__


DOCUMENT_CHECKS = {C.MISSING_DOCUMENTS, C.DOCUMENT_MISMATCH}


def test_no_other_gate_is_checked_once_the_policy_is_not_in_force():
    case = g10_admitted_after_policy_ended()
    trace = adjudicate(case.policy, case.claim).reasoning_trace
    assert [step.check for step in trace if step.check not in DOCUMENT_CHECKS] == [C.POLICY_PERIOD]


def test_nothing_else_is_checked_without_a_discharge_summary():
    case = g32_discharge_summary_missing()
    trace = adjudicate(case.policy, case.claim).reasoning_trace
    assert [(step.check, step.effect) for step in trace] == [(C.MISSING_DOCUMENTS, Effect.ESCALATE)]


def test_an_immaterial_contradiction_is_recorded_but_does_not_fire():
    case = g36_claim_form_dates_differ_but_cannot_matter()
    step = next(s for s in adjudicate(case.policy, case.claim).reasoning_trace if s.check == C.DOCUMENT_MISMATCH)
    assert (step.effect, step.facts["dates_differ"], step.facts["material"]) == (Effect.PASS, True, False)


@pytest.mark.parametrize(
    "build, exception",
    [
        (g16_accident_exception_but_short_stay, C.INITIAL_WAITING_ACCIDENT),
        (g17_cataract_inside_specified_disease_wait, C.DAY_CARE),
    ],
)
def test_rescuing_exception_is_in_the_trace_but_not_the_answer_key_when_a_gate_rejects(build, exception):
    case = build()
    decision = adjudicate(case.policy, case.claim)
    exceptions = [step.fired_clause for step in decision.reasoning_trace if step.effect is Effect.EXCEPTION]
    assert exceptions == [exception]
    assert exception not in decision.clauses


def test_room_rent_is_not_checked_without_a_room_line():
    case = g13_day_care_cataract()
    decision = adjudicate(case.policy, case.claim)
    assert C.ROOM_RENT not in decision.checks
