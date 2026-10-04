"""Golden cases for the New India Mediclaim product: worked by hand from its wording.

Like the other golden files, these are labels a person must check, independently
of the engine, against the wording itself (corpus/pdfs/new_india_mediclaim.pdf,
fetched by corpus/fetch.py; the page numbers below are the PDF's printed ones).

Several of them exist to catch what this product does differently from Arogya
Sanjeevani, since a benchmark with two products is only worth having if the
answers actually differ:

  NIM01/NIM02  the room limit is 1% of the sum insured with no rupee ceiling, so
               the same room rate is over the limit on one policy and under it on
               another.
  NIM06        a hernia repair finished inside a day is not covered, because this
               product's day care cover is a closed list and hernia repair is not
               on it. Under Arogya Sanjeevani's open definition the same claim is
               paid (AS06).
  NIM07/NIM08  diabetes, hypertension and cardiac conditions wait ninety days, a
               tier Arogya Sanjeevani has no equivalent of.
  NIM09        pre-existing diseases wait forty-eight months here, not thirty-six.
  NIM13        AYUSH treatment needs no AYUSH hospital, where under Arogya
               Sanjeevani the same claim is refused (AS14).

THE RULES these cases use (the wording's own section numbers):

  Room rent     3.1(a): room, boarding, DMO/RMO/CMO/RMP and nursing, not exceeding
                1% of the sum insured a day (p10). Nursing counts in that rate.
  Proportionate 3.2 with 2.46: above the limit the deduction falls on Associate
  deduction     Medical Expenses only, being professional fees, anaesthesia,
                theatre and procedure charges, and never on pharmacy, consumables,
                implants or diagnostics (p7, p10).
  ICU           3.1(b): 2% of the sum insured a day, with no proportionate
                deduction (p10).
  Cataract      3.3: 20% of the sum insured, at most Rs 50,000, for each eye (p10).
  AYUSH         3.4: up to 100% of the sum insured, anywhere (p10).
  Pre / post    3.1(e), 3.1(f): 30 days before, 60 days after (p10).
  Waits         4.1 PED 48 months; 4.2 listed conditions 90 days / 24 / 36 / 48
                months, accidents excepted; 4.3 first 30 days (p16-18).
  Day care      2.18 with Annexure I, a closed list of 226 procedures (p4, p30-32).
  Co-payment    3.16: none, unless the policyholder buys a voluntary 20% (p13).

THE POLICY, unless a case says otherwise: period 1 Apr 2025 - 31 Mar 2026, sum
insured Rs 3,00,000 (so the room limit is Rs 3,000 a day and the intensive care
limit Rs 6,000), no cumulative bonus, no co-payment, member covered without break
since 1 Apr 2020, so every waiting period is long over.

THE CLAIM, unless a case says otherwise: allopathic, illness, all three documents
submitted and agreeing with each other.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from engine import clauses as C
from engine.schema import Cause, Claim, Hospital, Policy, TreatmentSystem, Verdict
from sampler.products.new_india_mediclaim import TERMS
from tests.builders import (
    admission_kit,
    anaesthetist,
    build_claim,
    build_policy,
    consultant,
    dx,
    gloves,
    icu,
    implant,
    investigations,
    nursing,
    ot,
    ped,
    pharmacy,
    post,
    pre,
    px,
    registration,
    room,
    surgeon,
    therapy,
)
from tests.golden_cases import Expected, GoldenCase, expect

GOLDEN: list[Callable[[], GoldenCase]] = []


def golden(build: Callable[[], tuple[Policy, Claim, Expected]]) -> Callable[[], GoldenCase]:
    def case() -> GoldenCase:
        policy, claim, expected = build()
        return GoldenCase(build.__name__, policy, claim, expected)

    case.__name__ = build.__name__
    case.__doc__ = build.__doc__
    GOLDEN.append(case)
    return case


def policy(**changes) -> Policy:
    values = {"sum_insured": 300_000, "first_inception": dt.date(2020, 4, 1)} | changes
    return build_policy(TERMS, **values)


CATARACT = dx("H25.1", "Senile nuclear cataract")
DIABETIC_FOOT = dx("E11.5", "Type 2 diabetes mellitus with foot ulcer")
PNEUMONIA = dx("J18.9", "Pneumonia")
APPENDICITIS = dx("K35.8", "Acute appendicitis")
APPENDICECTOMY = px("PX-LAP-APPENDICECTOMY", "Laparoscopic appendicectomy")


# ---------------------------------------------------------------- the room limit is a share


FOUR_DAY_BILL = [
    room(2_600, days=4),
    nursing(500, days=4),
    surgeon(30_000),
    anaesthetist(7_000),
    ot(12_000),
    pharmacy(9_000),
    investigations(5_000),
    gloves(400),
]


def _four_day_stay():
    return build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-08 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=FOUR_DAY_BILL,
    )


@golden
def nim01_room_over_a_one_percent_limit():
    """NIM01. Room and nursing together pass 1% of the sum insured -> PARTIAL

    Sum insured Rs 3,00,000, so the room limit is Rs 3,000 a day.
    Acute appendicitis, laparoscopic appendicectomy.
    Admitted 4 Aug 2025 10:00, discharged 8 Aug 10:00 (4 days).

      Room            4 days x 2,600      10,400
      Nursing         4 days x 500         2,000
      Surgeon                             30,000
      Anaesthetist                         7,000
      OT                                  12,000
      Pharmacy                             9,000
      Investigations                       5,000
      Surgical gloves   (non-payable)        400
      Bill total                          75,800

    Working
      Non-payables    gloves 400 off                                        75,400
      Room rent       limit 1% of 3,00,000 = 3,000/day. Room and nursing count
                      together (3.1(a)): (10,400 + 2,000) / 4 = 3,100/day, above
                      the limit, ratio 3,000/3,100 = 30/31.
                      Scaled: room 10,400 + nursing 2,000 + surgeon 30,000
                      + anaesthetist 7,000 + OT 12,000 = 61,400;
                      61,400 x 1/31 = 1,980.65 -> 1,981 off                  73,419
                      (pharmacy and investigations are spared by 3.2)

    Expected: PARTIAL, Rs 73,419, clauses [3.1_room_rent_limit, A1_non_payable_items]
    """
    return policy(), _four_day_stay(), expect(Verdict.PARTIAL, 73_419, C.ROOM_RENT, C.NON_PAYABLE)


@golden
def nim02_the_same_room_is_within_the_limit_on_a_larger_policy():
    """NIM02. The same claim at a sum insured of Rs 5,00,000 -> APPROVE

    Identical to NIM01 in every respect except the sum insured, which makes the
    room limit 1% of 5,00,000 = Rs 5,000 a day. There is no rupee ceiling on this
    product's room limit, so the same Rs 3,100 a day that was over the limit in
    NIM01 is under it here.

    Working
      Non-payables    gloves 400 off                                        75,400
      Room rent       3,100/day is within the 5,000/day limit
      Sum insured     75,400 is within 5,00,000

    Expected: APPROVE, Rs 75,400, clauses [A1_non_payable_items]
    """
    return policy(sum_insured=500_000), _four_day_stay(), expect(Verdict.APPROVE, 75_400, C.NON_PAYABLE)


@golden
def nim03_intensive_care_over_its_limit_is_cut_alone():
    """NIM03. ICU above 2% of the sum insured, and nothing else is touched -> PARTIAL

    Pneumonia. Admitted 4 Aug 2025 10:00, discharged 9 Aug 10:00 (5 days: 2 in
    intensive care, 3 on the ward).

      Room            3 days x 2,000       6,000
      Nursing         3 days x 400         1,200
      ICU             2 days x 9,000      18,000
      Consultant                           5,000
      Pharmacy                            12,000
      Investigations                       8,000
      Bill total                          50,200

    Working
      Room rent       (6,000 + 1,200) / 3 = 2,400/day, within the 3,000 limit
      ICU             limit 2% of 3,00,000 = 6,000/day; 9,000 is above it, so the
                      ICU line is paid at 6,000/9,000 = 2/3:
                      18,000 x 1/3 = 6,000 off                               44,200
                      Nothing else is scaled: 3.2 reaches only Associate Medical
                      Expenses, and intensive care is not one of them.

    Expected: PARTIAL, Rs 44,200, clauses [3.2_icu_limit]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-09 10:00",
        diagnosis=PNEUMONIA,
        items=[
            room(2_000, days=3),
            nursing(400, days=3),
            icu(9_000, days=2),
            consultant(5_000),
            pharmacy(12_000),
            investigations(8_000),
        ],
    )
    return policy(), claim, expect(Verdict.PARTIAL, 44_200, C.ICU_LIMIT)


