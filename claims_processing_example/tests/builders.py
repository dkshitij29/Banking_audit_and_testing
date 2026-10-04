"""Builders for test policies and claims.

placeholder_terms() assembles the UNVERIFIED placeholder product from
engine/tables.py for unit and property tests. The golden cases do not use it:
they define their own test product (tests/golden_cases.py), so replacing the
placeholders at step 3 cannot change their answers.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from engine import clauses as C
from engine import tables
from engine.schema import (
    ALL_DOCUMENTS,
    Ayush,
    BillCategory,
    BillLine,
    Cap,
    Cause,
    Claim,
    ClaimForm,
    ConditionGroup,
    DeclaredPed,
    Diagnosis,
    DocType,
    Doctor,
    Duration,
    DurationUnit,
    Exclusion,
    Gender,
    Hospital,
    LineExclusion,
    Member,
    Phase,
    Policy,
    Procedure,
    ProductTerms,
    Relation,
    SpecificWait,
    Sublimit,
    TreatmentSystem,
    Wait,
)


def days(n: int) -> Duration:
    return Duration(value=n, unit=DurationUnit.DAYS)


def months(n: int) -> Duration:
    return Duration(value=n, unit=DurationUnit.MONTHS)


def placeholder_terms(**overrides: Any) -> ProductTerms:
    """The placeholder product. UNVERIFIED: no value here comes from a real wording.

    Waiting periods and windows are deliberately unrealistic (100 / 500 / 1000
    days; 50 / 100 days) so they cannot be mistaken for real ones; caps are
    arbitrary round numbers.
    """
    values: dict[str, Any] = {
        "product_id": "PLACEHOLDER",
        "source": tables.PLACEHOLDER_SOURCE,
        "initial_wait": Wait(duration=days(100), accident_exempt=True),  # UNVERIFIED PLACEHOLDER
        "specific_wait": SpecificWait(
            groups=tuple(
                ConditionGroup(name=name, match=match, duration=days(500))  # UNVERIFIED PLACEHOLDER
                for name, match in tables.PLACEHOLDER_SPECIFIC_CONDITIONS.items()
            ),
            accident_exempt=True,  # UNVERIFIED PLACEHOLDER
        ),
        "ped_wait": days(1_000),  # UNVERIFIED PLACEHOLDER
        "exclusions": tuple(
            Exclusion(clause_id=clause_id, match=match)
            for clause_id, match in tables.PLACEHOLDER_EXCLUSIONS.items()
        ),
        # UNVERIFIED PLACEHOLDER
        "ayush": Ayush(covered=True, requires_ayush_hospital=True, cap=Cap(rupees=20_000)),
        "min_stay_hours": 24,  # UNVERIFIED PLACEHOLDER
        "day_care_procedures": tables.PLACEHOLDER_DAY_CARE_PROCEDURES,
        "required_documents": ALL_DOCUMENTS,
        "pre_hospitalisation_days": 50,  # UNVERIFIED PLACEHOLDER
        "post_hospitalisation_days": 100,  # UNVERIFIED PLACEHOLDER
        "line_exclusions": (
            LineExclusion(clause_id=C.NON_PAYABLE, item_codes=tables.PLACEHOLDER_NON_PAYABLE_ITEMS),
            LineExclusion(
                clause_id=C.DIETARY_SUPPLEMENTS, item_codes=tables.PLACEHOLDER_DIETARY_SUPPLEMENTS
            ),
        ),
        "room_cap": Cap(rupees=5_000),  # UNVERIFIED PLACEHOLDER
        "room_rate_includes": (),
        "room_associated": tables.PLACEHOLDER_ROOM_ASSOCIATED,
        "icu_cap": Cap(rupees=10_000),  # UNVERIFIED PLACEHOLDER
        "icu_associated": tables.PLACEHOLDER_ICU_ASSOCIATED,
        "sublimits": tuple(
            Sublimit(name=name, match=match, cap_per_unit=Cap(rupees=25_000))  # UNVERIFIED PLACEHOLDER
            for name, match in tables.PLACEHOLDER_SUBLIMIT_CONDITIONS.items()
        ),
    }
    values.update(overrides)
    return ProductTerms(**values)


def replace[M](model: M, **changes: Any) -> M:
    """A validated copy of a frozen model with some fields changed."""
    return type(model).model_validate({**dict(model), **changes})  # type: ignore[attr-defined]


# ---------------------------------------------------------------- bill items


@dataclass(frozen=True)
class Item:
    """A bill line before build_claim numbers it. Inpatient lines are dated on the
    admission day; pre/post-hospitalisation lines carry their own date."""

    category: BillCategory
    item_code: str
    description: str
    unit_price: int
    qty: int = 1
    phase: Phase = Phase.INPATIENT
    on: dt.date | None = None


def pre(item: Item, on: str) -> Item:
    """The item as a pre-hospitalisation bill dated `on`."""
    return dataclasses.replace(item, phase=Phase.PRE, on=dt.date.fromisoformat(on))


def post(item: Item, on: str) -> Item:
    """The item as a post-hospitalisation bill dated `on`."""
    return dataclasses.replace(item, phase=Phase.POST, on=dt.date.fromisoformat(on))


def room(rate: int, days: int) -> Item:
    return Item(BillCategory.ROOM, "RM-ROOM", "Room rent", rate, days)


def icu(rate: int, days: int) -> Item:
    return Item(BillCategory.ICU, "RM-ICU", "ICU charges", rate, days)


def nursing(rate: int, days: int) -> Item:
    return Item(BillCategory.NURSING, "NS-NURSING", "Nursing charges", rate, days)


def surgeon(amount: int) -> Item:
    return Item(BillCategory.SURGEON, "PF-SURGEON", "Surgeon's fee", amount)


def anaesthetist(amount: int) -> Item:
    return Item(BillCategory.ANAESTHETIST, "PF-ANAESTHETIST", "Anaesthetist's fee", amount)


def consultant(amount: int, description: str = "Consultant visits") -> Item:
    return Item(BillCategory.CONSULTANT, "PF-CONSULTANT", description, amount)


def ot(amount: int) -> Item:
    return Item(BillCategory.OT, "OT-CHARGES", "Operation theatre charges", amount)


def pharmacy(amount: int, description: str = "Pharmacy") -> Item:
    return Item(BillCategory.PHARMACY, "PH-DRUGS", description, amount)


def investigations(amount: int, description: str = "Investigations") -> Item:
    return Item(BillCategory.INVESTIGATION, "IN-LAB", description, amount)


def therapy(amount: int, description: str) -> Item:
    return Item(BillCategory.OTHER, "TH-THERAPY", description, amount)


def implant(price: int, description: str = "Implant", qty: int = 1) -> Item:
    return Item(BillCategory.IMPLANT, "IM-IMPLANT", description, price, qty)


def gloves(amount: int) -> Item:
    return Item(BillCategory.CONSUMABLE, "NP-GLOVES", "Surgical gloves", amount)


def admission_kit(amount: int) -> Item:
    return Item(BillCategory.CONSUMABLE, "NP-ADMISSION-KIT", "Admission kit", amount)


def registration(amount: int) -> Item:
    return Item(BillCategory.ADMIN, "NP-REGISTRATION", "Registration charges", amount)


def protein_supplement(amount: int) -> Item:
    return Item(BillCategory.PHARMACY, "EX-PROTEIN-SUPPLEMENT", "Protein supplement powder", amount)


# ---------------------------------------------------------------- policy and claim


def dx(icd10: str, term: str) -> Diagnosis:
    return Diagnosis(icd10=icd10, term=term)


def px(code: str, term: str, units: int = 1) -> Procedure:
    return Procedure(code=code, term=term, units=units)


def ped(name: str, *icd10_prefixes: str) -> DeclaredPed:
    return DeclaredPed(name=name, icd10_prefixes=icd10_prefixes)


def build_policy(
    terms: ProductTerms,
    *,
    sum_insured: int = 500_000,
    cumulative_bonus: int = 0,
    deductible: int = 0,
    copay_bp: int = 0,
    period_start: dt.date = dt.date(2025, 4, 1),
    period_end: dt.date = dt.date(2026, 3, 31),
    first_inception: dt.date = dt.date(2022, 4, 1),
    declared_peds: Sequence[DeclaredPed] = (),
) -> Policy:
    member = Member(
        member_id="M1",
        name="Test Member",
        dob=dt.date(1965, 6, 15),
        gender=Gender.FEMALE,
        relation=Relation.SELF,
        first_inception=first_inception,
        declared_peds=tuple(declared_peds),
    )
    return Policy(
        policy_number="POL-TEST-0001",
        period_start=period_start,
        period_end=period_end,
        sum_insured=sum_insured,
        cumulative_bonus=cumulative_bonus,
        deductible=deductible,
        copay_bp=copay_bp,
        members=(member,),
        terms=terms,
    )


def _at(value: str | dt.datetime) -> dt.datetime:
    return dt.datetime.fromisoformat(value) if isinstance(value, str) else value


def build_claim(
    *,
    admitted: str | dt.datetime,
    discharged: str | dt.datetime,
    items: Sequence[Item],
    diagnosis: Diagnosis,
    procedures: Sequence[Procedure] = (),
    secondary_diagnoses: Sequence[Diagnosis] = (),
    cause: Cause = Cause.ILLNESS,
    treatment_system: TreatmentSystem = TreatmentSystem.ALLOPATHY,
    hospital: Hospital | None = None,
    room_category: str | None = "Twin sharing",
    documents: Sequence[DocType] = ALL_DOCUMENTS,
    claimed_amount: int | None = None,
    form_admitted: str | dt.datetime | None = None,
    form_discharged: str | dt.datetime | None = None,
) -> Claim:
    """A claim whose bill lines are numbered L01, L02, ...

    Unless told otherwise, every document is submitted and the claim form agrees
    with the hospital: it claims the bill total, with the hospital's dates.
    """
    admitted_at, discharged_at = _at(admitted), _at(discharged)
    bill = tuple(
        BillLine(
            line_id=f"L{n:02d}",
            date=item.on or admitted_at.date(),
            category=item.category,
            item_code=item.item_code,
            description=item.description,
            unit_price=item.unit_price,
            qty=item.qty,
            amount=item.unit_price * item.qty,
            phase=item.phase,
        )
        for n, item in enumerate(items, start=1)
    )
    claim_form = None
    if DocType.CLAIM_FORM in documents:
        claim_form = ClaimForm(
            claimed_amount=sum(line.amount for line in bill) if claimed_amount is None else claimed_amount,
            admitted_at=admitted_at if form_admitted is None else _at(form_admitted),
            discharged_at=discharged_at if form_discharged is None else _at(form_discharged),
        )
    return Claim(
        claim_id="CLM-TEST-0001",
        member_id="M1",
        cause=cause,
        treatment_system=treatment_system,
        primary_dx=diagnosis,
        secondary_dx=tuple(secondary_diagnoses),
        procedures=tuple(procedures),
        admitted_at=admitted_at,
        discharged_at=discharged_at,
        room_category=room_category,
        hospital=hospital or Hospital(name="Test Hospital", city="Pune"),
        doctor=Doctor(name="Dr Test", registration_no="MMC-000000"),
        bill=bill,
        documents_submitted=tuple(documents),
        claim_form=claim_form,
    )


APPENDICITIS = dx("K35.8", "Acute appendicitis")
APPENDICECTOMY = px("PX-LAP-APPENDICECTOMY", "Laparoscopic appendicectomy")
PNEUMONIA = dx("J18.9", "Pneumonia, unspecified organism")
GASTROENTERITIS = dx("A09.0", "Acute gastroenteritis of infectious origin")
