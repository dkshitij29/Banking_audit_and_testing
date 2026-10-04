"""Golden cases for Arogya Sanjeevani: claims worked out by hand from the real wording.

Like tests/golden_cases.py, these are labels a person must check by hand,
independently of the engine. Unlike those, they run against the real product
terms (sampler/products/arogya_sanjeevani.py), so they also prove the product
was extracted correctly: check each case against the wording itself
(corpus/pdfs/arogya_sanjeevani_gci.pdf, fetched by corpus/fetch.py; page
numbers below are the PDF's printed ones).

THE RULES these cases use (the wording's section numbers):

  Room rent         4.1.i: "Room Rent, Boarding, Nursing Expenses" up to 2% of sum
                    insured, at most ₹5,000 a day (p7). Nursing counts in the rate.
  Proportionate     4.1.1 Note 2: above the room limit, everything except pharmacy,
  deduction         consumables, implants, medical devices and diagnostics is paid
                    in the ratio limit / actual rate (p7).
  ICU               4.1.ii: 5% of sum insured, at most ₹10,000 a day; Note 3: no
                    proportionate deduction (p7).
  Cataract          4.3: 25% of sum insured or ₹40,000, whichever is lower, per eye (p7).
  AYUSH             4.2: up to the sum insured, in an AYUSH hospital (p7).
  Pre / post        4.4 / 4.5: 30 days before admission, 60 days after discharge (p7).
  Waits             6.1 PED 36 months; 6.2 first 30 days, accidents exempt; 6.3
                    listed conditions 24 or 36 months, accidents exempt (p9-10).
  Day care          4.1.1.iv and definition 3.12: treatment under general or local
                    anaesthesia completed in under 24 hours that would otherwise need
                    a longer stay; the 24-hour minimum does not apply (p2, p7).
  Exclusions        Excl08 cosmetic surgery, except reconstruction after an accident;
                    Excl14 supplements not prescribed; Excl15 refractive error under
                    7.5 dioptres (p10-11).
  Non-payables      Annexure A: gloves (List I 56), admission kit (List II 27),
                    registration charges (List IV 1) (p21-23).
  Co-pay            7.III.5: 5% of every claim (p19).

THE POLICY, unless a case says otherwise: period 1 Apr 2025 - 31 Mar 2026, sum
insured ₹3,00,000 (so the room limit is ₹5,000 and the ICU limit ₹10,000), no
cumulative bonus, co-pay 5%, member continuously insured since 1 Apr 2021 (every
wait over by 1 Apr 2024), no pre-existing disease declared.

THE CLAIM, unless a case says otherwise: allopathic, illness, all three
documents submitted and agreeing with each other.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from engine import clauses as C
from engine.schema import Cause, Claim, Hospital, Policy, TreatmentSystem, Verdict
from sampler.products.arogya_sanjeevani import TERMS
from tests.builders import (
    APPENDICECTOMY,
    APPENDICITIS,
    GASTROENTERITIS,
    PNEUMONIA,
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
    protein_supplement,
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
    values = {"sum_insured": 300_000, "copay_bp": 500, "first_inception": dt.date(2021, 4, 1)} | changes
    return build_policy(TERMS, **values)


CATARACT = dx("H25.1", "Senile nuclear cataract")
PHACO = "PX-PHACO"
AYURVEDA_HOSPITAL = Hospital(name="Test Ayurveda Hospital", city="Pune", ayush_hospital=True)


# ---------------------------------------------------------------- room, ICU and cataract limits


@golden
def as01_nursing_takes_the_room_over_the_limit():
    """AS01. Room under the limit on its own, over it with nursing -> PARTIAL

    Pneumonia. Admitted 4 Aug 2025 10:00, discharged 8 Aug 10:00 (4 days).

      Room            4 days x ₹4,600      18,400
      Nursing         4 days x ₹800         3,200
      Consultant      visits                4,000
      Pharmacy                             12,000
      Investigations                        6,000
      Surgical gloves   (non-payable)         400
      Bill total                           44,000

    Working
      Non-payables    gloves 400 off                                        43,600
      Room rent       limit: 2% of 3,00,000 = 6,000, at most 5,000 -> ₹5,000/day.
                      Room, boarding and nursing count together (4.1.i):
                      4,600 + 800 = ₹5,400/day, above ₹5,000, ratio 5,000/5,400 = 25/27.
                      Scaled: room 18,400 + nursing 3,200 + consultant 4,000 = 25,600;
                      25,600 x 2/27 = 1,896.30 -> 1,896 off                  41,704
                      (pharmacy and investigations are not scaled, Note 2)
      Co-pay          5% of 41,704 = 2,085.20 -> 2,085 off                  39,619

    Expected: PARTIAL, ₹39,619, clauses [3.1_room_rent_limit, 5.2_copay, A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-08 10:00",
        diagnosis=PNEUMONIA,
        items=[
            room(4_600, days=4),
            nursing(800, days=4),
            consultant(4_000),
            pharmacy(12_000),
            investigations(6_000),
            gloves(400),
        ],
    )
    return policy(), claim, expect(Verdict.PARTIAL, 39_619, C.ROOM_RENT, C.COPAY, C.NON_PAYABLE)


