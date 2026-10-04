"""Unit tests for the amount steps and the verdict rules."""

import pytest

from engine import adjudicate
from engine import clauses as C
from engine.rules import (
    Context,
    Running,
    ayush_cap,
    copay,
    deductible,
    disease_sublimit,
    icu,
    line_exclusions,
    pre_post_window,
    room_rent,
    sum_insured,
)
from engine.schema import (
    Ayush,
    BillCategory,
    Cap,
    Effect,
    Hospital,
    Match,
    Sublimit,
    TreatmentSystem,
    UnsupportedCase,
    Verdict,
)
from tests.builders import (
    APPENDICECTOMY,
    APPENDICITIS,
    Item,
    build_claim,
    build_policy,
    consultant,
    dx,
    gloves,
    nursing,
    pharmacy,
    placeholder_terms,
    post,
    pre,
    protein_supplement,
    px,
    registration,
    replace,
    room,
    surgeon,
    therapy,
)
from tests.builders import icu as icu_line


def case(items, *, terms=None, diagnosis=APPENDICITIS, procedures=(APPENDICECTOMY,), **policy_args):
    policy = build_policy(terms or placeholder_terms(), **policy_args)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=diagnosis,
        procedures=procedures,
        items=items,
    )
    return policy, claim


def run_step(step, items, **kwargs):
    """Run one amount step on a fresh bill, as if it were the first step."""
    policy, claim = case(items, **kwargs)
    start = Running(claim.bill, sum(line.amount for line in claim.bill))
    return step(Context.of(policy, claim), start)


# ---------------------------------------------------------------- line exclusions


def test_each_line_is_removed_by_the_rule_that_lists_it():
    running, outcomes = run_step(line_exclusions, [surgeon(10_000), gloves(300), protein_supplement(700)])
    assert running.total == 10_000
    assert [(o.check, o.fired_clause, o.before, o.after) for o in outcomes] == [
        (C.NON_PAYABLE, C.NON_PAYABLE, 11_000, 10_700),
        (C.DIETARY_SUPPLEMENTS, C.DIETARY_SUPPLEMENTS, 10_700, 10_000),
    ]


def test_a_rule_with_nothing_to_remove_is_checked_but_does_not_fire():
    _, outcomes = run_step(line_exclusions, [surgeon(10_000)])
    assert [(o.effect, o.fired_clause) for o in outcomes] == [(Effect.PASS, None), (Effect.PASS, None)]


def test_a_free_excluded_line_is_removed_without_firing():
    running, outcomes = run_step(line_exclusions, [surgeon(10_000), gloves(0)])
    assert [line.item_code for line in running.lines] == ["PF-SURGEON"]
    assert outcomes[0].effect is Effect.PASS
    assert outcomes[0].facts["lines_removed"] == ("L02",)


# ---------------------------------------------------------------- room rent


def test_no_room_line_means_no_room_check():
    running, outcomes = run_step(room_rent, [surgeon(10_000)])
    assert outcomes == []


def test_no_room_cap_means_no_room_check():
    _, outcomes = run_step(room_rent, [room(9_000, 2)], terms=placeholder_terms(room_cap=None))
    assert outcomes == []


def test_room_at_the_cap_is_not_reduced():
    running, outcomes = run_step(room_rent, [room(5_000, 2), surgeon(10_000)])
    assert running.total == 20_000
    assert outcomes[0].effect is Effect.PASS


def test_room_above_the_cap_scales_room_and_associated_lines_only():
    # ratio 5,000 / 10,000 = 1/2. Scaled: room 20,000 + nursing 2,000 + surgeon 10,000 = 32,000.
    # Pharmacy 4,000 is not associated.
    running, outcomes = run_step(
        room_rent, [room(10_000, 2), nursing(1_000, 2), surgeon(10_000), pharmacy(4_000)]
    )
    assert running.total == 36_000 - 16_000
    assert outcomes[0].facts["ratio"] == "1/2"
    assert outcomes[0].facts["lines_scaled"] == ("L01", "L02", "L03")


def test_associated_set_comes_from_the_product():
    terms = placeholder_terms(room_associated=(BillCategory.PHARMACY,))
    running, _ = run_step(room_rent, [room(10_000, 2), surgeon(10_000), pharmacy(4_000)], terms=terms)
    # scaled: room 20,000 + pharmacy 4,000 = 24,000, halved -> 12,000 off; surgeon untouched
    assert running.total == 34_000 - 12_000


