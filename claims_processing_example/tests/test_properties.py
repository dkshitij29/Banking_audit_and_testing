"""Properties that must hold for every claim, checked on random policies and claims."""

import datetime as dt

from hypothesis import given, settings
from hypothesis import strategies as st

from engine import adjudicate, tables
from engine import clauses as C
from engine.schema import (
    ALL_DOCUMENTS,
    BP_SCALE,
    Ayush,
    BillCategory,
    BillLine,
    Cap,
    Cause,
    ConditionGroup,
    DocType,
    Duration,
    DurationUnit,
    Hospital,
    Phase,
    SpecificWait,
    Sublimit,
    TreatmentSystem,
    Verdict,
    Wait,
)
from tests.builders import Item, build_claim, build_policy, dx, ped, placeholder_terms, px, replace

PROPERTY = settings(max_examples=300, deadline=None)

DIAGNOSES = (
    dx("K35.8", "Acute appendicitis"),
    dx("J18.9", "Pneumonia"),
    dx("H25.1", "Senile nuclear cataract"),
    dx("K40.9", "Inguinal hernia"),
    dx("E11.5", "Diabetic foot"),
    dx("S02.2", "Fracture of nasal bones"),
    dx("H52.1", "Myopia"),
    dx("N20.0", "Calculus of kidney"),
    dx("M06.9", "Rheumatoid arthritis"),
)
PROCEDURES = (
    "PX-PHACO", "PX-HERNIA-REPAIR", "PX-THR", "PX-TKR", "PX-COSMETIC-RHINOPLASTY",
    "PX-LASIK", "PX-LITHOTRIPSY", "PX-LAP-APPENDICECTOMY", "PX-CABG",
)
PEDS = (ped("Type 2 diabetes mellitus", "E11"), ped("Inguinal hernia", "K40"), ped("Hypertension", "I10", "I11"))
PAYABLE_CODES = ("PF-SURGEON", "PH-DRUGS", "IN-LAB", "OT-CHARGES", "NS-NURSING", "IM-IMPLANT")
ITEM_CODES = PAYABLE_CODES + tables.PLACEHOLDER_NON_PAYABLE_ITEMS + tables.PLACEHOLDER_DIETARY_SUPPLEMENTS
OTHER_CATEGORIES = [c for c in BillCategory if c not in (BillCategory.ROOM, BillCategory.ICU)]


def durations(max_days=1_200, max_months=40):
    return st.one_of(
        st.builds(Duration, value=st.integers(0, max_days), unit=st.just(DurationUnit.DAYS)),
        st.builds(Duration, value=st.integers(0, max_months), unit=st.just(DurationUnit.MONTHS)),
    )


def caps(max_rupees=20_000, max_bp=500):
    rupees, share = st.integers(500, max_rupees), st.integers(25, max_bp)
    return st.one_of(
        st.builds(Cap, rupees=rupees),
        st.builds(Cap, bp_of_si=share),
        st.builds(Cap, rupees=rupees, bp_of_si=share),
    )