@golden
def as02_small_sum_insured_room_limit_is_two_percent():
    """AS02. Sum insured ₹1,00,000: the room limit is 2% of it, ₹2,000 a day -> PARTIAL

    Sum insured ₹1,00,000. Acute appendicitis, laparoscopic appendicectomy.
    Admitted 4 Aug 2025 10:00, discharged 7 Aug 10:00 (3 days).

      Room            3 days x ₹2,500       7,500
      Nursing         3 days x ₹500         1,500
      Surgeon                              20,000
      Anaesthetist                          5,000
      OT                                   10,000
      Pharmacy                              6,000
      Investigations                        3,000
      Registration      (non-payable)         300
      Bill total                           53,300

    Working
      Non-payables    registration 300 off                                  53,000
      Room rent       limit: 2% of 1,00,000 = ₹2,000/day (under ₹5,000).
                      2,500 + 500 = ₹3,000/day, ratio 2,000/3,000 = 2/3.
                      Scaled: room 7,500 + nursing 1,500 + surgeon 20,000
                      + anaesthetist 5,000 + OT 10,000 = 44,000;
                      44,000 x 1/3 = 14,666.67 -> 14,667 off                 38,333
      Co-pay          5% of 38,333 = 1,916.65 -> 1,917 off                  36,416
      Sum insured     36,416 is within 1,00,000

    Expected: PARTIAL, ₹36,416, clauses [3.1_room_rent_limit, 5.2_copay, A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=[
            room(2_500, days=3),
            nursing(500, days=3),
            surgeon(20_000),
            anaesthetist(5_000),
            ot(10_000),
            pharmacy(6_000),
            investigations(3_000),
            registration(300),
        ],
    )
    return policy(sum_insured=100_000), claim, expect(Verdict.PARTIAL, 36_416, C.ROOM_RENT, C.COPAY, C.NON_PAYABLE)


@golden
def as03_icu_above_its_limit_no_proportionate_deduction():
    """AS03. ICU above its limit: only the ICU charges are cut -> PARTIAL

    Pneumonia. Admitted 4 Aug 2025 10:00, discharged 9 Aug 10:00 (5 days:
    2 in ICU, 3 on the ward).

      Room            3 days x ₹3,000       9,000
      ICU             2 days x ₹16,000     32,000
      Nursing         3 days x ₹600         1,800
      Consultant      visits                5,000
      Pharmacy                             15,000
      Investigations                       10,000
      Bill total                           72,800

    Working
      Non-payables    none                                                   72,800
      Room rent       3,000 + 600 = ₹3,600/day, within ₹5,000                72,800
      ICU             limit: 5% of 3,00,000 = 15,000, at most 10,000 -> ₹10,000/day.
                      16,000 is above it: the ICU line is paid at 10,000/16,000,
                      32,000 x 3/8 = 12,000 off. Nothing else is scaled (Note 3). 60,800
      Co-pay          5% of 60,800 = 3,040 off                               57,760

    Expected: PARTIAL, ₹57,760, clauses [3.2_icu_limit, 5.2_copay]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-09 10:00",
        diagnosis=PNEUMONIA,
        items=[
            room(3_000, days=3),
            icu(16_000, days=2),
            nursing(600, days=3),
            consultant(5_000),
            pharmacy(15_000),
            investigations(10_000),
        ],
    )
    return policy(), claim, expect(Verdict.PARTIAL, 57_760, C.ICU_LIMIT, C.COPAY)


