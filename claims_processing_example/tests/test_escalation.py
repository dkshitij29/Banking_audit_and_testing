"""Stage 2: escalate only when a missing document or a contradiction could change the outcome."""

import datetime as dt

import pytest

from engine import adjudicate
from engine import clauses as C
from engine.schema import DocType, Effect, Verdict
from tests.builders import (
    APPENDICECTOMY,
    APPENDICITIS,
    build_claim,
    build_policy,
    pharmacy,
    placeholder_terms,
    pre,
    consultant,
    surgeon,
)

PAYABLE_BILL = [surgeon(20_000), pharmacy(5_000)]  # 25,000, nothing removed


def claim(*, admitted="2025-08-04 10:00", discharged="2025-08-07 10:00", items=PAYABLE_BILL, **kwargs):
    return build_claim(
        admitted=admitted,
        discharged=discharged,
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=items,
        **kwargs,
    )


def short_stay_claim(**kwargs):
    """Rejected at the gates: a 10-hour stay with no day-care procedure."""
    return claim(admitted="2025-08-04 08:00", discharged="2025-08-04 18:00", **kwargs)


def decide(claim_, terms=None, **policy_args):
    return adjudicate(build_policy(terms or placeholder_terms(), **policy_args), claim_)


def step(decision, clause):
    return next(s for s in decision.reasoning_trace if s.check == clause)


# ---------------------------------------------------------------- complete and consistent


def test_complete_consistent_documents_are_checked_and_pass():
    decision = decide(claim())
    assert (decision.verdict, decision.payable) == (Verdict.APPROVE, 25_000)
    assert step(decision, C.MISSING_DOCUMENTS).effect is Effect.PASS
    assert step(decision, C.DOCUMENT_MISMATCH).effect is Effect.PASS


# ---------------------------------------------------------------- missing documents


def test_a_missing_discharge_summary_escalates_before_any_gate():
    decision = decide(claim(documents=[DocType.CLAIM_FORM, DocType.HOSPITAL_BILL]))
    assert (decision.verdict, decision.payable, decision.clauses) == (Verdict.ESCALATE, 0, (C.MISSING_DOCUMENTS,))
    assert decision.checks == (C.MISSING_DOCUMENTS,)


@pytest.mark.parametrize("missing", [DocType.HOSPITAL_BILL, DocType.CLAIM_FORM])
def test_a_missing_bill_or_claim_form_escalates_a_claim_that_would_be_paid(missing):
    decision = decide(claim(documents=[doc for doc in DocType if doc is not missing]))
    assert (decision.verdict, decision.clauses) == (Verdict.ESCALATE, (C.MISSING_DOCUMENTS,))


@pytest.mark.parametrize("missing", [DocType.HOSPITAL_BILL, DocType.CLAIM_FORM])
def test_a_missing_bill_or_claim_form_cannot_matter_when_a_gate_rejects(missing):
    decision = decide(short_stay_claim(documents=[doc for doc in DocType if doc is not missing]))
    assert (decision.verdict, decision.clauses) == (Verdict.REJECT, (C.MIN_HOSPITALISATION,))
    documents = step(decision, C.MISSING_DOCUMENTS)
    assert (documents.effect, documents.facts["missing"]) == (Effect.PASS, (missing.value,))


def test_a_document_the_product_does_not_require_is_never_missing():
    terms = placeholder_terms(required_documents=(DocType.DISCHARGE_SUMMARY, DocType.HOSPITAL_BILL))
    decision = decide(claim(documents=[DocType.DISCHARGE_SUMMARY, DocType.HOSPITAL_BILL]), terms=terms)
    assert decision.verdict is Verdict.APPROVE


def test_an_escalated_claim_is_not_decided_further():
    decision = decide(claim(documents=[DocType.CLAIM_FORM, DocType.DISCHARGE_SUMMARY]))
    stage_3 = {C.NON_PAYABLE, C.SUM_INSURED}
    assert not stage_3 & set(decision.checks)


# ---------------------------------------------------------------- claimed amount


def test_a_claimed_amount_that_differs_escalates_a_claim_that_would_be_paid():
    decision = decide(claim(claimed_amount=30_000))
    assert (decision.verdict, decision.clauses) == (Verdict.ESCALATE, (C.DOCUMENT_MISMATCH,))


def test_a_claimed_amount_that_differs_cannot_matter_when_a_gate_rejects():
    decision = decide(short_stay_claim(claimed_amount=30_000))
    assert decision.verdict is Verdict.REJECT
    mismatch = step(decision, C.DOCUMENT_MISMATCH)
    assert (mismatch.effect, mismatch.facts["amount_differs"]) == (Effect.PASS, True)


def test_no_claim_form_means_no_comparison():
    terms = placeholder_terms(required_documents=(DocType.DISCHARGE_SUMMARY, DocType.HOSPITAL_BILL))
    decision = decide(claim(documents=[DocType.DISCHARGE_SUMMARY, DocType.HOSPITAL_BILL]), terms=terms)
    assert C.DOCUMENT_MISMATCH not in decision.checks


# ---------------------------------------------------------------- dates


def test_claim_form_dates_that_flip_a_waiting_period_escalate():
    # Placeholder initial wait: 100 days from 1 Apr 2025, over on 10 Jul 2025.
    decision = decide(
        claim(admitted="2025-07-02 10:00", discharged="2025-07-05 10:00",
              form_admitted="2025-07-12 10:00", form_discharged="2025-07-15 10:00"),
        first_inception=dt.date(2025, 4, 1),
    )
    assert (decision.verdict, decision.clauses) == (Verdict.ESCALATE, (C.DOCUMENT_MISMATCH,))
    assert C.INITIAL_WAITING not in decision.clauses


def test_claim_form_dates_that_move_a_bill_out_of_its_window_escalate():
    # On the hospital's dates the 20 Jun consultation is inside the 50-day pre window
    # (from 15 Jun). On the claim form's admission of 20 Aug the window starts 1 Jul.
    decision = decide(
        claim(items=[*PAYABLE_BILL, pre(consultant(1_000), on="2025-06-20")],
              form_admitted="2025-08-20 10:00", form_discharged="2025-08-23 10:00")
    )
    assert decision.verdict is Verdict.ESCALATE
    facts = step(decision, C.DOCUMENT_MISMATCH).facts
    assert (facts["result_on_hospital_dates"], facts["result_on_claim_form_dates"]) == (
        "APPROVE ₹26,000",
        "PARTIAL ₹25,000",
    )


def test_claim_form_dates_that_cannot_matter_are_decided_on_the_hospitals_records():
    decision = decide(claim(form_admitted="2025-08-04 09:00"))
    assert (decision.verdict, decision.payable) == (Verdict.APPROVE, 25_000)
    mismatch = step(decision, C.DOCUMENT_MISMATCH)
    assert (mismatch.effect, mismatch.facts["dates_differ"], mismatch.facts["material"]) == (Effect.PASS, True, False)


def test_short_stay_on_the_claim_form_would_reject_so_it_escalates():
    # Hospital: 72 h. Claim form: 10 h, which fails the minimum stay.
    decision = decide(claim(form_admitted="2025-08-07 00:00"))
    assert decision.verdict is Verdict.ESCALATE
