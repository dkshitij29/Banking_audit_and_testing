"""Arogya Sanjeevani: its golden cases, and how it reads the catalogue.

The checks that every product must pass live in tests/test_corpus.py. What is
here is this product's own.
"""

import re

import pytest

from engine import adjudicate
from engine import clauses as C
from sampler.catalogue import CONDITIONS
from sampler.products.arogya_sanjeevani import AROGYA_SANJEEVANI, TERMS
from sampler.sample import sample_case
from sampler.scenarios import Builder
from tests.golden_arogya_sanjeevani import GOLDEN


# ---------------------------------------------------------------- golden cases


@pytest.mark.parametrize("build", GOLDEN, ids=lambda build: build.__name__)
def test_golden_case(build):
    case = build()
    decision = adjudicate(case.policy, case.claim)
    got = (decision.verdict, decision.payable, decision.clauses)
    assert got == (case.expected.verdict, case.expected.payable, case.expected.clauses)


def test_every_golden_case_shows_its_working():
    for build in GOLDEN:
        assert build.__doc__ and "Working" in build.__doc__ and "Expected:" in build.__doc__, build.__name__


# ---------------------------------------------------------------- the product's coding of its wording

# How the product treats every catalogue condition: (specified-disease wait in
# months, exclusion, cataract sub-limit, day care). Checked by hand against the
# wording's lists (6.3, 6.B, 4.3, 3.12). A change to the catalogue or to the
# product's codes changes this table, and the new row must be checked the same way.
CLASSIFICATION = {
    "pneumonia": (None, None, False, False),
    "dengue": (None, None, False, False),
    "typhoid": (None, None, False, False),
    "gastroenteritis": (None, None, False, False),
    "uti": (None, None, False, False),
    "pancreatitis": (None, None, False, False),
    "cellulitis": (None, None, False, False),
    "asthma": (None, None, False, False),
    "diabetic_foot": (None, None, False, False),
    "hypertensive_hf": (None, None, False, False),
    "mi_ptca": (None, None, False, False),
    "cabg": (None, None, False, False),
    "appendicitis": (None, None, False, False),
    "gallstones": (24, None, False, False),  # calculi in gall bladder
    "hernia": (24, None, False, True),  # hernia of all types
    "haemorrhoids": (24, None, False, True),  # piles
    "kidney_stone": (24, None, False, True),  # calculi in urinary system
    "cataract": (24, None, True, True),
    "knee_oa_tkr": (36, None, False, False),  # joint replacement; age-related osteoarthritis
    "tonsillitis": (24, None, False, True),  # tonsillectomy; benign ENT disorders
    "fibroids": (24, None, False, False),  # hysterectomy; benign tumours
    "tibia_fracture": (None, None, False, False),
    "femur_neck_fracture": (36, None, False, False),  # joint replacement, but an accident
    "radius_fracture": (None, None, False, True),
    "head_injury": (None, None, False, False),
    "nasal_fracture_reconstruction": (None, None, False, True),  # reconstruction after an accident
    "cosmetic_rhinoplasty": (None, C.COSMETIC, False, False),
    "myopia_lasik": (None, C.REFRACTIVE_ERROR, False, False),  # LASIK never needed admission: not day care
    "infertility_ivf": (None, C.STERILITY_INFERTILITY, False, False),
    "ra_ayurveda": (24, None, False, False),  # rheumatism; non-infective arthritis
    "back_pain_ayush": (24, None, False, False),  # spinal diseases
    "psoriasis_ayurveda": (None, None, False, False),
}


def classify(key):
    condition, matches = CONDITIONS[key], Builder.matches
    wait = max((g.duration.value for g in TERMS.specific_wait.groups if matches(condition, g.match)), default=None)
    exclusion = next((e.clause_id for e in TERMS.exclusions if matches(condition, e.match)), None)
    sublimited = any(matches(condition, s.match) for s in TERMS.sublimits)
    day_care = condition.procedure is not None and condition.procedure.code in TERMS.day_care_procedures
    return wait, exclusion, sublimited, day_care


def test_every_catalogue_condition_is_classified_as_checked():
    assert set(CLASSIFICATION) == set(CONDITIONS)
    assert {key: classify(key) for key in CONDITIONS} == CLASSIFICATION


def test_every_catalogue_refractive_error_is_under_seven_and_a_half_dioptres():
    """Excl15 excludes refractive error "less than 7.5 diopters"; the exclusion
    matches on the code, so every catalogue case must state a power under 7.5."""
    refractive = [c for c in CONDITIONS.values() if c.icd10.startswith("H52")]
    assert refractive
    for condition in refractive:
        for term in (condition.plain, *condition.clinical):
            powers = [abs(float(p)) for p in re.findall(r"(-?\d+(?:\.\d+)?) dioptres", term)]
            assert powers and max(powers) < 7.5, term


def test_short_stays_never_rest_on_an_arguable_day_care_procedure():
    """Every procedure the catalogue can admit for under 24 hours is day care by
    definition 3.12, or is excluded anyway. Stays under 24 hours without a
    procedure are medical admissions, which are not day care."""
    for key, condition in CONDITIONS.items():
        can_be_short = condition.day_care or condition.stay_days[0] <= 1
        if can_be_short and condition.procedure and classify(key)[1] is None:
            assert condition.procedure.code in TERMS.day_care_procedures, key


def test_every_policy_carries_the_wordings_cost_sharing_and_bonus():
    """7.III.5: 5% co-pay on every claim; no deductible. 5: cumulative bonus of 5%
    of sum insured per claim-free year, at most 50%."""
    for seed in range(100):
        policy = sample_case(seed, AROGYA_SANJEEVANI).policy
        assert (policy.copay_bp, policy.deductible) == (500, 0)
        steps, rest = divmod(policy.cumulative_bonus, policy.sum_insured * 5 // 100)
        assert rest == 0 and steps <= 10