@golden
def as04_cataract_one_eye_forty_thousand():
    """AS04. Cataract, one eye, as day care: ₹40,000 limit -> PARTIAL

    Senile nuclear cataract, phacoemulsification with lens, one eye.
    Admitted 4 Aug 2025 08:00, discharged 15:00 (7 hours).

      Surgeon                              25,000
      Anaesthetist                          5,000
      OT                                    8,000
      Intraocular lens  1 x ₹20,000        20,000
      Pharmacy                              2,000
      Investigations                        1,500
      Surgical gloves   (non-payable)         300
      Bill total                           61,800

    Working
      Specified wait  cataract: 24 months from 1 Apr 2021, over on 1 Apr 2023
      Minimum stay    7 h is under 24 h, but cataract surgery is day care    -> 2.2_day_care
      Non-payables    gloves 300 off                                         61,500
      Cataract limit  25% of 3,00,000 = 75,000 or 40,000, whichever is lower:
                      ₹40,000 x 1 eye; capped, 21,500 off                    40,000
      Co-pay          5% of 40,000 = 2,000 off                               38,000

    Expected: PARTIAL, ₹38,000, clauses [2.2_day_care, 3.3_disease_sublimit, 5.2_copay, A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 08:00",
        discharged="2025-08-04 15:00",
        diagnosis=CATARACT,
        procedures=[px(PHACO, "Phacoemulsification with IOL")],
        room_category=None,
        items=[
            surgeon(25_000),
            anaesthetist(5_000),
            ot(8_000),
            implant(20_000, "Intraocular lens"),
            pharmacy(2_000),
            investigations(1_500),
            gloves(300),
        ],
    )
    return policy(), claim, expect(
        Verdict.PARTIAL, 38_000, C.DAY_CARE, C.DISEASE_SUBLIMIT, C.COPAY, C.NON_PAYABLE
    )


@golden
def as05_cataract_both_eyes_small_sum_insured():
    """AS05. Cataract, both eyes, sum insured ₹1,00,000: 25% of it per eye -> PARTIAL

    Sum insured ₹1,00,000. Senile nuclear cataract, phacoemulsification, both eyes.
    Admitted 4 Aug 2025 08:00, discharged 17:00 (9 hours).

      Surgeon                              45,000
      Anaesthetist                          9,000
      OT                                   14,000
      Intraocular lens  2 x ₹15,000        30,000
      Pharmacy                              3,000
      Investigations                        2,000
      Bill total                         1,03,000

    Working
      Minimum stay    9 h, cataract surgery is day care                      -> 2.2_day_care
      Cataract limit  25% of 1,00,000 = 25,000, lower than 40,000:
                      ₹25,000 x 2 eyes = 50,000; capped, 53,000 off           50,000
      Co-pay          5% of 50,000 = 2,500 off                               47,500
      Sum insured     47,500 is within 1,00,000

    Expected: PARTIAL, ₹47,500, clauses [2.2_day_care, 3.3_disease_sublimit, 5.2_copay]
    """
    claim = build_claim(
        admitted="2025-08-04 08:00",
        discharged="2025-08-04 17:00",
        diagnosis=CATARACT,
        procedures=[px(PHACO, "Phacoemulsification with IOL, both eyes", units=2)],
        room_category=None,
        items=[
            surgeon(45_000),
            anaesthetist(9_000),
            ot(14_000),
            implant(15_000, "Intraocular lens", qty=2),
            pharmacy(3_000),
            investigations(2_000),
        ],
    )
    return policy(sum_insured=100_000), claim, expect(Verdict.PARTIAL, 47_500, C.DAY_CARE, C.DISEASE_SUBLIMIT, C.COPAY)


# ---------------------------------------------------------------- stay length and day care


@golden
def as06_hernia_repair_as_day_care():
    """AS06. Hernia repair, discharged the same day: day care, payable -> APPROVE

    Inguinal hernia, Lichtenstein mesh repair. Admitted 4 Aug 2025 07:00,
    discharged 19:00 (12 hours).

      Surgeon                              30,000
      Anaesthetist                          7,500
      OT                                   12,000
      Mesh              1 x ₹8,000          8,000
      Pharmacy                              3,000
      Investigations                        2,500
      Admission kit     (non-payable)         600
      Bill total                           63,600

    Working
      Specified wait  hernia: 24 months from 1 Apr 2021, over on 1 Apr 2023
      Minimum stay    12 h is under 24 h, but a hernia repair under anaesthesia
                      is day care treatment (3.12)                           -> 2.2_day_care
      Non-payables    admission kit 600 off                                  63,000
      Co-pay          5% of 63,000 = 3,150 off                               59,850

    Expected: APPROVE, ₹59,850, clauses [2.2_day_care, 5.2_copay, A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 07:00",
        discharged="2025-08-04 19:00",
        diagnosis=dx("K40.9", "Inguinal hernia"),
        procedures=[px("PX-HERNIA-REPAIR", "Lichtenstein mesh hernioplasty")],
        room_category=None,
        items=[
            surgeon(30_000),
            anaesthetist(7_500),
            ot(12_000),
            implant(8_000, "Mesh"),
            pharmacy(3_000),
            investigations(2_500),
            admission_kit(600),
        ],
    )
    return policy(), claim, expect(Verdict.APPROVE, 59_850, C.DAY_CARE, C.COPAY, C.NON_PAYABLE)


