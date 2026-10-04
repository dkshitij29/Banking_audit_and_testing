"""Engine inputs and outputs: Policy (with its ProductTerms), Claim, Decision.

Conventions that hold everywhere:

- Money is whole rupees (int). Percentages are basis points (int; 10,000 = 100%).
  There are no floats: the engine computes with fractions.Fraction.
- Datetimes are naive and mean IST.
- Set-like fields are stored as sorted, de-duplicated tuples, so JSON output is
  byte-stable whatever PYTHONHASHSEED is.
- Models are frozen and strict: a wrong type is an error, never silently coerced.

Every product number and list lives on ProductTerms, which is embedded in Policy.
A case file is therefore self-contained, and rule logic holds no product numbers.
"""

from __future__ import annotations

import calendar
import datetime as dt
import itertools
import math
from enum import StrEnum
from fractions import Fraction
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    NaiveDatetime,
    StringConstraints,
    field_validator,
    model_validator,
)

from engine import clauses as C

BP_SCALE = 10_000
"""Basis points in 100%."""


class UnsupportedCase(Exception):
    """A well-formed case that falls outside what the engine models.

    The engine raises this rather than guess. The sampler discards such cases.
    """


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


def _sorted_unique[T](values: tuple[T, ...]) -> tuple[T, ...]:
    return tuple(sorted(set(values)))


def _registered(clause_id: str) -> str:
    if clause_id not in C.REGISTRY:
        raise ValueError(f"unknown clause ID {clause_id!r}")
    return clause_id


Text = Annotated[str, StringConstraints(min_length=1)]
Code = Annotated[str, StringConstraints(pattern=r"^\S+$")]
ClauseId = Annotated[str, AfterValidator(_registered)]
Rupees = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
BasisPoints = Annotated[int, Field(ge=0, le=BP_SCALE)]
Icd10 = Annotated[str, StringConstraints(pattern=r"^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$")]
Icd10Prefix = Annotated[str, StringConstraints(pattern=r"^[A-Z][0-9]{1,2}(\.[0-9A-Z]{1,4})?$")]
CodeSet = Annotated[tuple[Code, ...], AfterValidator(_sorted_unique)]
Icd10PrefixSet = Annotated[tuple[Icd10Prefix, ...], AfterValidator(_sorted_unique)]


# ---------------------------------------------------------------- enums


class Verdict(StrEnum):
    APPROVE = "APPROVE"
    PARTIAL = "PARTIAL"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class Cause(StrEnum):
    ILLNESS = "ILLNESS"
    ACCIDENT = "ACCIDENT"


class Gender(StrEnum):
    FEMALE = "FEMALE"
    MALE = "MALE"
    OTHER = "OTHER"


class Relation(StrEnum):
    SELF = "SELF"
    SPOUSE = "SPOUSE"
    CHILD = "CHILD"
    PARENT = "PARENT"
    PARENT_IN_LAW = "PARENT_IN_LAW"


class BillCategory(StrEnum):
    ROOM = "ROOM"
    ICU = "ICU"
    NURSING = "NURSING"
    SURGEON = "SURGEON"
    ANAESTHETIST = "ANAESTHETIST"
    CONSULTANT = "CONSULTANT"
    OT = "OT"
    INVESTIGATION = "INVESTIGATION"
    PHARMACY = "PHARMACY"
    CONSUMABLE = "CONSUMABLE"
    IMPLANT = "IMPLANT"
    ADMIN = "ADMIN"
    OTHER = "OTHER"


class DurationUnit(StrEnum):
    DAYS = "DAYS"
    MONTHS = "MONTHS"


class Phase(StrEnum):
    """When a bill line was incurred, relative to the hospital stay."""

    PRE = "PRE"  # before admission (pre-hospitalisation)
    INPATIENT = "INPATIENT"
    POST = "POST"  # after discharge (post-hospitalisation)


class TreatmentSystem(StrEnum):
    ALLOPATHY = "ALLOPATHY"
    AYURVEDA = "AYURVEDA"
    YOGA_NATUROPATHY = "YOGA_NATUROPATHY"
    UNANI = "UNANI"
    SIDDHA = "SIDDHA"
    HOMEOPATHY = "HOMEOPATHY"


class DocType(StrEnum):
    """Claim documents the claimant submits. The policy certificate and wording
    are the insurer's own and always present."""

    CLAIM_FORM = "CLAIM_FORM"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    HOSPITAL_BILL = "HOSPITAL_BILL"