# ---------------------------------------------------------------- the cataract limit, both ways


@golden
def nim04_cataract_both_eyes_where_the_rupee_ceiling_bites():
    """NIM04. Cataract, both eyes, sum insured Rs 3,00,000 -> PARTIAL

    20% of 3,00,000 is 60,000, so the Rs 50,000 ceiling is the lower of the two
    and applies to each eye.
    Senile nuclear cataract, phacoemulsification, both eyes.
    Admitted 4 Aug 2025 08:00, discharged 16:00 (8 hours).

      Surgeon                             55,000
      Anaesthetist                        11,000
      OT                                  16,000
      Intraocular lens  2 x 22,000        44,000
      Pharmacy                             3,000
      Investigations                       2,500
      Registration      (non-payable)        500
      Bill total                        1,32,000

    Working
      Minimum stay    8 h is under 24 h, but surgery for cataract is item 55 of
                      Annexure I                                    -> 2.2_day_care
      Non-payables    registration 500 off                                 1,31,500
      Cataract limit  20% of 3,00,000 = 60,000 or 50,000, whichever is lower:
                      50,000 x 2 eyes = 1,00,000; capped, 31,500 off        1,00,000

    Expected: PARTIAL, Rs 1,00,000, clauses [2.2_day_care, 3.3_disease_sublimit, A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 08:00",
        discharged="2025-08-04 16:00",
        diagnosis=CATARACT,
        procedures=[px("PX-PHACO", "Phacoemulsification with IOL, both eyes", units=2)],
        room_category=None,
        items=[
            surgeon(55_000),
            anaesthetist(11_000),
            ot(16_000),
            implant(22_000, "Intraocular lens", qty=2),
            pharmacy(3_000),
            investigations(2_500),
            registration(500),
        ],
    )
    return policy(), claim, expect(Verdict.PARTIAL, 100_000, C.DAY_CARE, C.DISEASE_SUBLIMIT, C.NON_PAYABLE)


@golden
def nim05_cataract_one_eye_where_the_percentage_bites():
    """NIM05. Cataract, one eye, sum insured Rs 2,00,000 -> PARTIAL

    20% of 2,00,000 is 40,000, which is below the Rs 50,000 ceiling, so the
    percentage is what limits this claim.
    Admitted 4 Aug 2025 09:00, discharged 15:00 (6 hours).

      Surgeon                             30,000
      Anaesthetist                         6,000
      OT                                   9,000
      Intraocular lens                    18,000
      Pharmacy                             2,000
      Investigations                       1,500
      Bill total                          66,500

    Working
      Minimum stay    6 h, cataract surgery is day care            -> 2.2_day_care
      Cataract limit  40,000 for the one eye; capped, 26,500 off            40,000

    Expected: PARTIAL, Rs 40,000, clauses [2.2_day_care, 3.3_disease_sublimit]
    """
    claim = build_claim(
        admitted="2025-08-04 09:00",
        discharged="2025-08-04 15:00",
        diagnosis=CATARACT,
        procedures=[px("PX-PHACO", "Phacoemulsification with IOL")],
        room_category=None,
        items=[
            surgeon(30_000),
            anaesthetist(6_000),
            ot(9_000),
            implant(18_000, "Intraocular lens"),
            pharmacy(2_000),
            investigations(1_500),
        ],
    )
    return policy(sum_insured=200_000), claim, expect(Verdict.PARTIAL, 40_000, C.DAY_CARE, C.DISEASE_SUBLIMIT)


# ---------------------------------------------------------------- day care is a closed list


@golden
def nim06_hernia_repair_inside_a_day_is_not_day_care_here():
    """NIM06. Hernia repair, discharged the same day -> REJECT

    The same admission that Arogya Sanjeevani pays in AS06. This product's day
    care cover is Annexure I, a closed list of 226 procedures, and a hernia repair
    is nowhere on it, so the 24-hour rule in 2.18 is not lifted.

    Inguinal hernia, Lichtenstein mesh repair.
    Admitted 4 Aug 2025 07:00, discharged 17:00 (10 hours).

      Surgeon                             30,000
      Anaesthetist                         7,000
      OT                                  12,000
      Mesh                                 8,000
      Pharmacy                             2,500
      Investigations                       2,000
      Bill total                          61,500

    Working
      Specified wait  hernia waits 24 months from 1 Apr 2020, over on 1 Apr 2022
      Minimum stay    10 h is under 24 h, and no procedure is on Annexure I -> 2.1

    Expected: REJECT, Rs 0, clauses [2.1_min_hospitalisation]
    """
    claim = build_claim(
        admitted="2025-08-04 07:00",
        discharged="2025-08-04 17:00",
        diagnosis=dx("K40.9", "Inguinal hernia"),
        procedures=[px("PX-HERNIA-REPAIR", "Lichtenstein mesh hernioplasty")],
        room_category=None,
        items=[
            surgeon(30_000),
            anaesthetist(7_000),
            ot(12_000),
            implant(8_000, "Mesh"),
            pharmacy(2_500),
            investigations(2_000),
        ],
    )
    return policy(), claim, expect(Verdict.REJECT, 0, C.MIN_HOSPITALISATION)


# ---------------------------------------------------------------- the ninety-day tier


NINETY_DAY_BILL = [
    room(2_000, days=5),
    nursing(400, days=5),
    pharmacy(18_000),
    investigations(7_000),
    registration(300),
]


@golden
def nim07_a_diabetic_admission_inside_the_ninety_days():
    """NIM07. Diabetes sixty-four days into a new policy -> REJECT

    New policy: first cover 1 Apr 2025. Type 2 diabetes mellitus with foot ulcer.
    Admitted 4 Jun 2025 10:00, discharged 9 Jun 10:00.

      Room            5 days x 2,000      10,000
      Nursing         5 days x 400         2,000
      Pharmacy                            18,000
      Investigations                       7,000
      Registration      (non-payable)        300
      Bill total                          37,300

    Working
      Initial wait    30 days from 1 Apr 2025, over on 1 May 2025; admitted after it
      Specified wait  Diabetes Mellitus is in the ninety-day list (4.2 (i)), which
                      runs from 1 Apr 2025 to 30 Jun 2025; admitted 4 Jun, inside -> 4.2

    Expected: REJECT, Rs 0, clauses [4.2_specific_disease_waiting]
    """
    claim = build_claim(
        admitted="2025-06-04 10:00",
        discharged="2025-06-09 10:00",
        diagnosis=DIABETIC_FOOT,
        items=NINETY_DAY_BILL,
    )
    return policy(first_inception=dt.date(2025, 4, 1)), claim, expect(Verdict.REJECT, 0, C.SPECIFIC_WAITING)


@golden
def nim08_the_same_admission_after_the_ninety_days():
    """NIM08. The same diabetic admission, after the ninety days -> APPROVE

    As NIM07, but admitted 4 Aug 2025, by which time the ninety days that ended on
    30 Jun 2025 are behind the member.

    Working
      Specified wait  the ninety days from 1 Apr 2025 were over on 30 Jun 2025
      Non-payables    registration 300 off                                  37,000
      Room rent       (10,000 + 2,000) / 5 = 2,400/day, within the 3,000 limit

    Expected: APPROVE, Rs 37,000, clauses [A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-09 10:00",
        diagnosis=DIABETIC_FOOT,
        items=NINETY_DAY_BILL,
    )
    return policy(first_inception=dt.date(2025, 4, 1)), claim, expect(Verdict.APPROVE, 37_000, C.NON_PAYABLE)


