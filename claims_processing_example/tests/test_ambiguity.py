"""Guards against readings a wording leaves open: each fires when the answer could
depend on the reading, and stays quiet when it cannot."""

import datetime as dt

import pytest

from engine import adjudicate
from engine.schema import Hospital, TreatmentSystem
from sampler import ambiguity
from sampler.products.arogya_sanjeevani import TERMS
from tests.builders import (
    APPENDICECTOMY,
    APPENDICITIS,
    PNEUMONIA,
    anaesthetist,
    build_claim,
    build_policy,
    consultant,
    dx,
    icu,
    investigations,
    nursing,
    pharmacy,
    post,
    pre,
    px,
    room,
    surgeon,
    therapy,
)


def policy(**changes):
    values = {"sum_insured": 300_000, "copay_bp": 500, "first_inception": dt.date(2021, 4, 1)} | changes
    return build_policy(TERMS, **values)


def claim(items=None, **changes):
    values = {
        "admitted": "2025-08-04 10:00",
        "discharged": "2025-08-07 10:00",
        "diagnosis": APPENDICITIS,
        "procedures": [APPENDICECTOMY],
        "items": items if items is not None else [room(3_000, 3), surgeon(20_000), pharmacy(5_000)],
    } | changes
    return build_claim(**values)


def fires(guard, policy, claim) -> bool:
    return guard(policy, claim, adjudicate(policy, claim)) is not None


ROOM_ABOVE = [room(6_000, 3), nursing(500, 3), surgeon(20_000), pharmacy(5_000)]


# ---------------------------------------------------------------- every product


@pytest.mark.parametrize(
    "admitted, form_admitted, expected",
    [
        ("2025-05-01 10:00", None, True),  # 30 days from 1 Apr end on 1 May
        ("2025-05-02 10:00", None, False),
        ("2025-05-02 10:00", "2025-05-01 10:00", True),  # the claim form's date counts too
    ],
)
def test_a_wait_ending_on_the_admission_day_is_left_alone(admitted, form_admitted, expected):
    new = policy(first_inception=dt.date(2025, 4, 1))
    stay = dt.datetime.fromisoformat(admitted)
    c = claim(
        admitted=stay, discharged=stay + dt.timedelta(days=3),
        form_admitted=form_admitted,
        form_discharged=None if form_admitted is None else dt.datetime.fromisoformat(form_admitted) + dt.timedelta(days=3),
    )
    assert fires(ambiguity.wait_ends_on_admission_day, new, c) is expected


@pytest.mark.parametrize("on, expected", [("2025-07-05", True), ("2025-07-06", False), ("2025-07-04", False)])
def test_a_pre_hospitalisation_bill_on_the_last_day_of_its_window_is_left_alone(on, expected):
    # 30 days before 4 Aug is 5 Jul.
    c = claim([pre(consultant(1_000), on=on), room(3_000, 3), surgeon(20_000)])
    assert fires(ambiguity.bill_on_last_day_of_window, policy(), c) is expected


def test_a_post_hospitalisation_bill_on_the_last_day_of_its_window_is_left_alone():
    # 60 days after 7 Aug is 6 Oct.
    on_the_day = claim([room(3_000, 3), post(pharmacy(900), on="2025-10-06")])
    day_before = claim([room(3_000, 3), post(pharmacy(900), on="2025-10-05")])
    assert fires(ambiguity.bill_on_last_day_of_window, policy(), on_the_day)
    assert not fires(ambiguity.bill_on_last_day_of_window, policy(), day_before)


@pytest.mark.parametrize("discharged, expected", [("2025-08-05 10:00", True), ("2025-08-05 10:15", False)])
def test_a_stay_of_exactly_the_minimum_is_left_alone(discharged, expected):
    c = claim(discharged=discharged, items=[room(3_000, 1), pharmacy(2_000)], diagnosis=PNEUMONIA, procedures=[])
    assert fires(ambiguity.stay_of_exactly_the_minimum, policy(), c) is expected


# ---------------------------------------------------------------- wordings that need them