class Effect(StrEnum):
    PASS = "PASS"  # checked; nothing happened
    REJECT = "REJECT"  # a gate rejected the claim
    EXCEPTION = "EXCEPTION"  # an exception stopped a gate from rejecting
    REDUCE = "REDUCE"  # an amount step reduced the payable
    ESCALATE = "ESCALATE"  # the claim goes to a human


CategorySet = Annotated[tuple[BillCategory, ...], AfterValidator(_sorted_unique)]
DocSet = Annotated[tuple[DocType, ...], AfterValidator(_sorted_unique)]
ALL_DOCUMENTS: tuple[DocType, ...] = tuple(sorted(DocType))


# ---------------------------------------------------------------- product terms


class Duration(_Model):
    value: Annotated[int, Field(ge=0)]
    unit: DurationUnit

    def add_to(self, start: dt.date) -> dt.date:
        """The date `start` + this duration: the first day after a period of this
        length that began on `start`.

        Months are calendar months. A start on the 29th-31st lands on the last day
        of a shorter month: 31 Jan + 1 month = 28 Feb (29 Feb in a leap year).
        """
        if self.unit is DurationUnit.DAYS:
            return start + dt.timedelta(days=self.value)
        months = start.month - 1 + self.value
        year, month = start.year + months // 12, months % 12 + 1
        return dt.date(year, month, min(start.day, calendar.monthrange(year, month)[1]))

    def describe(self) -> str:
        """'100 days', '1 month'."""
        unit = self.unit.value.lower()
        return f"{self.value} {unit[:-1] if self.value == 1 else unit}"

    def adjective(self) -> str:
        """'100-day', '24-month', as in 'the 100-day initial wait'."""
        return f"{self.value}-{self.unit.value.lower()[:-1]}"


class Wait(_Model):
    duration: Duration
    accident_exempt: bool
    """Whether a claim caused by an accident is outside this waiting period."""


class Cap(_Model):
    """A money limit: a fixed amount, a share of the base sum insured, or the
    lower of the two ("2% of sum insured or ₹5,000, whichever is lower").

    The share is of the base sum insured; cumulative bonus never raises a cap.
    """

    rupees: PositiveInt | None = None
    bp_of_si: Annotated[int, Field(gt=0, le=BP_SCALE)] | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Cap:
        if self.rupees is None and self.bp_of_si is None:
            raise ValueError("a cap needs a rupee amount, a share of sum insured, or both")
        return self


class Ayush(_Model):
    """AYUSH treatment (Ayurveda, Yoga and Naturopathy, Unani, Siddha, Homeopathy)."""

    covered: bool
    requires_ayush_hospital: bool
    """Whether treatment must be in a hospital that qualifies as an AYUSH hospital."""
    cap: Cap | None
    """A limit on the whole AYUSH claim, or None for up to the sum insured."""


class LineExclusion(_Model):
    """Bill items this product never pays, removed line by line.

    The list of non-payable items (A1) is one entry. An exclusion that removes
    single lines, such as dietary supplements under 4.14, is another. Removing A1
    items leaves a claim APPROVE; removing items under an exclusion makes it PARTIAL.
    """

    clause_id: ClauseId
    item_codes: CodeSet

    @field_validator("clause_id")
    @classmethod
    def _cites_a_line_level_clause(cls, clause_id: str) -> str:
        if clause_id != C.NON_PAYABLE and clause_id not in C.STANDARD_EXCLUSIONS:
            raise ValueError(
                f"a line exclusion must cite {C.NON_PAYABLE} or a standard exclusion (4.4-4.18), "
                f"not {clause_id!r}"
            )
        return clause_id

    @field_validator("item_codes")
    @classmethod
    def _not_empty(cls, item_codes: tuple[str, ...]) -> tuple[str, ...]:
        if not item_codes:
            raise ValueError("item_codes must not be empty")
        return item_codes


class Match(_Model):
    """Which claims a rule applies to, by code, never by text.

    A claim matches if its primary diagnosis's ICD-10 code starts with one of
    icd10_prefixes (H25 matches H25.1; K4 matches K40-K49), or if any of its
    procedures has a code in procedure_codes. Secondary diagnoses never match.
    """

    icd10_prefixes: Icd10PrefixSet = ()
    procedure_codes: CodeSet = ()

    @model_validator(mode="after")
    def _not_empty(self) -> Match:
        if not self.icd10_prefixes and not self.procedure_codes:
            raise ValueError("a match needs at least one ICD-10 prefix or procedure code")
        return self


