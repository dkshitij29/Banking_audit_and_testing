"""The clause registry. Clause IDs are graded, so this file pins them."""

from engine import clauses as C

FROZEN_IDS = (
    "2.1_min_hospitalisation",
    "2.2_day_care",
    "3.1_room_rent_limit",
    "3.2_icu_limit",
    "3.3_disease_sublimit",
    "3.4_ayush",
    "3.5_pre_hospitalisation",
    "3.6_post_hospitalisation",
    "4.1_ped_waiting",
    "4.2_specific_disease_waiting",
    "4.2_accident_exception",
    "4.3_initial_waiting",
    "4.3_accident_exception",
    "4.4_investigation_evaluation",
    "4.5_rest_cure_rehabilitation",
    "4.6_obesity_weight_control",
    "4.7_change_of_gender",
    "4.8_cosmetic_surgery",
    "4.9_hazardous_sports",
    "4.10_breach_of_law",
    "4.11_excluded_providers",
    "4.12_substance_abuse",
    "4.13_hydros_spas",
    "4.14_dietary_supplements",
    "4.15_refractive_error",
    "4.16_unproven_treatments",
    "4.17_sterility_infertility",
    "4.18_maternity",
    "5.1_deductible",
    "5.2_copay",
    "5.3_sum_insured",
    "6.1_policy_period",
    "7.1_missing_documents",
    "7.2_document_mismatch",
    "A1_non_payable_items",
)


def test_registered_ids_are_exactly_the_frozen_list():
    """Adding an ID means adding it here too. Renaming or removing one breaks grading."""
    assert tuple(C.REGISTRY) == FROZEN_IDS


def test_every_id_is_well_formed_and_described():
    for clause in C.REGISTRY.values():
        assert C.CLAUSE_ID_PATTERN.match(clause.id)
        assert clause.description and not any(ch.isdigit() for ch in clause.description), clause.id


def test_standard_exclusions_are_4_4_to_4_18():
    assert [clause_id.split("_")[0] for clause_id in C.STANDARD_EXCLUSIONS] == [f"4.{n}" for n in range(4, 19)]