@golden
def as07_eighteen_hours_without_a_procedure():
    """AS07. 18 hours for gastroenteritis, no procedure: not hospitalisation -> REJECT

    Acute gastroenteritis, IV fluids. Admitted 4 Aug 2025 10:00, discharged
    5 Aug 04:00 (18 hours).

      Room            1 day x ₹2,000        2,000
      Nursing         1 day x ₹500            500
      Consultant                            1,000
      Pharmacy                              2,500
      Investigations                        2,000
      Bill total                            8,000

    Working
      Minimum stay    18 h is under 24 h. No procedure under anaesthesia, so it is
                      not day care treatment (3.12)                         -> 2.1

    Expected: REJECT, ₹0, clauses [2.1_min_hospitalisation]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-05 04:00",
        diagnosis=GASTROENTERITIS,
        items=[
            room(2_000, days=1),
            nursing(500, days=1),
            consultant(1_000),
            pharmacy(2_500),
            investigations(2_000),
        ],
    )
    return policy(), claim, expect(Verdict.REJECT, 0, C.MIN_HOSPITALISATION)


# ---------------------------------------------------------------- waiting periods


@golden
def as08_knee_replacement_waits_thirty_six_months():
    """AS08. Knee replacement 28 months into cover: the 36-month wait applies -> REJECT

    Member continuously insured since 1 Apr 2023. Primary osteoarthritis of the
    knee, total knee replacement. Admitted 4 Aug 2025 10:00, discharged 9 Aug 10:00.

      Room            5 days x ₹4,000      20,000
      Nursing         5 days x ₹800         4,000
      Surgeon                              80,000
      Anaesthetist                         20,000
      OT                                   40,000
      Knee prosthesis 1 x ₹1,00,000      1,00,000
      Pharmacy                             20,000
      Investigations                       10,000
      Bill total                         2,94,000

    Working
      Specified wait  osteoarthritis of the knee is "Non Infective Arthritis"
                      (24 months, over on 1 Apr 2025), and the claim is also
                      "Treatment for joint replacement" and "Age-related
                      Osteoarthritis" (36 months, over on 1 Apr 2026). The longer
                      wait applies: admitted 4 Aug 2025, inside it           -> 4.2

    Expected: REJECT, ₹0, clauses [4.2_specific_disease_waiting]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-09 10:00",
        diagnosis=dx("M17.1", "Primary osteoarthritis of the knee"),
        procedures=[px("PX-TKR", "Total knee arthroplasty")],
        items=[
            room(4_000, days=5),
            nursing(800, days=5),
            surgeon(80_000),
            anaesthetist(20_000),
            ot(40_000),
            implant(100_000, "Knee prosthesis"),
            pharmacy(20_000),
            investigations(10_000),
        ],
    )
    return policy(first_inception=dt.date(2023, 4, 1)), claim, expect(Verdict.REJECT, 0, C.SPECIFIC_WAITING)