def test_percent_of_sum_insured_cap_uses_the_base_sum_insured():
    # 1% of 4,00,000 = 4,000/day; the bonus must not raise it.
    terms = placeholder_terms(room_cap=Cap(bp_of_si=100))
    _, outcomes = run_step(
        room_rent, [room(5_000, 1)], terms=terms, sum_insured=400_000, cumulative_bonus=200_000
    )
    assert outcomes[0].facts["cap_per_day"] == 4_000
    assert outcomes[0].after == 4_000


def test_fractional_cap_is_kept_exact():
    # 1% of 3,33,333 = 3,333.33/day
    terms = placeholder_terms(room_cap=Cap(bp_of_si=100))
    _, outcomes = run_step(room_rent, [room(4_000, 3)], terms=terms, sum_insured=333_333)
    assert outcomes[0].facts["cap_per_day"] == "333333/100"
    # 12,000 x (1 - 333333/400000) = 2,000.01 -> 2,000
    assert outcomes[0].facts["deduction"] == 2_000


NURSING_IN_ROOM_RATE = {"room_rate_includes": (BillCategory.NURSING,), "room_associated": (BillCategory.SURGEON,)}


def test_charges_counted_in_the_room_rate_can_take_a_room_under_the_cap_over_it():
    # Room 4,600/day alone is under the 5,000 cap; with nursing 800/day the rate is 5,400.
    # Ratio 5,000 / 5,400 = 25/27. Scaled: room 13,800 + nursing 2,400 + surgeon 10,000 = 26,200.
    # 26,200 x 2/27 = 1,940.74 -> 1,941 off. Pharmacy 4,000 is untouched.
    terms = placeholder_terms(**NURSING_IN_ROOM_RATE)
    running, outcomes = run_step(
        room_rent, [room(4_600, 3), nursing(800, 3), surgeon(10_000), pharmacy(4_000)], terms=terms
    )
    facts = outcomes[0].facts
    assert (facts["rate"], facts["rate_includes"], facts["ratio"]) == (5_400, ("L02",), "25/27")
    assert facts["lines_scaled"] == ("L01", "L02", "L03")
    assert running.total == 30_200 - 1_941


def test_counted_charges_billed_as_one_sum_are_spread_over_the_room_days():
    # (16,000 room + 4,000 nursing) / 4 days = 5,000/day: at the cap, nothing off.
    terms = placeholder_terms(**NURSING_IN_ROOM_RATE)
    running, outcomes = run_step(room_rent, [room(4_000, 4), nursing(4_000, 1)], terms=terms)
    assert (outcomes[0].effect, outcomes[0].facts["rate"], running.total) == (Effect.PASS, 5_000, 20_000)


def test_pre_and_post_bills_are_never_counted_in_the_room_rate():
    terms = placeholder_terms(**NURSING_IN_ROOM_RATE)
    _, outcomes = run_step(room_rent, [room(5_000, 2), post(nursing(900, 3), on="2025-08-20")], terms=terms)
    assert (outcomes[0].effect, outcomes[0].facts["rate_includes"]) == (Effect.PASS, ())


def test_without_counted_charges_the_rate_is_the_room_line_alone():
    _, outcomes = run_step(room_rent, [room(4_600, 3), nursing(800, 3)])
    assert outcomes[0].facts["rate"] == 4_600
    assert "rate_includes" not in outcomes[0].facts


def test_two_room_rates_are_not_modelled():
    with pytest.raises(UnsupportedCase):
        run_step(room_rent, [room(4_000, 2), Item(BillCategory.ROOM, "RM-ROOM-2", "Room rent", 6_000, 1)])


# ---------------------------------------------------------------- ICU


def test_icu_above_its_cap_scales_only_the_icu_line_by_default():
    # placeholder ICU cap 10,000/day; 15,000/day -> paid at 2/3. Room 3,000/day is within its cap.
    running, outcomes = run_step(icu, [icu_line(15_000, 2), room(3_000, 2), consultant(6_000)])
    assert running.total == 42_000 - 10_000
    assert outcomes[0].facts["lines_scaled"] == ("L01",)