class ConditionGroup(_Model):
    """Listed conditions and procedures that share one specified-disease wait."""

    name: Text
    match: Match
    duration: Duration


class SpecificWait(_Model):
    """The specified disease/procedure waiting period (4.2)."""

    groups: tuple[ConditionGroup, ...]
    """A claim matching several groups waits for the longest of them."""
    accident_exempt: bool


class Exclusion(_Model):
    """Treatment this product never covers: a matching claim is rejected."""

    clause_id: ClauseId
    match: Match

    @field_validator("clause_id")
    @classmethod
    def _cites_a_standard_exclusion(cls, clause_id: str) -> str:
        if clause_id not in C.STANDARD_EXCLUSIONS:
            raise ValueError(f"an exclusion must cite a standard exclusion (4.4-4.18), not {clause_id!r}")
        return clause_id


class Sublimit(_Model):
    """A cap on the whole claim for a condition or procedure (3.3).

    The cap is cap_per_unit times the units of the claim's matching procedures
    (eyes, joints), or times 1 when only the diagnosis matches.
    """

    name: Text
    match: Match
    cap_per_unit: Cap


class ProductTerms(_Model):
    """Everything a policy wording decides. Every rule reads its numbers from here."""

    product_id: Code
    source: Text
    """Where these terms come from: a wording reference, or UNVERIFIED_PLACEHOLDER."""
    initial_wait: Wait
    specific_wait: SpecificWait
    ped_wait: Duration
    """Pre-existing disease waiting period. It has no accident exemption."""
    exclusions: tuple[Exclusion, ...]
    ayush: Ayush
    min_stay_hours: PositiveInt
    day_care_procedures: CodeSet
    required_documents: DocSet
    pre_hospitalisation_days: Annotated[int, Field(ge=0)]
    """Bills from up to this many days before the admission date are covered."""
    post_hospitalisation_days: Annotated[int, Field(ge=0)]
    """Bills from up to this many days after the discharge date are covered."""
    line_exclusions: tuple[LineExclusion, ...]
    """Applied in this order; a bill line is removed by the first entry that lists it."""
    room_cap: Cap | None
    """Per day."""
    room_rate_includes: CategorySet
    """Charges billed on lines of their own that count as part of the daily room
    rate, for a wording that caps "room rent, boarding and nursing" together. They
    are compared with the cap along with the room line, and scaled with it."""
    room_associated: CategorySet
    """Charges scaled down with room rent when the room is above the cap. The room
    line and the room_rate_includes charges are always scaled, so they are not
    listed here."""
    icu_cap: Cap | None
    """Per day."""
    icu_associated: CategorySet
    """Charges scaled down with ICU charges when the ICU is above its cap. The ICU
    line itself is always scaled, so ICU is not listed here."""
    sublimits: tuple[Sublimit, ...]

    @field_validator("room_rate_includes", "room_associated", "icu_associated")
    @classmethod
    def _other_charges_only(cls, categories: tuple[BillCategory, ...]) -> tuple[BillCategory, ...]:
        for category in (BillCategory.ROOM, BillCategory.ICU):
            if category in categories:
                raise ValueError(f"{category} has its own limit; list only the other charges that go with it")
        return categories

    @model_validator(mode="after")
    def _consistent(self) -> ProductTerms:
        groups = {
            "counted in the room rate": set(self.room_rate_includes),
            "scaled with room rent": set(self.room_associated),
            "scaled with ICU charges": set(self.icu_associated),
        }
        for (label_a, a), (label_b, b) in itertools.combinations(groups.items(), 2):
            if a & b:
                raise ValueError(f"{sorted(a & b)} cannot be both {label_a} and {label_b}")

        listed_under: dict[str, str] = {}
        line_clauses = [rule.clause_id for rule in self.line_exclusions]
        if len(set(line_clauses)) != len(line_clauses):
            raise ValueError("each clause may appear only once in line_exclusions")
        for rule in self.line_exclusions:
            for code in rule.item_codes:
                if code in listed_under:
                    raise ValueError(
                        f"item {code!r} is listed under both {listed_under[code]} and {rule.clause_id}"
                    )
                listed_under[code] = rule.clause_id

        claim_clauses = [exclusion.clause_id for exclusion in self.exclusions]
        if len(set(claim_clauses)) != len(claim_clauses):
            raise ValueError("each clause may appear only once in exclusions")
        if set(claim_clauses) & set(line_clauses):
            raise ValueError("a clause cannot exclude both whole claims and single bill lines")

        for label, names in (
            ("condition group", [group.name for group in self.specific_wait.groups]),
            ("sub-limit", [sublimit.name for sublimit in self.sublimits]),
        ):
            if len(set(names)) != len(names):
                raise ValueError(f"{label} names must be unique")
        return self


