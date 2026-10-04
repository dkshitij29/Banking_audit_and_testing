"""Unit tests for the gate predicates, mostly at their boundaries."""

import datetime as dt

import pytest

from engine import clauses as C
from engine.rules import (
    Context,
    ayush_eligibility,
    initial_waiting,
    min_stay,
    ped_waiting,
    permanent_exclusions,
    policy_in_force,
    specific_waiting,
)
from engine.schema import (
    Ayush,
    Cause,
    ConditionGroup,
    Duration,
    DurationUnit,
    Effect,
    Exclusion,
    Hospital,
    Match,
    SpecificWait,
    TreatmentSystem,
    Wait,
)
from tests.builders import (
    PNEUMONIA,
    build_claim,
    build_policy,
    days,
    dx,
    months,
    ped,
    pharmacy,
    placeholder_terms,
    px,
)


def ctx(
    *,
    admitted,
    discharged=None,
    cause=Cause.ILLNESS,
    diagnosis=PNEUMONIA,
    procedures=(),
    secondary=(),
    terms=None,
    **policy_args,
):
    admitted_at = dt.datetime.fromisoformat(admitted)
    discharged_at = dt.datetime.fromisoformat(discharged) if discharged else admitted_at + dt.timedelta(days=3)
    policy = build_policy(terms or placeholder_terms(), **policy_args)
    claim = build_claim(
        admitted=admitted_at,
        discharged=discharged_at,
        cause=cause,
        diagnosis=diagnosis,
        procedures=procedures,
        secondary_diagnoses=secondary,
        items=[pharmacy(1_000)],
    )
    return Context.of(policy, claim)


def months_wait(n: int, *, accident_exempt: bool = True):
    return placeholder_terms(
        initial_wait=Wait(duration=Duration(value=n, unit=DurationUnit.MONTHS), accident_exempt=accident_exempt)
    )


# ---------------------------------------------------------------- policy in force


@pytest.mark.parametrize(
    "admitted, effect",
    [
        ("2025-03-31 23:59", Effect.REJECT),  # day before the period
        ("2025-04-01 00:00", Effect.PASS),  # first day
        ("2026-03-31 23:59", Effect.PASS),  # last day
        ("2026-04-01 00:00", Effect.REJECT),  # day after
    ],
)
def test_policy_period_includes_both_ends(admitted, effect):
    outcome = policy_in_force(ctx(admitted=admitted))
    assert outcome.effect is effect


def test_admission_inside_period_counts_even_if_discharge_is_after_it():
    outcome = policy_in_force(ctx(admitted="2026-03-30 10:00", discharged="2026-04-04 10:00"))
    assert outcome.effect is Effect.PASS


# ---------------------------------------------------------------- initial waiting period


@pytest.mark.parametrize(
    "admitted, effect",
    [
        ("2025-07-09 23:59", Effect.REJECT),  # day 100 of cover
        ("2025-07-10 00:00", Effect.PASS),  # day 101
    ],
)
def test_initial_wait_in_days(admitted, effect):
    outcome = initial_waiting(ctx(admitted=admitted, first_inception=dt.date(2025, 4, 1)))
    assert outcome.effect is effect


@pytest.mark.parametrize(
    "inception, months, last_day_inside",
    [
        (dt.date(2025, 1, 31), 1, dt.date(2025, 2, 27)),  # 31 Jan + 1 month = 28 Feb
        (dt.date(2024, 1, 31), 1, dt.date(2024, 2, 28)),  # leap year: 29 Feb
        (dt.date(2023, 3, 15), 24, dt.date(2025, 3, 14)),
        (dt.date(2024, 11, 30), 3, dt.date(2025, 2, 27)),  # crosses a year end, clamps to 28 Feb
    ],
)
def test_initial_wait_in_months(inception, months, last_day_inside):
    period = {"period_start": inception, "period_end": inception + dt.timedelta(days=1_000)}
    terms = months_wait(months)
    inside = ctx(admitted=f"{last_day_inside} 12:00", terms=terms, first_inception=inception, **period)
    over = ctx(
        admitted=f"{last_day_inside + dt.timedelta(days=1)} 12:00",
        terms=terms,
        first_inception=inception,
        **period,
    )
    assert initial_waiting(inside).effect is Effect.REJECT
    assert initial_waiting(over).effect is Effect.PASS