def test_icu_associated_charges_come_from_the_product():
    terms = placeholder_terms(room_associated=(BillCategory.SURGEON,), icu_associated=(BillCategory.CONSULTANT,))
    running, _ = run_step(icu, [icu_line(15_000, 2), consultant(6_000)], terms=terms)
    # scaled: 30,000 + 6,000 = 36,000, a third off -> 12,000
    assert running.total == 36_000 - 12_000


def test_no_icu_line_means_no_icu_check():
    assert run_step(icu, [room(9_000, 2)])[1] == []


def test_room_and_icu_cannot_share_an_associated_charge():
    with pytest.raises(ValueError, match="both scaled with room rent and scaled with ICU"):
        placeholder_terms(icu_associated=(BillCategory.SURGEON,))


@pytest.mark.parametrize("other", ["room_associated", "icu_associated"])
def test_a_charge_counted_in_the_room_rate_goes_on_no_other_list(other):
    with pytest.raises(ValueError, match="counted in the room rate"):
        placeholder_terms(
            room_rate_includes=(BillCategory.NURSING,),
            room_associated=(BillCategory.NURSING,) if other == "room_associated" else (),
            icu_associated=(BillCategory.NURSING,) if other == "icu_associated" else (),
        )


def test_two_icu_rates_are_not_modelled():
    with pytest.raises(UnsupportedCase):
        run_step(icu, [icu_line(9_000, 1), Item(BillCategory.ICU, "RM-ICU-2", "ICU charges", 12_000, 1)])


# ---------------------------------------------------------------- disease-wise sub-limit

CATARACT = dx("H25.1", "Senile nuclear cataract")


def test_sublimit_caps_per_unit_of_the_matching_procedure():
    # placeholder cataract sub-limit: 25,000 per eye
    running, outcomes = run_step(
        disease_sublimit, [surgeon(70_000)], diagnosis=CATARACT, procedures=(px("PX-PHACO", "Phaco", units=2),)
    )
    assert running.total == 50_000
    assert (outcomes[0].facts["units"], outcomes[0].fired_clause) == (2, C.DISEASE_SUBLIMIT)


def test_a_diagnosis_only_match_counts_as_one_unit():
    running, _ = run_step(disease_sublimit, [surgeon(70_000)], diagnosis=CATARACT, procedures=())
    assert running.total == 25_000


def test_amount_within_the_sublimit_is_checked_and_untouched():
    running, outcomes = run_step(disease_sublimit, [surgeon(20_000)], diagnosis=CATARACT, procedures=())
    assert (running.total, outcomes[0].effect) == (20_000, Effect.PASS)


def test_a_claim_no_sublimit_covers_is_checked_but_passes():
    running, outcomes = run_step(disease_sublimit, [surgeon(70_000)])
    assert (running.total, outcomes[0].effect) == (70_000, Effect.PASS)


def test_two_matching_sublimits_are_not_modelled():
    terms = placeholder_terms(
        sublimits=(
            Sublimit(name="Eyes", match=Match(icd10_prefixes=("H25",)), cap_per_unit=Cap(rupees=10_000)),
            Sublimit(name="Phaco", match=Match(procedure_codes=("PX-PHACO",)), cap_per_unit=Cap(rupees=20_000)),
        )
    )
    with pytest.raises(UnsupportedCase):
        run_step(disease_sublimit, [surgeon(70_000)], terms=terms, diagnosis=CATARACT,
                 procedures=(px("PX-PHACO", "Phaco"),))


# ---------------------------------------------------------------- deductible


def test_zero_deductible_means_no_deductible_check():
    assert run_step(deductible, [surgeon(10_000)], deductible=0)[1] == []


def test_deductible_is_subtracted():
    running, outcomes = run_step(deductible, [surgeon(30_000)], deductible=10_000)
    assert (running.total, outcomes[0].fired_clause) == (20_000, C.DEDUCTIBLE)


def test_deductible_never_goes_below_zero():
    running, outcomes = run_step(deductible, [surgeon(4_000)], deductible=10_000)
    assert (running.total, outcomes[0].facts["deduction"]) == (0, 4_000)


def test_deductible_alone_keeps_approve():
    policy, claim = case([surgeon(30_000)], deductible=10_000)
    decision = adjudicate(policy, claim)
    assert (decision.verdict, decision.payable, decision.clauses) == (Verdict.APPROVE, 20_000, (C.DEDUCTIBLE,))