# ---------------------------------------------------------------- policy


class DeclaredPed(_Model):
    """A pre-existing disease the member declared, as accepted onto the policy."""

    name: Text
    icd10_prefixes: Icd10PrefixSet
    """The condition and its direct complications, e.g. E11 for type 2 diabetes."""

    @field_validator("icd10_prefixes")
    @classmethod
    def _not_empty(cls, prefixes: tuple[str, ...]) -> tuple[str, ...]:
        if not prefixes:
            raise ValueError("a declared PED needs at least one ICD-10 prefix")
        return prefixes


class Member(_Model):
    member_id: Code
    name: Text
    dob: dt.date
    gender: Gender
    relation: Relation
    first_inception: dt.date
    """Start of this member's first continuous cover. Waiting periods count from here."""
    declared_peds: tuple[DeclaredPed, ...] = ()
    """The PED waiting period keys off these, never off the claim's diagnoses."""


class Policy(_Model):
    policy_number: Code
    period_start: dt.date
    period_end: dt.date
    """Both ends are inside the period."""
    sum_insured: PositiveInt
    cumulative_bonus: Rupees
    deductible: Rupees
    """Per claim: the policyholder bears the first this-many rupees."""
    copay_bp: BasisPoints
    members: tuple[Member, ...]
    terms: ProductTerms

    @model_validator(mode="after")
    def _consistent(self) -> Policy:
        if self.period_end < self.period_start:
            raise ValueError("policy period ends before it starts")
        if not self.members:
            raise ValueError("a policy needs at least one member")
        member_ids = [member.member_id for member in self.members]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("member IDs must be unique")
        for member in self.members:
            if member.first_inception > self.period_start:
                raise ValueError(
                    f"member {member.member_id}: first inception is after the current period starts"
                )
            if member.dob > member.first_inception:
                raise ValueError(f"member {member.member_id}: born after first inception")
        return self


# ---------------------------------------------------------------- claim


class Diagnosis(_Model):
    icd10: Icd10
    term: Text
    """Clinical wording, for rendering only. No rule reads it."""


class Procedure(_Model):
    code: Code
    term: Text
    """Clinical wording, for rendering only. No rule reads it."""
    units: PositiveInt = 1
    """How many were done in this admission: eyes, joints. Sub-limits multiply by it."""


class Hospital(_Model):
    name: Text
    city: Text
    ayush_hospital: bool = False
    """Whether it qualifies as an AYUSH hospital under the policy's definition."""


class Doctor(_Model):
    name: Text
    registration_no: Code


class BillLine(_Model):
    line_id: Code
    date: dt.date
    category: BillCategory
    item_code: Code
    description: Text
    unit_price: Rupees
    qty: PositiveInt
    amount: Rupees
    phase: Phase = Phase.INPATIENT

    @model_validator(mode="after")
    def _consistent(self) -> BillLine:
        if self.amount != self.unit_price * self.qty:
            raise ValueError(
                f"line {self.line_id}: amount {self.amount} != {self.unit_price} x {self.qty}"
            )
        if self.category in (BillCategory.ROOM, BillCategory.ICU) and self.phase is not Phase.INPATIENT:
            raise ValueError(f"line {self.line_id}: {self.category} charges are always inpatient")
        return self


class ClaimForm(_Model):
    """What the claimant declared on the claim form. It can contradict the hospital's
    records; stage 2 of the engine decides whether a contradiction matters."""

    claimed_amount: Rupees
    admitted_at: NaiveDatetime
    discharged_at: NaiveDatetime

    @model_validator(mode="after")
    def _consistent(self) -> ClaimForm:
        if self.discharged_at <= self.admitted_at:
            raise ValueError("claim form: discharge must be after admission")
        return self