@st.composite
def terms(draw):
    groups = tuple(
        ConditionGroup(name=group.name, match=group.match, duration=draw(durations()))
        for group in placeholder_terms().specific_wait.groups
    )
    # Each other charge is counted in the room rate, scaled with room rent, scaled with
    # ICU charges, or none of these; never two.
    scaled_with = draw(st.lists(
        st.sampled_from(["includes", "room", "icu", None]),
        min_size=len(OTHER_CATEGORIES), max_size=len(OTHER_CATEGORIES),
    ))
    room_rate_includes = [c for c, with_ in zip(OTHER_CATEGORIES, scaled_with) if with_ == "includes"]
    room_associated = [c for c, with_ in zip(OTHER_CATEGORIES, scaled_with) if with_ == "room"]
    icu_associated = [c for c, with_ in zip(OTHER_CATEGORIES, scaled_with) if with_ == "icu"]
    sublimits = tuple(
        Sublimit(name=s.name, match=s.match, cap_per_unit=draw(caps(100_000, 5_000)))
        for s in placeholder_terms().sublimits
    )
    return placeholder_terms(
        initial_wait=Wait(duration=draw(durations(400, 24)), accident_exempt=draw(st.booleans())),
        specific_wait=SpecificWait(groups=groups, accident_exempt=draw(st.booleans())),
        ped_wait=draw(durations()),
        ayush=Ayush(
            covered=draw(st.booleans()),
            requires_ayush_hospital=draw(st.booleans()),
            cap=draw(st.one_of(st.none(), caps(100_000, 5_000))),
        ),
        min_stay_hours=draw(st.integers(1, 48)),
        day_care_procedures=tuple(draw(st.lists(st.sampled_from(PROCEDURES), unique=True))),
        pre_hospitalisation_days=draw(st.integers(0, 120)),
        post_hospitalisation_days=draw(st.integers(0, 180)),
        room_cap=draw(st.one_of(st.none(), caps())),
        room_rate_includes=tuple(room_rate_includes),
        room_associated=tuple(room_associated),
        icu_cap=draw(st.one_of(st.none(), caps())),
        icu_associated=tuple(icu_associated),
        sublimits=sublimits,
    )


@st.composite
def policies(draw):
    si = draw(st.sampled_from([100_000, 300_000, 500_000, 1_000_000]))
    return build_policy(
        draw(terms()),
        sum_insured=si,
        cumulative_bonus=draw(st.integers(0, si)),
        deductible=draw(st.integers(0, 50_000)),
        copay_bp=draw(st.integers(0, 5_000)),
        first_inception=draw(st.dates(dt.date(2019, 1, 1), dt.date(2025, 4, 1))),
        declared_peds=draw(st.lists(st.sampled_from(PEDS), unique=True)),
    )


@st.composite
def items(draw, admitted: dt.date, discharged: dt.date):
    phase = draw(st.sampled_from(Phase))
    on = {
        Phase.PRE: admitted - dt.timedelta(days=draw(st.integers(0, 150))),
        Phase.INPATIENT: admitted,
        Phase.POST: discharged + dt.timedelta(days=draw(st.integers(0, 200))),
    }[phase]
    return Item(
        draw(st.sampled_from(OTHER_CATEGORIES)),
        draw(st.sampled_from(ITEM_CODES)),
        "item",
        draw(st.integers(0, 60_000)),
        draw(st.integers(1, 5)),
        phase=phase,
        on=on,
    )


@st.composite
def claims(draw, consistent: bool = False):
    """Random claims. consistent=True: every document submitted, and the claim form agrees."""
    admitted = draw(st.datetimes(dt.datetime(2025, 3, 1), dt.datetime(2026, 4, 30))).replace(second=0, microsecond=0)
    discharged = admitted + dt.timedelta(minutes=draw(st.integers(1, 20 * 24 * 60)))
    bill = draw(st.lists(items(admitted.date(), discharged.date()), min_size=1, max_size=8))
    for category, code in ((BillCategory.ROOM, "RM-ROOM"), (BillCategory.ICU, "RM-ICU")):
        if draw(st.booleans()):
            bill.append(Item(category, code, "stay", draw(st.integers(0, 20_000)), draw(st.integers(1, 10))))
    procedures = [
        px(code, code, units=draw(st.integers(1, 2)))
        for code in draw(st.lists(st.sampled_from(PROCEDURES), unique=True, max_size=2))
    ]
    documents, form = ALL_DOCUMENTS, {}
    if not consistent:
        documents = tuple(draw(st.lists(st.sampled_from(DocType), unique=True, min_size=1)))
        if draw(st.booleans()):
            form["claimed_amount"] = draw(st.integers(0, 300_000))
        if draw(st.booleans()):
            shift = dt.timedelta(hours=draw(st.integers(-240, 240)))
            form["form_admitted"] = admitted + shift
            form["form_discharged"] = discharged + shift
    return build_claim(
        admitted=admitted,
        discharged=discharged,
        cause=draw(st.sampled_from(Cause)),
        treatment_system=draw(st.sampled_from(TreatmentSystem)),
        hospital=Hospital(name="Test Hospital", city="Pune", ayush_hospital=draw(st.booleans())),
        diagnosis=draw(st.sampled_from(DIAGNOSES)),
        procedures=procedures,
        items=bill,
        documents=documents,
        **form,
    )