# ---------------------------------------------------------------- co-pay and sum insured


def test_zero_copay_means_no_copay_check():
    _, outcomes = run_step(copay, [surgeon(10_000)], copay_bp=0)
    assert outcomes == []


@pytest.mark.parametrize(
    "total, copay_bp, deduction",
    [
        (12_345, 1_000, 1_235),  # 1,234.50 rounds up
        (12_344, 1_000, 1_234),  # 1,234.40 rounds down
        (10_005, 1_050, 1_051),  # 10.5% of 10,005 = 1,050.525
        (3, 1_000, 0),  # 0.30 rounds to nothing: checked, does not fire
    ],
)
def test_copay_rounds_the_deduction_half_up(total, copay_bp, deduction):
    running, outcomes = run_step(copay, [surgeon(total)], copay_bp=copay_bp)
    assert running.total == total - deduction
    assert outcomes[0].fired_clause == (C.COPAY if deduction else None)


def test_sum_insured_limit_includes_cumulative_bonus():
    running, outcomes = run_step(sum_insured, [surgeon(450_000)], sum_insured=400_000, cumulative_bonus=40_000)
    assert running.total == 440_000
    assert outcomes[0].fired_clause == C.SUM_INSURED


def test_amount_within_sum_insured_is_untouched():
    running, outcomes = run_step(sum_insured, [surgeon(440_000)], sum_insured=400_000, cumulative_bonus=40_000)
    assert running.total == 440_000
    assert outcomes[0].effect is Effect.PASS


# ---------------------------------------------------------------- verdicts


def test_nothing_left_after_non_payables_is_a_reject():
    policy, claim = case([gloves(300), registration(200)])
    decision = adjudicate(policy, claim)
    assert (decision.verdict, decision.payable, decision.clauses) == (Verdict.REJECT, 0, (C.NON_PAYABLE,))


def test_cost_sharing_alone_keeps_approve():
    policy, claim = case([surgeon(10_000), gloves(500)], copay_bp=1_000)
    assert adjudicate(policy, claim).verdict is Verdict.APPROVE


@pytest.mark.parametrize(
    "items, policy_args, clause",
    [
        ([room(9_000, 1), surgeon(1_000)], {}, C.ROOM_RENT),
        ([surgeon(10_000), protein_supplement(500)], {}, C.DIETARY_SUPPLEMENTS),
        ([surgeon(10_000)], {"sum_insured": 5_000}, C.SUM_INSURED),
    ],
)
def test_a_limit_or_exclusion_makes_partial(items, policy_args, clause):
    policy, claim = case(items, **policy_args)
    decision = adjudicate(policy, claim)
    assert decision.verdict is Verdict.PARTIAL
    assert clause in decision.clauses


def test_room_cap_can_be_turned_off_per_product():
    terms = replace(placeholder_terms(), room_cap=None)
    policy, claim = case([room(50_000, 3)], terms=terms)
    assert adjudicate(policy, claim).payable == 150_000


def test_fixed_cap_is_independent_of_sum_insured():
    terms = placeholder_terms(room_cap=Cap(rupees=2_000))
    for si in (100_000, 900_000):
        policy, claim = case([room(3_000, 1)], terms=terms, sum_insured=si)
        assert adjudicate(policy, claim).payable == 2_000


# ---------------------------------------------------------------- caps


@pytest.mark.parametrize(
    "cap, sum_insured, per_day",
    [
        (Cap(rupees=5_000), 1_000_000, 5_000),
        (Cap(bp_of_si=200), 100_000, 2_000),  # 2% of 1,00,000
        (Cap(rupees=5_000, bp_of_si=200), 100_000, 2_000),  # lower of 5,000 and 2,000
        (Cap(rupees=5_000, bp_of_si=200), 1_000_000, 5_000),  # lower of 5,000 and 20,000
    ],
)
def test_a_cap_is_its_amount_its_share_or_the_lower_of_both(cap, sum_insured, per_day):
    _, outcomes = run_step(room_rent, [room(50_000, 1)], terms=placeholder_terms(room_cap=cap), sum_insured=sum_insured)
    assert outcomes[0].facts["cap_per_day"] == per_day


