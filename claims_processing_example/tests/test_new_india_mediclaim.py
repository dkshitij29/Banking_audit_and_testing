"""New India Mediclaim: its golden cases, and how it reads the catalogue.

The checks that every product must pass live in tests/test_corpus.py. What is
here is this product's own: the answers a person worked out by hand, and the
table of how its lists classify every condition the sampler can draw.
"""

import datetime as dt
import re

import pytest

from engine import adjudicate
from engine import clauses as C
from sampler.catalogue import CONDITIONS
from sampler.products.new_india_mediclaim import NEW_INDIA_MEDICLAIM, TERMS
from sampler.scenarios import Builder
from tests.golden_new_india_mediclaim import GOLDEN


@pytest.mark.parametrize("build", GOLDEN, ids=lambda build: build.__name__)
def test_golden_case(build):
    case = build()
    decision = adjudicate(case.policy, case.claim)
    got = (decision.verdict, decision.payable, decision.clauses)
    assert got == (case.expected.verdict, case.expected.payable, case.expected.clauses)


def test_every_golden_case_shows_its_working():
    for build in GOLDEN:
        assert build.__doc__ and "Working" in build.__doc__ and "Expected:" in build.__doc__, build.__name__


# How this product treats every catalogue condition: (the longest specified
# waiting period, the exclusion, the cataract sub-limit, day care). Checked by
# hand against 4.2's four lists, 4.4, 3.3 and Annexure I. A change to the
# catalogue or to the product's codes changes this table, and the new row must be
# checked the same way.
CLASSIFICATION = {
    "pneumonia": (None, None, False, False),
    "dengue": (None, None, False, False),
    "typhoid": (None, None, False, False),
    "gastroenteritis": (None, None, False, False),
    "uti": (None, None, False, False),
    "pancreatitis": (None, None, False, False),
    "cellulitis": (None, None, False, False),  # an infection, not a "Skin Disorder"
    "asthma": (None, None, False, False),
    "diabetic_foot": ("90 days", None, False, False),  # Diabetes Mellitus, 4.2 (i)
    "hypertensive_hf": ("90 days", None, False, False),  # Hypertension, 4.2 (i)
    "mi_ptca": ("90 days", None, False, False),  # Cardiac Conditions, 4.2 (i)
    "cabg": ("90 days", None, False, False),  # Cardiac Conditions, 4.2 (i)
    "appendicitis": (None, None, False, False),
    "gallstones": ("24 months", None, False, False),
    "hernia": ("24 months", None, False, False),  # and not on Annexure I
    "haemorrhoids": ("24 months", None, False, True),
    "kidney_stone": ("24 months", None, False, True),
    "cataract": ("24 months", None, True, True),
    "knee_oa_tkr": ("48 months", None, False, False),  # the longest of three groups
    "tonsillitis": ("24 months", None, False, True),
    "fibroids": ("24 months", None, False, False),
    "tibia_fracture": (None, None, False, False),
    "femur_neck_fracture": ("48 months", None, False, False),  # but an accident
    "radius_fracture": (None, None, False, True),
    "head_injury": (None, None, False, False),
    "nasal_fracture_reconstruction": (None, None, False, True),
    "cosmetic_rhinoplasty": (None, C.COSMETIC, False, False),
    "myopia_lasik": (None, C.REFRACTIVE_ERROR, False, False),
    "infertility_ivf": (None, C.STERILITY_INFERTILITY, False, False),
    "ra_ayurveda": ("24 months", None, False, False),
    "back_pain_ayush": ("24 months", None, False, False),
    "psoriasis_ayurveda": ("24 months", None, False, False),  # a chronic skin disorder
}


def classify(key):
    condition, matches = CONDITIONS[key], Builder.matches
    groups = [g for g in TERMS.specific_wait.groups if matches(condition, g.match)]
    # Longest by the date it ends, since the tiers mix days with months.
    longest = max((g.duration for g in groups), key=lambda d: d.add_to(dt.date(2000, 1, 1)), default=None)
    exclusion = next((e.clause_id for e in TERMS.exclusions if matches(condition, e.match)), None)
    sublimited = any(matches(condition, s.match) for s in TERMS.sublimits)
    day_care = condition.procedure is not None and condition.procedure.code in TERMS.day_care_procedures
    return (longest.describe() if longest else None), exclusion, sublimited, day_care


def test_every_catalogue_condition_is_classified_as_checked():
    assert set(CLASSIFICATION) == set(CONDITIONS)
    assert {key: classify(key) for key in CONDITIONS} == CLASSIFICATION


def test_the_ninety_day_tier_is_reachable_and_is_this_product_s_own():
    """No other product modelled so far has a waiting period shorter than a year."""
    from sampler.products.arogya_sanjeevani import TERMS as AROGYA

    short = [g for g in TERMS.specific_wait.groups if g.duration.unit.value == "DAYS"]
    assert {g.name for g in short} == {"Diabetes Mellitus", "Hypertension", "Cardiac Conditions"}
    assert [key for key in CONDITIONS if classify(key)[0] == "90 days"]
    assert not [g for g in AROGYA.specific_wait.groups if g.duration.unit.value == "DAYS"]


def test_hernia_repair_is_day_care_under_one_product_and_not_the_other():
    """Annexure I is a closed list and hernia repair is not on it, where Arogya
    Sanjeevani has only a definition, which a hernia repair meets."""
    from sampler.products.arogya_sanjeevani import TERMS as AROGYA

    assert "PX-HERNIA-REPAIR" not in TERMS.day_care_procedures
    assert "PX-HERNIA-REPAIR" in AROGYA.day_care_procedures


def test_the_room_limit_has_no_rupee_ceiling():
    """1% of the sum insured, whatever that comes to, which is what makes NIM01
    and NIM02 differ."""
    assert TERMS.room_cap.rupees is None and TERMS.room_cap.bp_of_si == 100
    assert TERMS.icu_cap.rupees is None and TERMS.icu_cap.bp_of_si == 200


def test_the_wording_settles_the_bonus_question_so_no_guard_is_carried():
    from sampler import ambiguity

    assert ambiguity.bonus_in_percentage_limits not in NEW_INDIA_MEDICLAIM.ambiguities
    assert ambiguity.room_limit_with_icu_stay not in NEW_INDIA_MEDICLAIM.ambiguities


def test_every_catalogue_refractive_error_is_under_seven_and_a_half_dioptres():
    for condition in [c for c in CONDITIONS.values() if c.icd10.startswith("H52")]:
        for term in (condition.plain, *condition.clinical):
            powers = [abs(float(p)) for p in re.findall(r"(-?\d+(?:\.\d+)?) dioptres", term)]
            assert powers and max(powers) < 7.5, term