def test_accident_inside_wait_fires_the_exception():
    outcome = initial_waiting(ctx(admitted="2025-05-01 10:00", cause=Cause.ACCIDENT, first_inception=dt.date(2025, 4, 1)))
    assert (outcome.effect, outcome.fired_clause) == (Effect.EXCEPTION, C.INITIAL_WAITING_ACCIDENT)


def test_accident_is_rejected_when_the_product_does_not_exempt_accidents():
    terms = placeholder_terms(
        initial_wait=Wait(duration=Duration(value=100, unit=DurationUnit.DAYS), accident_exempt=False)
    )
    outcome = initial_waiting(
        ctx(admitted="2025-05-01 10:00", cause=Cause.ACCIDENT, terms=terms, first_inception=dt.date(2025, 4, 1))
    )
    assert (outcome.effect, outcome.fired_clause) == (Effect.REJECT, C.INITIAL_WAITING)


def test_zero_length_wait_never_fires():
    terms = placeholder_terms(initial_wait=Wait(duration=Duration(value=0, unit=DurationUnit.DAYS), accident_exempt=False))
    outcome = initial_waiting(ctx(admitted="2025-04-01 00:00", terms=terms, first_inception=dt.date(2025, 4, 1)))
    assert outcome.effect is Effect.PASS


# ---------------------------------------------------------------- minimum stay and day-care


def stay(length: dt.timedelta, procedures=()):
    admitted = dt.datetime(2025, 8, 4, 8, 0)
    return ctx(
        admitted=admitted.isoformat(sep=" "),
        discharged=(admitted + length).isoformat(sep=" "),
        procedures=procedures,
    )


HOURS_24 = dt.timedelta(hours=24)
PHACO = px("PX-PHACO", "Phacoemulsification")


def test_exactly_the_minimum_stay_qualifies():
    assert min_stay(stay(HOURS_24)).effect is Effect.PASS


def test_one_minute_short_is_rejected():
    outcome = min_stay(stay(HOURS_24 - dt.timedelta(minutes=1)))
    assert (outcome.effect, outcome.fired_clause) == (Effect.REJECT, C.MIN_HOSPITALISATION)


def test_short_stay_with_a_day_care_procedure_fires_the_exception():
    outcome = min_stay(stay(dt.timedelta(hours=6), procedures=[PHACO]))
    assert (outcome.effect, outcome.fired_clause) == (Effect.EXCEPTION, C.DAY_CARE)
    assert outcome.facts["day_care_procedures"] == ("PX-PHACO",)


def test_short_stay_with_a_procedure_not_on_the_list_is_rejected():
    outcome = min_stay(stay(dt.timedelta(hours=6), procedures=[px("PX-CLOSED-REDUCTION", "Closed reduction")]))
    assert outcome.effect is Effect.REJECT


def test_day_care_exception_is_not_needed_for_a_long_stay():
    outcome = min_stay(stay(dt.timedelta(hours=30), procedures=[PHACO]))
    assert (outcome.effect, outcome.fired_clause) == (Effect.PASS, None)


# ---------------------------------------------------------------- specified disease waiting period

CATARACT = dx("H25.1", "Senile nuclear cataract")
NEW = {"first_inception": dt.date(2025, 4, 1)}


def specific_terms(*groups, accident_exempt=True):
    return placeholder_terms(specific_wait=SpecificWait(groups=groups, accident_exempt=accident_exempt))


def group(name, duration, *, prefixes=(), procedures=()):
    return ConditionGroup(name=name, match=Match(icd10_prefixes=prefixes, procedure_codes=procedures), duration=duration)


@pytest.mark.parametrize(
    "admitted, effect",
    [
        ("2025-08-12 10:00", Effect.REJECT),  # placeholder wait: 500 days from 1 Apr 2025 -> over on 14 Aug 2026
        ("2026-08-13 10:00", Effect.REJECT),  # last day inside
        ("2026-08-14 10:00", Effect.PASS),  # over
    ],
)
def test_listed_condition_waits_its_own_period(admitted, effect):
    period = {"period_start": dt.date(2025, 4, 1), "period_end": dt.date(2027, 3, 31)}
    outcome = specific_waiting(ctx(admitted=admitted, diagnosis=CATARACT, **NEW, **period))
    assert outcome.effect is effect