def test_percentage_limits_with_a_bonus_are_left_alone_only_when_the_bonus_would_matter():
    # Sum insured 1,00,000: room limit 2% = 2,000/day, or 2,200/day counting a 10,000 bonus.
    between = claim([room(2_100, 3), pharmacy(5_000)])
    assert fires(ambiguity.bonus_in_percentage_limits, policy(sum_insured=100_000, cumulative_bonus=10_000), between)
    assert not fires(ambiguity.bonus_in_percentage_limits, policy(sum_insured=100_000), between)
    # Sum insured 3,00,000: the fixed 5,000 limit is lower either way.
    above = claim([room(5_600, 3), pharmacy(5_000)])
    assert not fires(ambiguity.bonus_in_percentage_limits, policy(cumulative_bonus=30_000), above)


def test_copay_is_left_alone_only_when_the_claim_reaches_the_sum_insured():
    # Sum insured 1,00,000; the room is within its 2,000/day limit.
    big = claim([room(1_500, 3), surgeon(1_20_000), pharmacy(10_000)])  # 1,34,500 reaches co-pay
    small = claim([room(1_500, 3), surgeon(60_000), pharmacy(10_000)])  # 74,500
    assert fires(ambiguity.copay_after_sum_insured, policy(sum_insured=100_000), big)
    assert not fires(ambiguity.copay_after_sum_insured, policy(sum_insured=100_000), small)


def test_a_room_above_the_limit_with_an_icu_stay_is_left_alone():
    with_icu = claim([*ROOM_ABOVE, icu(8_000, 1)])
    assert fires(ambiguity.room_limit_with_icu_stay, policy(), with_icu)
    assert not fires(ambiguity.room_limit_with_icu_stay, policy(), claim(ROOM_ABOVE))
    within = claim([room(3_000, 3), icu(8_000, 1), surgeon(20_000)])
    assert not fires(ambiguity.room_limit_with_icu_stay, policy(), within)


def test_a_room_above_the_limit_with_pre_post_bills_is_left_alone():
    with_post = claim([*ROOM_ABOVE, post(pharmacy(900), on="2025-08-20")])
    assert fires(ambiguity.room_limit_with_pre_post_bills, policy(), with_post)
    assert not fires(ambiguity.room_limit_with_pre_post_bills, policy(), claim(ROOM_ABOVE))


def test_day_care_with_pre_post_bills_is_left_alone():
    hernia = {"diagnosis": dx("K40.9", "Inguinal hernia"), "procedures": [px("PX-HERNIA-REPAIR", "Hernia repair")],
              "admitted": "2025-08-04 07:00", "discharged": "2025-08-04 19:00", "room_category": None}
    bill = [surgeon(30_000), anaesthetist(7_000)]
    assert fires(ambiguity.pre_post_with_day_care, policy(), claim([*bill, post(pharmacy(900), on="2025-08-20")], **hernia))
    assert not fires(ambiguity.pre_post_with_day_care, policy(), claim(bill, **hernia))


def test_a_cataract_claim_with_pre_post_bills_is_left_alone():
    cataract = {"diagnosis": dx("H25.1", "Senile cataract"), "procedures": [px("PX-PHACO", "Phaco")],
                "admitted": "2025-08-04 08:00", "discharged": "2025-08-04 15:00", "room_category": None}
    bill = [surgeon(25_000), pharmacy(2_000)]
    assert fires(ambiguity.sublimit_with_pre_post, policy(), claim([*bill, pre(investigations(1_500), on="2025-07-30")], **cataract))
    assert not fires(ambiguity.sublimit_with_pre_post, policy(), claim(bill, **cataract))


def test_ayush_treatment_with_a_room_above_the_limit_is_left_alone():
    ayurveda = {"diagnosis": dx("M06.9", "Rheumatoid arthritis"), "procedures": [],
                "treatment_system": TreatmentSystem.AYURVEDA,
                "hospital": Hospital(name="Test Ayurveda Hospital", city="Pune", ayush_hospital=True)}
    above = claim([room(6_000, 3), therapy(9_000, "Panchakarma")], **ayurveda)
    within = claim([room(3_000, 3), therapy(9_000, "Panchakarma")], **ayurveda)
    assert fires(ambiguity.room_limit_on_ayush, policy(), above)
    assert not fires(ambiguity.room_limit_on_ayush, policy(), within)
    assert not fires(ambiguity.room_limit_on_ayush, policy(), claim(ROOM_ABOVE))  # allopathy


def test_the_first_reason_wins_and_none_means_keep():
    c, p = claim(), policy()
    d = adjudicate(p, c)
    assert ambiguity.first_reason((), p, c, d) is None
    assert ambiguity.first_reason((lambda *_: None, lambda *_: "second", lambda *_: "third"), p, c, d) == "second"