class Claim(_Model):
    claim_id: Code
    member_id: Code
    cause: Cause
    cause_note: Text | None = None
    """How an accident happened, in the hospital's words ("a fall at home"). For
    rendering only; no rule reads it. None for an illness."""
    treatment_system: TreatmentSystem = TreatmentSystem.ALLOPATHY
    primary_dx: Diagnosis
    """The reason for admission. Rules key on its ICD-10 code, never on its text."""
    secondary_dx: tuple[Diagnosis, ...] = ()
    """Context for rendering. No rule reads these."""
    procedures: tuple[Procedure, ...] = ()
    admitted_at: NaiveDatetime
    discharged_at: NaiveDatetime
    """Admission and discharge as the hospital recorded them (discharge summary)."""
    room_category: Text | None = None
    uhid: Code | None = None
    """The hospital's own number for this patient, as its paperwork carries it.
    For rendering only; no rule reads it."""
    bill_no: Code | None = None
    """The hospital's number for this bill. For rendering only."""
    hospital: Hospital
    doctor: Doctor
    bill: tuple[BillLine, ...]
    """The daily room rate is the unit_price of the one ROOM line; its qty is the days."""
    documents_submitted: DocSet = ALL_DOCUMENTS
    claim_form: ClaimForm | None
    """The claim form's contents; None exactly when no claim form was submitted."""

    @model_validator(mode="after")
    def _consistent(self) -> Claim:
        if self.discharged_at <= self.admitted_at:
            raise ValueError("discharge must be after admission")
        if not self.bill:
            raise ValueError("a claim needs at least one bill line")
        line_ids = [line.line_id for line in self.bill]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("bill line IDs must be unique")
        admitted, discharged = self.admitted_at.date(), self.discharged_at.date()
        for line in self.bill:
            if line.phase is Phase.INPATIENT and not admitted <= line.date <= discharged:
                raise ValueError(f"line {line.line_id} is dated {line.date}, outside the stay")
            if line.phase is Phase.PRE and line.date > admitted:
                raise ValueError(f"pre-hospitalisation line {line.line_id} is dated after admission")
            if line.phase is Phase.POST and line.date < discharged:
                raise ValueError(f"post-hospitalisation line {line.line_id} is dated before discharge")
        if (self.claim_form is None) == (DocType.CLAIM_FORM in self.documents_submitted):
            raise ValueError("claim_form must be given exactly when a claim form was submitted")
        if self.cause_note is not None and self.cause is not Cause.ACCIDENT:
            raise ValueError("only an accident has a cause note")
        return self


# ---------------------------------------------------------------- decision

FactValue = str | int | bool | tuple[str, ...] | None


class TraceStep(_Model):
    """What one rule saw and did."""

    seq: PositiveInt
    check: ClauseId
    """The rule that was checked, by its main clause ID."""
    fired_clause: ClauseId | None
    """The clause that fired: the checked clause itself, or an exception to it.
    None when the check passed."""
    effect: Effect
    facts: dict[str, FactValue]
    note: Text
    before: Rupees | None = None
    after: Rupees | None = None


class Decision(_Model):
    verdict: Verdict
    payable: Rupees
    """0 for REJECT and ESCALATE."""
    clauses: tuple[ClauseId, ...]
    """The answer key: sorted clause IDs that explain the outcome."""
    checks: tuple[ClauseId, ...]
    """Sorted clause IDs of every rule that was checked (for the mandatory-checks metric)."""
    reasoning_trace: tuple[TraceStep, ...]


# ---------------------------------------------------------------- display helpers for trace notes


def format_rupees(amount: int | Fraction) -> str:
    """Rupees with Indian digit grouping: ₹1,05,000. Fractions show paise."""
    exact = Fraction(amount)
    if exact.denominator == 1:
        whole, paise = int(exact), ""
    else:
        cents = math.floor(exact * 100 + Fraction(1, 2))
        whole, paise = cents // 100, f".{cents % 100:02d}"
    digits = str(whole)
    head, groups = digits[:-3], [digits[-3:]]
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join(groups) + paise


def format_percent(bp: int) -> str:
    whole, rest = divmod(bp, 100)
    return f"{whole}%" if rest == 0 else f"{whole}.{rest:02d}".rstrip("0") + "%"


def format_stay(stay: dt.timedelta) -> str:
    hours, minutes = divmod(stay // dt.timedelta(minutes=1), 60)
    return f"{hours} h" if minutes == 0 else f"{hours} h {minutes} min"