@golden
def as09_hip_replacement_after_a_fall_inside_the_wait():
    """AS09. Hip replacement after a fall, 16 months into cover: accidents are exempt -> APPROVE

    Sum insured ₹5,00,000 (room limit still ₹5,000). Member continuously insured
    since 1 Apr 2024. Fracture of the neck of the femur in a fall; total hip
    replacement. Admitted 4 Aug 2025 10:00, discharged 10 Aug 10:00 (6 days).

      Room            6 days x ₹4,000      24,000
      Nursing         6 days x ₹800         4,800
      Surgeon                              90,000
      Anaesthetist                         20,000
      OT                                   40,000
      Hip prosthesis  1 x ₹1,20,000      1,20,000
      Pharmacy                             25,000
      Investigations                       12,000
      Surgical gloves   (non-payable)         700
      Bill total                         3,36,500

    Working
      Initial wait    30 days from 1 Apr 2024, over
      Specified wait  "Treatment for joint replacement" waits 36 months (over on
                      1 Apr 2027), but the claim arises from an accident, which
                      6.3.a exempts                                  -> 4.2_accident_exception
      Non-payables    gloves 700 off                                      3,35,800
      Room rent       4,000 + 800 = ₹4,800/day, within ₹5,000
      Co-pay          5% of 3,35,800 = 16,790 off                          3,19,010
      Sum insured     3,19,010 is within 5,00,000

    Expected: APPROVE, ₹3,19,010, clauses [4.2_accident_exception, 5.2_copay, A1_non_payable_items]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-10 10:00",
        diagnosis=dx("S72.0", "Fracture of neck of femur"),
        procedures=[px("PX-THR", "Total hip arthroplasty")],
        cause=Cause.ACCIDENT,
        items=[
            room(4_000, days=6),
            nursing(800, days=6),
            surgeon(90_000),
            anaesthetist(20_000),
            ot(40_000),
            implant(120_000, "Hip prosthesis"),
            pharmacy(25_000),
            investigations(12_000),
            gloves(700),
        ],
    )
    return (
        policy(sum_insured=500_000, first_inception=dt.date(2024, 4, 1)),
        claim,
        expect(Verdict.APPROVE, 319_010, C.SPECIFIC_WAITING_ACCIDENT, C.COPAY, C.NON_PAYABLE),
    )


@golden
def as10_illness_in_the_first_thirty_days():
    """AS10. Dengue on day 21 of a new policy -> REJECT

    New policy: first inception 1 Apr 2025. Dengue fever. Admitted 21 Apr 2025
    10:00, discharged 24 Apr 10:00.

      Room            3 days x ₹3,000       9,000
      Nursing         3 days x ₹500         1,500
      Pharmacy                              6,000
      Investigations                        5,000
      Bill total                           21,500

    Working
      Initial wait    30 days from 1 Apr 2025, over on 1 May 2025; admitted 21 Apr,
                      inside; the cause is illness                          -> 4.3

    Expected: REJECT, ₹0, clauses [4.3_initial_waiting]
    """
    claim = build_claim(
        admitted="2025-04-21 10:00",
        discharged="2025-04-24 10:00",
        diagnosis=dx("A90", "Dengue fever"),
        items=[room(3_000, days=3), nursing(500, days=3), pharmacy(6_000), investigations(5_000)],
    )
    return policy(first_inception=dt.date(2025, 4, 1)), claim, expect(Verdict.REJECT, 0, C.INITIAL_WAITING)


@golden
def as11_accident_in_the_first_thirty_days():
    """AS11. Fracture from a road accident on day 11 of a new policy -> APPROVE

    New policy: first inception 1 Apr 2025. Fracture of the shaft of the tibia,
    internal fixation. Admitted 11 Apr 2025 10:00, discharged 15 Apr 10:00.

      Room            4 days x ₹3,500      14,000
      Nursing         4 days x ₹600         2,400
      Surgeon                              45,000
      Anaesthetist                         10,000
      OT                                   20,000
      Nail              1 x ₹25,000        25,000
      Pharmacy                              8,000
      Investigations                        5,000
      Bill total                         1,29,400

    Working
      Initial wait    inside the 30 days, but claims arising from an accident are
                      excepted (6.2.a)                               -> 4.3_accident_exception
      Room rent       3,500 + 600 = ₹4,100/day, within ₹5,000
      Co-pay          5% of 1,29,400 = 6,470 off                          1,22,930

    Expected: APPROVE, ₹1,22,930, clauses [4.3_accident_exception, 5.2_copay]
    """
    claim = build_claim(
        admitted="2025-04-11 10:00",
        discharged="2025-04-15 10:00",
        diagnosis=dx("S82.2", "Fracture of shaft of tibia"),
        procedures=[px("PX-ORIF-TIBIA", "Intramedullary nailing of the tibia")],
        cause=Cause.ACCIDENT,
        items=[
            room(3_500, days=4),
            nursing(600, days=4),
            surgeon(45_000),
            anaesthetist(10_000),
            ot(20_000),
            implant(25_000, "Intramedullary nail"),
            pharmacy(8_000),
            investigations(5_000),
        ],
    )
    return (
        policy(first_inception=dt.date(2025, 4, 1)),
        claim,
        expect(Verdict.APPROVE, 122_930, C.INITIAL_WAITING_ACCIDENT, C.COPAY),
    )


@golden
def as12_declared_diabetes_inside_thirty_six_months():
    """AS12. Diabetic foot 28 months into cover, diabetes declared -> REJECT

    Member continuously insured since 1 Apr 2023; declared type 2 diabetes
    mellitus (E11). Type 2 diabetes with foot ulcer. Admitted 4 Aug 2025 10:00,
    discharged 9 Aug 10:00.

      Room            5 days x ₹3,000      15,000
      Nursing         5 days x ₹500         2,500
      Pharmacy                             20,000
      Investigations                        9,000
      Bill total                           46,500

    Working
      PED wait        E11.5 is a direct complication of declared diabetes; 36 months
                      from 1 Apr 2023, over on 1 Apr 2026; admitted 4 Aug 2025,
                      inside                                                -> 4.1

    Expected: REJECT, ₹0, clauses [4.1_ped_waiting]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-09 10:00",
        diagnosis=dx("E11.5", "Type 2 diabetes mellitus with foot ulcer"),
        items=[room(3_000, days=5), nursing(500, days=5), pharmacy(20_000), investigations(9_000)],
    )
    return (
        policy(first_inception=dt.date(2023, 4, 1), declared_peds=[ped("Type 2 diabetes mellitus", "E11")]),
        claim,
        expect(Verdict.REJECT, 0, C.PED_WAITING),
    )