# ---------------------------------------------------------------- the longer waits


@golden
def nim09_declared_diabetes_inside_forty_eight_months():
    """NIM09. Diabetic foot forty months into cover, diabetes declared -> REJECT

    Pre-existing diseases wait forty-eight months under this wording, where the
    2024 standard product waits thirty-six. The engine matches the document it is
    given.

    Member covered without break since 1 Apr 2022; declared type 2 diabetes
    mellitus (E11). Admitted 4 Aug 2025 10:00, discharged 9 Aug 10:00.

      Room            5 days x 2,000      10,000
      Nursing         5 days x 400         2,000
      Pharmacy                            20,000
      Investigations                       9,000
      Bill total                          41,000

    Working
      Specified wait  the ninety days for Diabetes Mellitus ended on 30 Jun 2022
      PED wait        E11.5 is a direct complication of the declared diabetes;
                      48 months from 1 Apr 2022 run to 1 Apr 2026; admitted
                      4 Aug 2025, inside                                     -> 4.1

    Expected: REJECT, Rs 0, clauses [4.1_ped_waiting]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-09 10:00",
        diagnosis=DIABETIC_FOOT,
        items=[room(2_000, days=5), nursing(400, days=5), pharmacy(20_000), investigations(9_000)],
    )
    return (
        policy(first_inception=dt.date(2022, 4, 1), declared_peds=[ped("Type 2 diabetes mellitus", "E11")]),
        claim,
        expect(Verdict.REJECT, 0, C.PED_WAITING),
    )


@golden
def nim10_knee_replacement_waits_forty_eight_months():
    """NIM10. Knee replacement forty months into cover -> REJECT

    The claim is under three of the listed groups at once: Non Infective Arthritis
    at 24 months, and both Joint Replacement due to Degenerative Condition and
    Age-related Osteoarthritis at 48. The longest applies (4.2.c).

    Member covered since 1 Apr 2022. Primary osteoarthritis of the knee, total
    knee replacement. Admitted 4 Aug 2025 10:00, discharged 9 Aug 10:00.

      Room            5 days x 2,500      12,500
      Nursing         5 days x 600         3,000
      Surgeon                             90,000
      Anaesthetist                        22,000
      OT                                  40,000
      Knee prosthesis                   1,10,000
      Pharmacy                            20,000
      Investigations                      10,000
      Bill total                        3,07,500

    Working
      Specified wait  48 months from 1 Apr 2022 run to 1 Apr 2026; admitted
                      4 Aug 2025, inside                                     -> 4.2

    Expected: REJECT, Rs 0, clauses [4.2_specific_disease_waiting]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-09 10:00",
        diagnosis=dx("M17.1", "Primary osteoarthritis of the knee"),
        procedures=[px("PX-TKR", "Total knee arthroplasty")],
        items=[
            room(2_500, days=5),
            nursing(600, days=5),
            surgeon(90_000),
            anaesthetist(22_000),
            ot(40_000),
            implant(110_000, "Knee prosthesis"),
            pharmacy(20_000),
            investigations(10_000),
        ],
    )
    return policy(first_inception=dt.date(2022, 4, 1)), claim, expect(Verdict.REJECT, 0, C.SPECIFIC_WAITING)