def test_a_cap_needs_an_amount_or_a_share():
    with pytest.raises(ValueError, match="rupee amount, a share"):
        Cap()


def test_sublimit_per_unit_can_be_the_lower_of_amount_and_share():
    # 25% of 1,00,000 = 25,000, lower than 40,000
    terms = placeholder_terms(
        sublimits=(Sublimit(name="Cataract", match=Match(icd10_prefixes=("H25",)), cap_per_unit=Cap(rupees=40_000, bp_of_si=2_500)),)
    )
    running, _ = run_step(disease_sublimit, [surgeon(70_000)], terms=terms, diagnosis=CATARACT, procedures=(), sum_insured=100_000)
    assert running.total == 25_000


# ---------------------------------------------------------------- pre- and post-hospitalisation windows
# Admitted 4 Aug 2025, discharged 7 Aug. Placeholder windows: 50 days before (from 15 Jun),
# 100 days after (to 15 Nov).


@pytest.mark.parametrize("on, kept", [("2025-06-15", True), ("2025-06-14", False), ("2025-08-04", True)])
def test_pre_hospitalisation_window_includes_both_ends(on, kept):
    running, outcomes = run_step(pre_post_window, [surgeon(10_000), pre(consultant(1_000), on=on)])
    assert running.total == (11_000 if kept else 10_000)
    assert outcomes[0].fired_clause == (None if kept else C.PRE_HOSPITALISATION)


@pytest.mark.parametrize("on, kept", [("2025-08-07", True), ("2025-11-15", True), ("2025-11-16", False)])
def test_post_hospitalisation_window_includes_both_ends(on, kept):
    running, outcomes = run_step(pre_post_window, [surgeon(10_000), post(consultant(1_000), on=on)])
    assert running.total == (11_000 if kept else 10_000)
    assert outcomes[0].fired_clause == (None if kept else C.POST_HOSPITALISATION)


def test_no_pre_or_post_bills_means_no_window_check():
    assert run_step(pre_post_window, [surgeon(10_000)])[1] == []


def test_pre_and_post_bills_are_never_scaled_with_room_rent():
    running, outcomes = run_step(room_rent, [room(10_000, 1), pre(consultant(2_000), on="2025-07-30")])
    assert outcomes[0].facts["lines_scaled"] == ("L01",)
    assert running.total == 12_000 - 5_000


def test_non_payables_on_pre_and_post_bills_are_removed_too():
    running, _ = run_step(line_exclusions, [surgeon(10_000), pre(gloves(300), on="2025-07-30")])
    assert running.total == 10_000


# ---------------------------------------------------------------- AYUSH limit


def ayush_run(step, items, *, terms=None, system=TreatmentSystem.AYURVEDA, **policy_args):
    policy = build_policy(terms or placeholder_terms(), **policy_args)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-11 10:00",
        diagnosis=dx("M06.9", "Rheumatoid arthritis"),
        treatment_system=system,
        hospital=Hospital(name="Test Ayurveda Hospital", city="Kochi", ayush_hospital=True),
        items=items,
    )
    return step(Context.of(policy, claim), Running(claim.bill, sum(line.amount for line in claim.bill)))


def test_ayush_limit_caps_an_ayush_claim():
    running, outcomes = ayush_run(ayush_cap, [therapy(30_000, "Panchakarma")])  # placeholder limit 20,000
    assert (running.total, outcomes[0].fired_clause) == (20_000, C.AYUSH)


def test_ayush_limit_never_touches_allopathic_claims():
    assert ayush_run(ayush_cap, [surgeon(30_000)], system=TreatmentSystem.ALLOPATHY)[1] == []


def test_no_ayush_limit_means_up_to_the_sum_insured():
    terms = placeholder_terms(ayush=Ayush(covered=True, requires_ayush_hospital=True, cap=None))
    assert ayush_run(ayush_cap, [therapy(30_000, "Panchakarma")], terms=terms)[1] == []


def test_ayush_limit_can_be_a_share_of_sum_insured():
    terms = placeholder_terms(ayush=Ayush(covered=True, requires_ayush_hospital=True, cap=Cap(bp_of_si=1_000)))
    running, _ = ayush_run(ayush_cap, [therapy(30_000, "Panchakarma")], terms=terms, sum_insured=200_000)
    assert running.total == 20_000  # 10% of 2,00,000
