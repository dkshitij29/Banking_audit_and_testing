"""Validation rules on the engine's inputs."""

import datetime as dt

import pytest
from pydantic import ValidationError

from engine import clauses as C
from engine.schema import (
    BillCategory,
    BillLine,
    Claim,
    ClaimForm,
    DeclaredPed,
    DocType,
    Exclusion,
    LineExclusion,
    Match,
    Phase,
    Policy,
)
from tests.builders import (
    APPENDICITIS,
    build_claim,
    build_policy,
    ped,
    placeholder_terms,
    replace,
    surgeon,
)


def claim(**overrides):
    base = {"admitted": "2025-08-04 10:00", "discharged": "2025-08-07 10:00", "items": [surgeon(1_000)]}
    return build_claim(diagnosis=APPENDICITIS, **{**base, **overrides})


def line(**overrides):
    values = {
        "line_id": "L01",
        "date": dt.date(2025, 8, 4),
        "category": BillCategory.SURGEON,
        "item_code": "PF-SURGEON",
        "description": "Surgeon's fee",
        "unit_price": 1_000,
        "qty": 2,
        "amount": 2_000,
    }
    return BillLine(**{**values, **overrides})


def test_line_amount_must_equal_price_times_quantity():
    line()
    with pytest.raises(ValidationError, match="amount"):
        line(amount=1_999)


def test_types_are_never_coerced():
    with pytest.raises(ValidationError):
        line(unit_price="1000")
    with pytest.raises(ValidationError):
        line(qty=2.0)
    with pytest.raises(ValidationError):
        line(qty=True)


def test_discharge_must_follow_admission():
    with pytest.raises(ValidationError, match="discharge"):
        claim(discharged="2025-08-04 10:00")


def test_datetimes_must_be_naive():
    aware = dt.datetime(2025, 8, 4, 10, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    with pytest.raises(ValidationError):
        claim(admitted=aware)


def test_bill_lines_must_fall_inside_the_stay():
    with pytest.raises(ValidationError, match="outside the stay"):
        replace(claim(), bill=(line(date=dt.date(2025, 8, 1)),))


def test_member_cannot_be_first_insured_after_the_period_starts():
    with pytest.raises(ValidationError, match="first inception"):
        build_policy(placeholder_terms(), first_inception=dt.date(2025, 5, 1))


def test_set_like_fields_are_sorted_and_deduplicated():
    terms = placeholder_terms(
        day_care_procedures=("PX-B", "PX-A", "PX-B"),
        room_associated=(BillCategory.SURGEON, BillCategory.NURSING, BillCategory.SURGEON),
    )
    assert terms.day_care_procedures == ("PX-A", "PX-B")
    assert terms.room_associated == (BillCategory.NURSING, BillCategory.SURGEON)


@pytest.mark.parametrize("category", [BillCategory.ROOM, BillCategory.ICU])
def test_room_and_icu_cannot_be_room_associated(category):
    with pytest.raises(ValidationError):
        placeholder_terms(room_associated=(category,))


def test_line_exclusion_must_cite_a_registered_line_level_clause():
    LineExclusion(clause_id=C.DIETARY_SUPPLEMENTS, item_codes=("EX-X",))
    with pytest.raises(ValidationError, match="unknown clause"):
        LineExclusion(clause_id="9.9_made_up", item_codes=("EX-X",))
    with pytest.raises(ValidationError, match="must cite"):
        LineExclusion(clause_id=C.COPAY, item_codes=("EX-X",))


def test_an_item_cannot_be_listed_under_two_rules():
    with pytest.raises(ValidationError, match="listed under both"):
        placeholder_terms(
            line_exclusions=(
                LineExclusion(clause_id=C.NON_PAYABLE, item_codes=("NP-GLOVES",)),
                LineExclusion(clause_id=C.DIETARY_SUPPLEMENTS, item_codes=("NP-GLOVES",)),
            )
        )


def test_a_match_needs_at_least_one_code():
    with pytest.raises(ValidationError, match="at least one"):
        Match()


@pytest.mark.parametrize("prefix", ["H25", "K4", "H25.1", "E11"])
def test_icd10_prefixes_accept_categories_and_subcategories(prefix):
    Match(icd10_prefixes=(prefix,))


@pytest.mark.parametrize("prefix", ["h25", "H", "25", "H25.", "cataract"])
def test_icd10_prefixes_reject_text_and_malformed_codes(prefix):
    with pytest.raises(ValidationError):
        Match(icd10_prefixes=(prefix,))


def test_claim_level_exclusion_must_cite_a_standard_exclusion():
    Exclusion(clause_id=C.COSMETIC, match=Match(procedure_codes=("PX-X",)))
    with pytest.raises(ValidationError, match="standard exclusion"):
        Exclusion(clause_id=C.NON_PAYABLE, match=Match(procedure_codes=("PX-X",)))


def test_a_clause_cannot_exclude_both_claims_and_bill_lines():
    with pytest.raises(ValidationError, match="both whole claims and single bill lines"):
        placeholder_terms(
            exclusions=(Exclusion(clause_id=C.DIETARY_SUPPLEMENTS, match=Match(icd10_prefixes=("E56",))),)
        )


def test_a_declared_ped_needs_a_code():
    with pytest.raises(ValidationError):
        DeclaredPed(name="Diabetes", icd10_prefixes=())


@pytest.mark.parametrize(
    "phase, on, message",
    [
        (Phase.PRE, dt.date(2025, 8, 5), "dated after admission"),
        (Phase.POST, dt.date(2025, 8, 6), "dated before discharge"),
    ],
)
def test_pre_and_post_lines_must_sit_on_their_side_of_the_stay(phase, on, message):
    with pytest.raises(ValidationError, match=message):
        replace(claim(), bill=(line(date=on, phase=phase),))


def test_room_and_icu_charges_are_always_inpatient():
    with pytest.raises(ValidationError, match="always inpatient"):
        line(category=BillCategory.ROOM, phase=Phase.PRE, date=dt.date(2025, 8, 1))


def test_claim_form_contents_are_given_exactly_when_a_claim_form_was_submitted():
    original = claim()
    with pytest.raises(ValidationError, match="claim_form must be given"):
        replace(original, claim_form=None)
    with pytest.raises(ValidationError, match="claim_form must be given"):
        replace(original, documents_submitted=(DocType.DISCHARGE_SUMMARY, DocType.HOSPITAL_BILL))


def test_claim_form_discharge_must_follow_its_admission():
    with pytest.raises(ValidationError, match="claim form"):
        ClaimForm(
            claimed_amount=1_000,
            admitted_at=dt.datetime(2025, 8, 7, 10),
            discharged_at=dt.datetime(2025, 8, 4, 10),
        )


def test_json_round_trip_is_exact():
    policy = build_policy(placeholder_terms(), declared_peds=[ped("Type 2 diabetes mellitus", "E11")])
    assert Policy.model_validate_json(policy.model_dump_json()) == policy
    original = claim()
    assert Claim.model_validate_json(original.model_dump_json()) == original