def test_a_listed_procedure_matches_even_with_an_unlisted_diagnosis():
    outcome = specific_waiting(
        ctx(admitted="2025-08-12 10:00", diagnosis=dx("M17.1", "Primary osteoarthritis of knee"),
            procedures=[px("PX-TKR", "Total knee replacement")], **NEW)
    )
    assert outcome.effect is Effect.REJECT
    assert outcome.facts["matched_by"] == ("procedure PX-TKR",)


def test_an_unlisted_claim_is_checked_but_passes():
    outcome = specific_waiting(ctx(admitted="2025-08-12 10:00", **NEW))
    assert (outcome.effect, outcome.facts["groups_matched"]) == (Effect.PASS, ())


def test_the_longest_matching_group_decides():
    terms = specific_terms(
        group("Eyes", months(6), prefixes=("H25",)),
        group("Eye surgery", months(24), procedures=("PX-PHACO",)),
    )
    context = ctx(admitted="2026-01-15 10:00", diagnosis=CATARACT, procedures=[PHACO], terms=terms, **NEW)
    outcome = specific_waiting(context)
    assert outcome.facts["wait_over_on"] == "2027-04-01"
    assert outcome.effect is Effect.REJECT


def test_an_accident_inside_the_specified_wait_fires_its_exception():
    outcome = specific_waiting(
        ctx(admitted="2025-08-12 10:00", cause=Cause.ACCIDENT, procedures=[px("PX-THR", "Hip replacement")], **NEW)
    )
    assert (outcome.effect, outcome.fired_clause) == (Effect.EXCEPTION, C.SPECIFIC_WAITING_ACCIDENT)


def test_no_accident_exception_when_the_product_has_none():
    terms = specific_terms(group("Joints", days(500), procedures=("PX-THR",)), accident_exempt=False)
    outcome = specific_waiting(
        ctx(admitted="2025-08-12 10:00", cause=Cause.ACCIDENT, procedures=[px("PX-THR", "Hip")], terms=terms, **NEW)
    )
    assert (outcome.effect, outcome.fired_clause) == (Effect.REJECT, C.SPECIFIC_WAITING)


def test_no_listed_conditions_means_no_check():
    assert specific_waiting(ctx(admitted="2025-08-12 10:00", terms=specific_terms(), **NEW)) is None


# ---------------------------------------------------------------- pre-existing disease waiting period

DIABETES = ped("Type 2 diabetes mellitus", "E11")
DIABETIC_FOOT = dx("E11.5", "Type 2 diabetes mellitus with peripheral circulatory complications")


def test_no_declared_ped_means_no_check():
    assert ped_waiting(ctx(admitted="2025-08-12 10:00", diagnosis=DIABETIC_FOOT)) is None


def test_admission_for_a_declared_ped_inside_the_wait_is_rejected():
    # placeholder PED wait: 1,000 days from 1 Apr 2023 -> over on 26 Dec 2025
    context = ctx(admitted="2025-12-25 10:00", diagnosis=DIABETIC_FOOT, first_inception=dt.date(2023, 4, 1),
                  declared_peds=[DIABETES])
    outcome = ped_waiting(context)
    assert (outcome.effect, outcome.fired_clause) == (Effect.REJECT, C.PED_WAITING)
    assert outcome.facts["wait_over_on"] == "2025-12-26"


def test_admission_for_a_declared_ped_after_the_wait_passes():
    context = ctx(admitted="2025-12-26 10:00", diagnosis=DIABETIC_FOOT, first_inception=dt.date(2023, 4, 1),
                  declared_peds=[DIABETES])
    assert ped_waiting(context).effect is Effect.PASS


def test_ped_wait_keys_off_the_declaration_not_the_claim():
    # The claim is for diabetes, but the member declared only hypertension.
    context = ctx(admitted="2025-08-12 10:00", diagnosis=DIABETIC_FOOT, declared_peds=[ped("Hypertension", "I10")])
    outcome = ped_waiting(context)
    assert (outcome.effect, outcome.facts["related_to"]) == (Effect.PASS, ())