@golden
def as19_declared_diabetes_after_thirty_six_months():
    """AS19. Diabetic foot 40 months into cover, diabetes declared: the wait is over -> APPROVE

    Member continuously insured since 1 Apr 2022; declared type 2 diabetes
    mellitus (E11). Type 2 diabetes with foot ulcer. Admitted 4 Aug 2025 10:00,
    discharged 9 Aug 10:00. The same bill as AS12.

      Room            5 days x ₹3,000      15,000
      Nursing         5 days x ₹500         2,500
      Pharmacy                             20,000
      Investigations                        9,000
      Bill total                           46,500

    Working
      PED wait        36 months from 1 Apr 2022, over on 1 Apr 2025; admitted
                      4 Aug 2025, after it: covered. (The 48-month wait of the
                      wording's earlier version would have run to 1 Apr 2026.)
      Room rent       3,000 + 500 = ₹3,500/day, within ₹5,000
      Co-pay          5% of 46,500 = 2,325 off                               44,175

    Expected: APPROVE, ₹44,175, clauses [5.2_copay]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-09 10:00",
        diagnosis=dx("E11.5", "Type 2 diabetes mellitus with foot ulcer"),
        items=[room(3_000, days=5), nursing(500, days=5), pharmacy(20_000), investigations(9_000)],
    )
    return (
        policy(first_inception=dt.date(2022, 4, 1), declared_peds=[ped("Type 2 diabetes mellitus", "E11")]),
        claim,
        expect(Verdict.APPROVE, 44_175, C.COPAY),
    )


# ---------------------------------------------------------------- AYUSH


def _ayurveda_claim(hospital: Hospital) -> Claim:
    return build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-14 10:00",
        diagnosis=dx("M06.9", "Rheumatoid arthritis"),
        treatment_system=TreatmentSystem.AYURVEDA,
        hospital=hospital,
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


@golden
def as13_ayurveda_in_an_ayush_hospital():
    """AS13. Ayurveda in an AYUSH hospital: covered up to the sum insured -> APPROVE

    Rheumatoid arthritis, Ayurvedic treatment at an AYUSH hospital.
    Admitted 4 Aug 2025 10:00, discharged 14 Aug 10:00 (10 days).

      Room            10 days x ₹2,000     20,000
      Nursing         10 days x ₹300        3,000
      Consultant                            6,000
      Panchakarma therapy                  15,000
      Pharmacy                              5,000
      Investigations                        1,500
      Registration      (non-payable)         300
      Bill total                           50,800

    Working
      Specified wait  rheumatoid arthritis is listed (24 months), over on 1 Apr 2023
      AYUSH           covered in an AYUSH hospital, with no limit of its own (4.2)
      Non-payables    registration 300 off                                   50,500
      Room rent       2,000 + 300 = ₹2,300/day, within ₹5,000
      Co-pay          5% of 50,500 = 2,525 off                               47,975

    Expected: APPROVE, ₹47,975, clauses [5.2_copay, A1_non_payable_items]
    """
    return policy(), _ayurveda_claim(AYURVEDA_HOSPITAL), expect(Verdict.APPROVE, 47_975, C.COPAY, C.NON_PAYABLE)


@golden
def as14_ayurveda_in_an_ordinary_hospital():
    """AS14. The same Ayurvedic treatment in a hospital that is not an AYUSH hospital -> REJECT

    As AS13, at Test Hospital, which does not qualify as an AYUSH hospital
    (definition 3.4).

    Working
      AYUSH           covered only "in any AYUSH Hospital" (4.2)            -> 3.4

    Expected: REJECT, ₹0, clauses [3.4_ayush]
    """
    ordinary = Hospital(name="Test Hospital", city="Pune")
    return policy(), _ayurveda_claim(ordinary), expect(Verdict.REJECT, 0, C.AYUSH)


# ---------------------------------------------------------------- bills


@golden
def as15_pre_hospitalisation_bill_outside_thirty_days():
    """AS15. A consultation 31 days before admission is outside the window -> PARTIAL

    Acute appendicitis, laparoscopic appendicectomy. Admitted 4 Aug 2025 10:00,
    discharged 7 Aug 10:00.

      Consultation  (pre, 4 Jul 2025)       1,000
      Tests         (pre, 20 Jul 2025)      3,000
      Room            3 days x ₹3,000       9,000
      Nursing         3 days x ₹500         1,500
      Surgeon                              25,000
      Anaesthetist                          6,000
      OT                                   10,000
      Pharmacy                              5,000
      Investigations                        3,000
      Follow-up     (post, 30 Sep 2025)       800
      Medicines     (post, 5 Oct 2025)      1,200
      Bill total                           65,500

    Working
      Pre-hospitalisation   30 days before 4 Aug: 5 Jul to 4 Aug. The 4 Jul
                            consultation is 31 days before, outside: 1,000 off.
                            The 20 Jul tests are inside                     64,500
      Post-hospitalisation  60 days after 7 Aug: to 6 Oct. Both inside
      Room rent             3,000 + 500 = ₹3,500/day, within ₹5,000
      Co-pay                5% of 64,500 = 3,225 off                       61,275

    Expected: PARTIAL, ₹61,275, clauses [3.5_pre_hospitalisation, 5.2_copay]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=[
            pre(consultant(1_000, "Consultation"), on="2025-07-04"),
            pre(investigations(3_000, "Tests"), on="2025-07-20"),
            room(3_000, days=3),
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
    return policy(), claim, expect(Verdict.PARTIAL, 61_275, C.PRE_HOSPITALISATION, C.COPAY)


@golden
def as16_supplement_not_prescribed():
    """AS16. An over-the-counter protein supplement is excluded -> PARTIAL

    Pneumonia. Admitted 4 Aug 2025 10:00, discharged 7 Aug 10:00.

      Room            3 days x ₹3,000       9,000
      Nursing         3 days x ₹500         1,500
      Consultant                            3,000
      Pharmacy                              8,000
      Investigations                        4,000
      Protein supplement (not prescribed)   1,500
      Bill total                           27,000

    Working
      Excl14          supplements bought without a prescription, 1,500 off   25,500
      Room rent       3,000 + 500 = ₹3,500/day, within ₹5,000
      Co-pay          5% of 25,500 = 1,275 off                               24,225

    Expected: PARTIAL, ₹24,225, clauses [4.14_dietary_supplements, 5.2_copay]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=PNEUMONIA,
        items=[
            room(3_000, days=3),
            nursing(500, days=3),
            consultant(3_000),
            pharmacy(8_000),
            investigations(4_000),
            protein_supplement(1_500),
        ],
    )
    return policy(), claim, expect(Verdict.PARTIAL, 24_225, C.DIETARY_SUPPLEMENTS, C.COPAY)


# ---------------------------------------------------------------- exclusions


@golden
def as17_lasik_for_low_myopia():
    """AS17. LASIK for -4.5 dioptres, 4 hours: excluded, and not hospitalisation -> REJECT

    Myopia of -4.5 dioptres, both eyes; LASIK. Admitted 4 Aug 2025 09:00,
    discharged 13:00 (4 hours).

      Surgeon                              30,000
      OT                                    6,000
      Pharmacy                              1,000
      Bill total                           37,000

    Working
      Excl15          correction of refractive error under 7.5 dioptres     -> 4.15
      Minimum stay    4 h is under 24 h, and LASIK is not day care: it never
                      needed a stay of more than 24 hours (3.12)             -> 2.1
      Both grounds count.

    Expected: REJECT, ₹0, clauses [2.1_min_hospitalisation, 4.15_refractive_error]
    """
    claim = build_claim(
        admitted="2025-08-04 09:00",
        discharged="2025-08-04 13:00",
        diagnosis=dx("H52.1", "Myopia, -4.5 dioptres"),
        procedures=[px("PX-LASIK", "LASIK")],
        room_category=None,
        items=[surgeon(30_000), ot(6_000), pharmacy(1_000)],
    )
    return policy(), claim, expect(Verdict.REJECT, 0, C.MIN_HOSPITALISATION, C.REFRACTIVE_ERROR)


@golden
def as18_nose_reconstruction_after_an_accident():
    """AS18. Nose reconstruction after a road accident: not cosmetic -> APPROVE

    Fracture of the nasal bones in a road accident; reconstructive
    septorhinoplasty. Admitted 4 Aug 2025 10:00, discharged 6 Aug 10:00.

      Room            2 days x ₹3,500       7,000
      Nursing         2 days x ₹600         1,200
      Surgeon                              50,000
      Anaesthetist                         12,000
      OT                                   20,000
      Pharmacy                              4,000
      Investigations                        3,000
      Bill total                           97,200

    Working
      Excl08          cosmetic surgery is excluded "unless for reconstruction
                      following an Accident"; 4.1.1.iii covers plastic surgery
                      necessitated by injury: not excluded
      Room rent       3,500 + 600 = ₹4,100/day, within ₹5,000
      Co-pay          5% of 97,200 = 4,860 off                               92,340

    Expected: APPROVE, ₹92,340, clauses [5.2_copay]
    """
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-06 10:00",
        diagnosis=dx("S02.2", "Fracture of nasal bones"),
        procedures=[px("PX-RHINOPLASTY-RECONSTRUCTIVE", "Post-traumatic septorhinoplasty")],
        cause=Cause.ACCIDENT,
        items=[
            room(3_500, days=2),
            nursing(600, days=2),
            surgeon(50_000),
            anaesthetist(12_000),
            ot(20_000),
            pharmacy(4_000),
            investigations(3_000),
        ],
    )
    return policy(), claim, expect(Verdict.APPROVE, 92_340, C.COPAY)