@golden
def nim11_hip_replacement_after_a_fall_is_excepted():
    """NIM11. Hip replacement after a fall, forty months into cover -> APPROVE

    Sum insured Rs 5,00,000, so the room limit is Rs 5,000 a day.
    Member covered since 1 Apr 2022. Fracture of the neck of the femur in a fall;
    total hip replacement. Admitted 4 Aug 2025 10:00, discharged 10 Aug 10:00 (6 days).

      Room            6 days x 4,000      24,000
      Nursing         6 days x 700         4,200
      Surgeon                             95,000
      Anaesthetist                        22,000
      OT                                  40,000
      Hip prosthesis                    1,20,000
      Pharmacy                            25,000
      Investigations                      12,000
      Surgical gloves   (non-payable)        700
      Bill total                        3,42,900

    Working
      Specified wait  Joint Replacement waits 48 months, over on 1 Apr 2026, but
                      the claim arises from an accident, which 4.2.a excepts
                                                          -> 4.2_accident_exception
      Non-payables    gloves 700 off                                      3,42,200
      Room rent       (24,000 + 4,200) / 6 = 4,700/day, within the 5,000 limit
      Sum insured     3,42,200 is within 5,00,000

    Expected: APPROVE, Rs 3,42,200, clauses [4.2_accident_exception, A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-10 10:00",
        diagnosis=dx("S72.0", "Fracture of neck of femur"),
        procedures=[px("PX-THR", "Total hip arthroplasty")],
        cause=Cause.ACCIDENT,
        items=[
            room(4_000, days=6),
            nursing(700, days=6),
            surgeon(95_000),
            anaesthetist(22_000),
            ot(40_000),
            implant(120_000, "Hip prosthesis"),
            pharmacy(25_000),
            investigations(12_000),
            gloves(700),
        ],
    )
    return (
        policy(sum_insured=500_000, first_inception=dt.date(2022, 4, 1)),
        claim,
        expect(Verdict.APPROVE, 342_200, C.SPECIFIC_WAITING_ACCIDENT, C.NON_PAYABLE),
    )


# ---------------------------------------------------------------- what the policyholder bears


@golden
def nim12_a_voluntary_co_payment():
    """NIM12. A policy bought with the voluntary 20% co-payment -> APPROVE

    There is no co-payment on this product unless the policyholder buys one for a
    discount on the premium (3.16). Co-payment is cost sharing the policyholder
    agreed to, so the verdict stays APPROVE.

    Acute appendicitis. Admitted 4 Aug 2025 10:00, discharged 7 Aug 10:00.

      Room            3 days x 2,400       7,200
      Nursing         3 days x 500         1,500
      Surgeon                             25,000
      Anaesthetist                         6,000
      OT                                  10,000
      Pharmacy                             6,000
      Investigations                       4,000
      Admission kit     (non-payable)        600
      Bill total                          60,300

    Working
      Non-payables    admission kit 600 off                                 59,700
      Room rent       (7,200 + 1,500) / 3 = 2,900/day, within the 3,000 limit
      Co-payment      20% of 59,700 = 11,940 off                            47,760

    Expected: APPROVE, Rs 47,760, clauses [5.2_copay, A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=[
            room(2_400, days=3),
            nursing(500, days=3),
            surgeon(25_000),
            anaesthetist(6_000),
            ot(10_000),
            pharmacy(6_000),
            investigations(4_000),
            admission_kit(600),
        ],
    )
    return policy(copay_bp=2_000), claim, expect(Verdict.APPROVE, 47_760, C.COPAY, C.NON_PAYABLE)