def test_a_ped_recorded_only_as_a_secondary_diagnosis_does_not_count():
    context = ctx(admitted="2025-08-12 10:00", secondary=[dx("E11.9", "Type 2 diabetes")], declared_peds=[DIABETES],
                  first_inception=dt.date(2025, 4, 1))
    assert ped_waiting(context).effect is Effect.PASS


def test_ped_wait_has_no_accident_exception():
    context = ctx(admitted="2025-08-12 10:00", cause=Cause.ACCIDENT, diagnosis=DIABETIC_FOOT,
                  declared_peds=[DIABETES], first_inception=dt.date(2025, 4, 1))
    assert ped_waiting(context).effect is Effect.REJECT


# ---------------------------------------------------------------- permanent exclusions


def test_each_configured_exclusion_is_checked():
    outcomes = permanent_exclusions(ctx(admitted="2025-08-12 10:00"))
    assert [o.check for o in outcomes] == [e.clause_id for e in placeholder_terms().exclusions]
    assert all(o.effect is Effect.PASS for o in outcomes)


def test_a_matching_exclusion_fires_with_its_own_clause():
    outcomes = permanent_exclusions(
        ctx(admitted="2025-08-12 10:00", diagnosis=dx("H52.1", "Myopia"), procedures=[px("PX-LASIK", "LASIK")])
    )
    fired = [(o.fired_clause, o.facts["matched_by"]) for o in outcomes if o.effect is Effect.REJECT]
    assert fired == [(C.REFRACTIVE_ERROR, ("diagnosis H52.1", "procedure PX-LASIK"))]


def test_every_matching_exclusion_fires():
    terms = placeholder_terms(
        exclusions=(
            Exclusion(clause_id=C.COSMETIC, match=Match(procedure_codes=("PX-LIPOSUCTION",))),
            Exclusion(clause_id=C.OBESITY, match=Match(icd10_prefixes=("E66",))),
        )
    )
    context = ctx(admitted="2025-08-12 10:00", diagnosis=dx("E66.0", "Obesity"),
                  procedures=[px("PX-LIPOSUCTION", "Liposuction")], terms=terms)
    assert [o.fired_clause for o in permanent_exclusions(context)] == [C.COSMETIC, C.OBESITY]


# ---------------------------------------------------------------- AYUSH eligibility


def ayush_ctx(*, covered=True, requires=True, ayush_hospital=True, system=TreatmentSystem.AYURVEDA):
    terms = placeholder_terms(ayush=Ayush(covered=covered, requires_ayush_hospital=requires, cap=None))
    claim = build_claim(
        admitted="2025-08-12 10:00",
        discharged="2025-08-19 10:00",
        diagnosis=dx("M06.9", "Rheumatoid arthritis"),
        treatment_system=system,
        hospital=Hospital(name="Test Hospital", city="Kochi", ayush_hospital=ayush_hospital),
        items=[pharmacy(1_000)],
    )
    return Context.of(build_policy(terms), claim)


def test_allopathic_treatment_has_no_ayush_check():
    assert ayush_eligibility(ayush_ctx(system=TreatmentSystem.ALLOPATHY)) is None


def test_ayush_treatment_in_an_ayush_hospital_is_covered():
    assert ayush_eligibility(ayush_ctx()).effect is Effect.PASS


def test_ayush_treatment_elsewhere_is_rejected_when_the_product_requires_an_ayush_hospital():
    outcome = ayush_eligibility(ayush_ctx(ayush_hospital=False))
    assert (outcome.effect, outcome.fired_clause) == (Effect.REJECT, C.AYUSH)


def test_ayush_treatment_elsewhere_is_covered_when_the_product_does_not_require_one():
    assert ayush_eligibility(ayush_ctx(requires=False, ayush_hospital=False)).effect is Effect.PASS


def test_ayush_treatment_is_rejected_when_the_product_does_not_cover_it():
    outcome = ayush_eligibility(ayush_ctx(covered=False, system=TreatmentSystem.HOMEOPATHY))
    assert (outcome.effect, outcome.fired_clause) == (Effect.REJECT, C.AYUSH)