@PROPERTY
@given(policies(), claims())
def test_payable_is_between_zero_and_sum_insured_plus_bonus(policy, claim):
    payable = adjudicate(policy, claim).payable
    assert 0 <= payable <= policy.sum_insured + policy.cumulative_bonus


@PROPERTY
@given(policies(), claims())
def test_nothing_is_paid_exactly_when_the_claim_is_rejected_or_escalated(policy, claim):
    decision = adjudicate(policy, claim)
    assert (decision.verdict in (Verdict.REJECT, Verdict.ESCALATE)) == (decision.payable == 0)


@PROPERTY
@given(policies(), claims())
def test_an_escalation_cites_only_escalation_clauses(policy, claim):
    decision = adjudicate(policy, claim)
    if decision.verdict is Verdict.ESCALATE:
        assert decision.clauses and set(decision.clauses) <= {C.MISSING_DOCUMENTS, C.DOCUMENT_MISMATCH}


@PROPERTY
@given(policies(), claims(consistent=True))
def test_complete_consistent_documents_never_escalate(policy, claim):
    assert adjudicate(policy, claim).verdict is not Verdict.ESCALATE


@PROPERTY
@given(policies(), claims(), st.sampled_from(tables.PLACEHOLDER_NON_PAYABLE_ITEMS), st.integers(0, 60_000))
def test_adding_a_non_payable_line_changes_nothing(policy, claim, code, price):
    extra = BillLine(
        line_id="LX",
        date=claim.admitted_at.date(),
        category=BillCategory.CONSUMABLE,
        item_code=code,
        description="extra",
        unit_price=price,
        qty=1,
        amount=price,
    )
    changes = {"bill": claim.bill + (extra,)}
    if claim.claim_form is not None:  # the claimant claims the extra line too
        changes["claim_form"] = replace(claim.claim_form, claimed_amount=claim.claim_form.claimed_amount + price)
    before = adjudicate(policy, claim)
    after = adjudicate(policy, replace(claim, **changes))
    assert (after.verdict, after.payable) == (before.verdict, before.payable)


@PROPERTY
@given(policies(), claims(consistent=True), st.integers(1, 1_000_000))
def test_more_sum_insured_never_pays_less(policy, claim, extra):
    richer = replace(policy, sum_insured=policy.sum_insured + extra)
    assert adjudicate(richer, claim).payable >= adjudicate(policy, claim).payable


@PROPERTY
@given(policies(), claims(consistent=True), st.integers(0, BP_SCALE))
def test_more_copay_never_pays_more(policy, claim, copay_bp):
    low, high = sorted((policy.copay_bp, copay_bp))
    assert (
        adjudicate(replace(policy, copay_bp=low), claim).payable
        >= adjudicate(replace(policy, copay_bp=high), claim).payable
    )


@PROPERTY
@given(policies(), claims(consistent=True), st.integers(0, 200_000))
def test_more_deductible_never_pays_more(policy, claim, other):
    low, high = sorted((policy.deductible, other))
    assert (
        adjudicate(replace(policy, deductible=low), claim).payable
        >= adjudicate(replace(policy, deductible=high), claim).payable
    )


@PROPERTY
@given(policies(), claims())
def test_same_inputs_give_byte_identical_output(policy, claim):
    assert adjudicate(policy, claim).model_dump_json() == adjudicate(policy, claim).model_dump_json()


@PROPERTY
@given(policies(), claims())
def test_answer_key_and_checks_agree_with_the_trace(policy, claim):
    decision = adjudicate(policy, claim)
    trace = decision.reasoning_trace
    assert set(decision.clauses) <= {step.fired_clause for step in trace}
    assert list(decision.clauses) == sorted(set(decision.clauses))
    assert list(decision.checks) == sorted({step.check for step in trace})
    assert [step.seq for step in trace] == list(range(1, len(trace) + 1))