# ---------------------------------------------------------------- AYUSH, and the windows


@golden
def nim13_ayurveda_in_a_hospital_that_is_not_an_ayush_hospital():
    """NIM13. Ayurvedic treatment at a general hospital -> APPROVE

    3.4 covers AYUSH treatment up to the sum insured and says nothing about where
    it must be taken. The same claim under Arogya Sanjeevani is refused (AS14),
    because that wording covers AYUSH only in an AYUSH hospital.

    Rheumatoid arthritis, Ayurvedic treatment at a general hospital.
    Admitted 4 Aug 2025 10:00, discharged 14 Aug 10:00 (10 days).

      Room            10 days x 2,000     20,000
      Nursing         10 days x 300        3,000
      Consultant                           6,000
      Panchakarma therapy                 15,000
      Pharmacy                             5,000
      Investigations                       1,500
      Registration      (non-payable)        300
      Bill total                          50,800

    Working
      Specified wait  rheumatoid arthritis is listed at 24 months, over on 1 Apr 2022
      AYUSH           covered up to the sum insured, wherever taken
      Non-payables    registration 300 off                                  50,500
      Room rent       (20,000 + 3,000) / 10 = 2,300/day, within the 3,000 limit

    Expected: APPROVE, Rs 50,500, clauses [A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-14 10:00",
        diagnosis=dx("M06.9", "Rheumatoid arthritis"),
        treatment_system=TreatmentSystem.AYURVEDA,
        hospital=Hospital(name="Test Hospital", city="Pune"),
        items=[
            room(2_000, days=10),
            nursing(300, days=10),
            consultant(6_000),
            therapy(15_000, "Panchakarma therapy"),
            pharmacy(5_000),
            investigations(1_500),
            registration(300),
        ],
    )
    return policy(), claim, expect(Verdict.APPROVE, 50_500, C.NON_PAYABLE)


@golden
def nim14_a_bill_thirty_one_days_before_admission():
    """NIM14. A consultation a day outside the pre-hospitalisation window -> PARTIAL

    The room rate here is exactly the limit, which is payable in full: 3.1(a)
    allows a rate "not exceeding" 1% of the sum insured.

    Acute appendicitis. Admitted 4 Aug 2025 10:00, discharged 7 Aug 10:00.

      Consultation  (pre, 4 Jul 2025)      1,000
      Tests         (pre, 20 Jul 2025)     3,000
      Room            3 days x 2,500       7,500
      Nursing         3 days x 500         1,500
      Surgeon                             25,000
      Anaesthetist                         6,000
      OT                                  10,000
      Pharmacy                             5,000
      Investigations                       3,000
      Follow-up     (post, 30 Sep 2025)      800
      Medicines     (post, 5 Oct 2025)     1,200
      Bill total                          64,000

    Working
      Pre-hospitalisation   30 days before 4 Aug is 5 Jul. The 4 Jul consultation
                            is 31 days before, outside: 1,000 off            63,000
                            The 20 Jul tests are inside
      Post-hospitalisation  60 days after 7 Aug runs to 6 Oct; both are inside
      Room rent             (7,500 + 1,500) / 3 = 3,000/day, exactly the limit,
                            so nothing is deducted

    Expected: PARTIAL, Rs 63,000, clauses [3.5_pre_hospitalisation]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=[
            pre(consultant(1_000, "Consultation"), on="2025-07-04"),
            pre(investigations(3_000, "Tests"), on="2025-07-20"),
            room(2_500, days=3),
            nursing(500, days=3),
            surgeon(25_000),
            anaesthetist(6_000),
            ot(10_000),
            pharmacy(5_000),
            investigations(3_000),
            post(consultant(800, "Follow-up"), on="2025-09-30"),
            post(pharmacy(1_200, "Medicines"), on="2025-10-05"),
        ],
    )
    return policy(), claim, expect(Verdict.PARTIAL, 63_000, C.PRE_HOSPITALISATION)
