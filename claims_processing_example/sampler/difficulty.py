"""Difficulty tiers: where the facts a decision needs appear in the document bundle.

Difficulty is where the facts live, not how hard the arithmetic is (CLAUDE.md).
This module turns that into a placement plan: for every fact the gold answer
depends on, the documents that must state it. The renderer (build step 4) writes
to the plan and the validator (step 5) checks it.

Every fact has a natural home: dates and diagnosis in the discharge summary,
amounts in the bill, policy values on the certificate, product rules in the
wording. The tiers add copies:

- EASY: every claim fact the decision needs also appears on the claim form, and
  every product rule it needs is also stated on the policy certificate.
- MEDIUM: claim facts stay in their natural homes, spread over two or three
  documents; product rules are also stated on the certificate.
- HARD: nothing is copied. At least one product rule that decides the case
  appears only in the policy wording, and the diagnosis is written clinically.

Three product rules live only in the wording in every tier, because no real
certificate or claim form restates them: the list of non-payable items, the
list of excluded bill items, and the required claim documents. Every bill
carries non-payable items, so that lookup is part of every case, easy included.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from engine import clauses as C
from engine.schema import Decision, DocType, Effect, ProductTerms


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Doc(StrEnum):
    POLICY_CERTIFICATE = "POLICY_CERTIFICATE"
    POLICY_WORDING = "POLICY_WORDING"
    CLAIM_FORM = "CLAIM_FORM"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    HOSPITAL_BILL = "HOSPITAL_BILL"


class DiagnosisStyle(StrEnum):
    PLAIN = "PLAIN"
    CLINICAL = "CLINICAL"


class Fact(StrEnum):
    # the claim
    ADMISSION = "ADMISSION"
    DISCHARGE = "DISCHARGE"
    DIAGNOSIS = "DIAGNOSIS"
    PROCEDURES = "PROCEDURES"
    CAUSE = "CAUSE"
    TREATMENT_SYSTEM = "TREATMENT_SYSTEM"
    AYUSH_HOSPITAL = "AYUSH_HOSPITAL"
    BILL_LINES = "BILL_LINES"
    ROOM_RATE = "ROOM_RATE"
    ICU_RATE = "ICU_RATE"
    PRE_POST_BILLS = "PRE_POST_BILLS"
    CLAIMED_AMOUNT = "CLAIMED_AMOUNT"
    CLAIM_FORM_DATES = "CLAIM_FORM_DATES"
    # the policy
    POLICY_PERIOD = "POLICY_PERIOD"
    SUM_INSURED = "SUM_INSURED"
    CUMULATIVE_BONUS = "CUMULATIVE_BONUS"
    COPAY = "COPAY"
    DEDUCTIBLE = "DEDUCTIBLE"
    FIRST_INCEPTION = "FIRST_INCEPTION"
    DECLARED_PEDS = "DECLARED_PEDS"
    ROOM_CAP = "ROOM_CAP"
    # the product's rules
    INITIAL_WAIT = "INITIAL_WAIT"
    SPECIFIED_DISEASES = "SPECIFIED_DISEASES"
    PED_WAIT = "PED_WAIT"
    EXCLUSIONS = "EXCLUSIONS"
    AYUSH_TERMS = "AYUSH_TERMS"
    MIN_STAY = "MIN_STAY"
    DAY_CARE_LIST = "DAY_CARE_LIST"
    ROOM_ASSOCIATED = "ROOM_ASSOCIATED"
    """Which charges count in the daily room rate, and which are scaled with it.
    The room cap itself is ROOM_CAP."""
    ICU_CAP = "ICU_CAP"
    SUBLIMITS = "SUBLIMITS"
    PRE_POST_WINDOWS = "PRE_POST_WINDOWS"
    NON_PAYABLES = "NON_PAYABLES"
    EXCLUDED_ITEMS = "EXCLUDED_ITEMS"
    REQUIRED_DOCUMENTS = "REQUIRED_DOCUMENTS"


F, D = Fact, Doc

HOME: dict[Fact, tuple[Doc, ...]] = {
    F.ADMISSION: (D.DISCHARGE_SUMMARY,),
    F.DISCHARGE: (D.DISCHARGE_SUMMARY,),
    F.DIAGNOSIS: (D.DISCHARGE_SUMMARY,),
    F.PROCEDURES: (D.DISCHARGE_SUMMARY,),
    F.CAUSE: (D.DISCHARGE_SUMMARY,),
    F.TREATMENT_SYSTEM: (D.DISCHARGE_SUMMARY,),
    F.AYUSH_HOSPITAL: (D.DISCHARGE_SUMMARY,),
    F.BILL_LINES: (D.HOSPITAL_BILL,),
    F.ROOM_RATE: (D.HOSPITAL_BILL,),
    F.ICU_RATE: (D.HOSPITAL_BILL,),
    F.PRE_POST_BILLS: (D.HOSPITAL_BILL,),
    F.CLAIMED_AMOUNT: (D.CLAIM_FORM,),
    F.CLAIM_FORM_DATES: (D.CLAIM_FORM,),
    F.POLICY_PERIOD: (D.POLICY_CERTIFICATE,),
    F.SUM_INSURED: (D.POLICY_CERTIFICATE,),
    F.CUMULATIVE_BONUS: (D.POLICY_CERTIFICATE,),
    F.COPAY: (D.POLICY_CERTIFICATE, D.POLICY_WORDING),
    F.DEDUCTIBLE: (D.POLICY_CERTIFICATE,),
    F.FIRST_INCEPTION: (D.POLICY_CERTIFICATE,),
    F.DECLARED_PEDS: (D.POLICY_CERTIFICATE,),
    F.ROOM_CAP: (D.POLICY_CERTIFICATE, D.POLICY_WORDING),
    **{fact: (D.POLICY_WORDING,) for fact in (
        F.INITIAL_WAIT, F.SPECIFIED_DISEASES, F.PED_WAIT, F.EXCLUSIONS, F.AYUSH_TERMS, F.MIN_STAY,
        F.DAY_CARE_LIST, F.ROOM_ASSOCIATED, F.ICU_CAP, F.SUBLIMITS, F.PRE_POST_WINDOWS, F.NON_PAYABLES,
        F.EXCLUDED_ITEMS, F.REQUIRED_DOCUMENTS,
    )},
}

CLAIM_FACTS = (F.ADMISSION, F.DISCHARGE, F.DIAGNOSIS, F.PROCEDURES, F.CAUSE, F.TREATMENT_SYSTEM,
               F.AYUSH_HOSPITAL, F.BILL_LINES, F.ROOM_RATE, F.ICU_RATE, F.PRE_POST_BILLS)
"""Copied onto the claim form in the easy tier."""

RESTATABLE_RULES = (F.INITIAL_WAIT, F.SPECIFIED_DISEASES, F.PED_WAIT, F.EXCLUSIONS, F.AYUSH_TERMS, F.MIN_STAY,
                    F.DAY_CARE_LIST, F.ROOM_ASSOCIATED, F.ICU_CAP, F.SUBLIMITS, F.PRE_POST_WINDOWS)
"""Product rules the certificate restates in the easy and medium tiers; in the
hard tier the decisive ones stay in the wording only."""

NEEDS: dict[str, tuple[Fact, ...]] = {
    C.POLICY_PERIOD: (F.POLICY_PERIOD, F.ADMISSION),
    C.INITIAL_WAITING: (F.FIRST_INCEPTION, F.ADMISSION, F.CAUSE, F.INITIAL_WAIT),
    C.SPECIFIC_WAITING: (F.FIRST_INCEPTION, F.ADMISSION, F.CAUSE, F.DIAGNOSIS, F.PROCEDURES, F.SPECIFIED_DISEASES),
    C.PED_WAITING: (F.FIRST_INCEPTION, F.ADMISSION, F.DIAGNOSIS, F.DECLARED_PEDS, F.PED_WAIT),
    C.AYUSH: (F.TREATMENT_SYSTEM, F.AYUSH_HOSPITAL, F.AYUSH_TERMS),
    C.MIN_HOSPITALISATION: (F.ADMISSION, F.DISCHARGE, F.PROCEDURES, F.MIN_STAY, F.DAY_CARE_LIST),
    C.MISSING_DOCUMENTS: (F.REQUIRED_DOCUMENTS,),
    C.DOCUMENT_MISMATCH: (F.CLAIMED_AMOUNT, F.CLAIM_FORM_DATES, F.ADMISSION, F.DISCHARGE, F.BILL_LINES),
    C.PRE_HOSPITALISATION: (F.PRE_POST_BILLS, F.ADMISSION, F.PRE_POST_WINDOWS),
    C.POST_HOSPITALISATION: (F.PRE_POST_BILLS, F.DISCHARGE, F.PRE_POST_WINDOWS),
    C.NON_PAYABLE: (F.BILL_LINES, F.NON_PAYABLES),
    C.ROOM_RENT: (F.ROOM_RATE, F.BILL_LINES, F.ROOM_CAP, F.ROOM_ASSOCIATED, F.SUM_INSURED),
    C.ICU_LIMIT: (F.ICU_RATE, F.BILL_LINES, F.ICU_CAP),
    C.DISEASE_SUBLIMIT: (F.DIAGNOSIS, F.PROCEDURES, F.SUBLIMITS),
    C.DEDUCTIBLE: (F.DEDUCTIBLE,),
    C.COPAY: (F.COPAY,),
    C.SUM_INSURED: (F.SUM_INSURED, F.CUMULATIVE_BONUS),
}
"""The facts needed to reproduce each check, fired or not."""

DECISIVE: dict[str, tuple[Fact, ...]] = {
    C.MIN_HOSPITALISATION: (F.MIN_STAY, F.DAY_CARE_LIST),
    C.DAY_CARE: (F.MIN_STAY, F.DAY_CARE_LIST),
    C.INITIAL_WAITING: (F.INITIAL_WAIT,),
    C.INITIAL_WAITING_ACCIDENT: (F.INITIAL_WAIT,),
    C.SPECIFIC_WAITING: (F.SPECIFIED_DISEASES,),
    C.SPECIFIC_WAITING_ACCIDENT: (F.SPECIFIED_DISEASES,),
    C.PED_WAITING: (F.PED_WAIT,),
    C.AYUSH: (F.AYUSH_TERMS,),
    C.PRE_HOSPITALISATION: (F.PRE_POST_WINDOWS,),
    C.POST_HOSPITALISATION: (F.PRE_POST_WINDOWS,),
    C.ROOM_RENT: (F.ROOM_ASSOCIATED,),
    C.ICU_LIMIT: (F.ICU_CAP,),
    C.DISEASE_SUBLIMIT: (F.SUBLIMITS,),
    **{clause: (F.EXCLUSIONS,) for clause in C.STANDARD_EXCLUSIONS},
}
"""The restatable rules behind each clause that can fire: the hard tier keeps
these in the wording only."""

MISSING_DOC = {DocType.CLAIM_FORM: D.CLAIM_FORM, DocType.DISCHARGE_SUMMARY: D.DISCHARGE_SUMMARY,
               DocType.HOSPITAL_BILL: D.HOSPITAL_BILL}


class Placement(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    facts: dict[Fact, tuple[Doc, ...]]
    """Every fact the decision needs, and the documents that must state it. A fact
    whose only home is a missing document has no documents: that gap is the case."""
    wording_only: tuple[Fact, ...]
    """Facts no document but the wording may state (hard tier)."""
    diagnosis_style: DiagnosisStyle


class NotPlaceable(Exception):
    """The decision gives the tier nothing to work with (e.g. a hard case with no
    decisive rule to hide in the wording). The sampler tries another draw."""


def diagnosis_style(tier: Difficulty) -> DiagnosisStyle:
    return DiagnosisStyle.CLINICAL if tier is Difficulty.HARD else DiagnosisStyle.PLAIN


def needed_facts(decision: Decision, terms: ProductTerms) -> list[Fact]:
    """Facts needed to reproduce every check the engine made, in Fact order."""
    line_level = {rule.clause_id for rule in terms.line_exclusions}
    needed: set[Fact] = set()
    for check in decision.checks:
        if check in NEEDS:
            needed.update(NEEDS[check])
        elif check in line_level:
            needed.update((F.BILL_LINES, F.EXCLUDED_ITEMS))
        elif check in C.STANDARD_EXCLUSIONS:
            needed.update((F.DIAGNOSIS, F.PROCEDURES, F.EXCLUSIONS))
        else:
            raise KeyError(f"no fact mapping for check {check}")
    return [fact for fact in Fact if fact in needed]


def decisive_rules(decision: Decision, terms: ProductTerms) -> list[Fact]:
    """The rules behind every clause that fired anywhere in the trace (the
    non-payables list aside, since every case uses it)."""
    line_level = {rule.clause_id for rule in terms.line_exclusions if rule.clause_id != C.NON_PAYABLE}
    fired = {step.fired_clause for step in decision.reasoning_trace if step.effect is not Effect.PASS}
    rules: set[Fact] = set()
    for clause in fired:
        if clause in line_level:
            rules.add(F.EXCLUDED_ITEMS)
        elif clause == C.MISSING_DOCUMENTS:
            rules.add(F.REQUIRED_DOCUMENTS)
        elif clause in DECISIVE:
            rules.update(DECISIVE[clause])
    return [fact for fact in Fact if fact in rules]


def plan(decision: Decision, terms: ProductTerms, tier: Difficulty, submitted: tuple[DocType, ...]) -> Placement:
    needed = needed_facts(decision, terms)
    wording_only: list[Fact] = []
    if tier is Difficulty.HARD:
        wording_only = [fact for fact in decisive_rules(decision, terms) if fact in needed]
        if not wording_only:
            # Nothing fired but cost sharing (a near miss, a declared PED that is not
            # related): what decides the case is every rule the checks relied on.
            wording_only = [fact for fact in needed if fact in RESTATABLE_RULES]
        if not wording_only:
            raise NotPlaceable("a hard case needs a deciding rule to keep in the wording")

    missing = {MISSING_DOC[doc] for doc in MISSING_DOC if doc not in submitted}
    facts: dict[Fact, tuple[Doc, ...]] = {}
    for fact in needed:
        docs = list(HOME[fact])
        if tier is Difficulty.EASY and fact in CLAIM_FACTS:
            docs.append(D.CLAIM_FORM)
        if tier is not Difficulty.HARD and fact in RESTATABLE_RULES:
            docs.append(D.POLICY_CERTIFICATE)
        facts[fact] = tuple(doc for doc in Doc if doc in docs and doc not in missing)
    return Placement(facts=facts, wording_only=tuple(wording_only), diagnosis_style=diagnosis_style(tier))
