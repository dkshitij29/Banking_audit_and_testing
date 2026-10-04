"""Golden cases: claims worked out by hand, with answers a person has checked.

These are the only labels a human writes. They exist to prove the engine is
right, so each must be checked by hand, independently of the engine code. The
docstring above each case gives its inputs and working; the code must say the
same thing.

THE TEST PRODUCT used by every case below. Its numbers are made up, like the
placeholders: judge whether each rule is applied correctly for these numbers,
not whether the numbers are realistic. It is separate from the placeholder
product in engine/tables.py, so replacing the placeholders never moves a case.

  Initial waiting period   100 days from first inception; accidents exempt
  Specified diseases       18 months from first inception; accidents exempt.
                           Cataract (H25, H26 or PX-PHACO), hernia (K40-K46 or
                           PX-HERNIA-REPAIR), joint replacement (PX-THR, PX-TKR)
  Pre-existing diseases    30 months from first inception, for what the member
                           declared; no accident exemption
  Permanent exclusions     cosmetic surgery (PX-COSMETIC-RHINOPLASTY),
                           refractive error (H52 or PX-LASIK)
  AYUSH                    covered in an AYUSH hospital only, up to ₹25,000 a claim
  Pre-hospitalisation      bills from up to 45 days before the admission date
  Post-hospitalisation     bills from up to 90 days after the discharge date
  Required documents       claim form, discharge summary, hospital bill
  Minimum stay             24 hours, unless a procedure is on the day-care list
  Day-care list            PX-PHACO (cataract surgery)
  Non-payable items (A1)   surgical gloves, admission kit, registration charges
  Excluded items (4.14)    protein supplement
  Room rent cap            ₹5,000 per day
  Scaled with room rent    nursing, surgeon, anaesthetist, consultant, OT
  ICU cap                  ₹8,000 per day; nothing else is scaled with it
  Sub-limit                cataract, ₹45,000 per eye
  Pharmacy, investigations and implants are never scaled.

Diagnoses match by ICD-10 code: a listed H25 matches a claim coded H25.1.

THE POLICY, unless a case says otherwise: period 1 Apr 2025 - 31 Mar 2026,
sum insured ₹5,00,000, no cumulative bonus, no deductible, no co-pay, member
continuously insured since 1 Apr 2022 (so every waiting period is long over)
and has declared no pre-existing disease.

THE CLAIM, unless a case says otherwise: allopathic treatment; every bill line
is from the hospital stay; all three documents are submitted, and the claim
form agrees with the hospital (it claims the bill total, with the same dates).

Each case's working lists the checks that matter for it. Checks that plainly
do not apply (a pneumonia claim against the cataract sub-limit) are left out.

Amounts use Indian grouping in the working (₹1,05,000) and Python's in code
(105_000).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from engine import clauses as C
from engine.schema import (
    ALL_DOCUMENTS,
    Ayush,
    BillCategory,
    Cap,
    Cause,
    Claim,
    ConditionGroup,
    DocType,
    Exclusion,
    Hospital,
    LineExclusion,
    Match,
    Policy,
    ProductTerms,
    SpecificWait,
    Sublimit,
    TreatmentSystem,
    Verdict,
    Wait,
)
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
    days,
    dx,
    gloves,
    icu,
    implant,
    investigations,
    months,
    nursing,
    ot,
    ped,
    pharmacy,
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

CATARACT = Match(icd10_prefixes=("H25", "H26"), procedure_codes=("PX-PHACO",))

TEST_PRODUCT = ProductTerms(
    product_id="GOLDEN-TEST",
    source="TEST-ONLY",
    initial_wait=Wait(duration=days(100), accident_exempt=True),
    specific_wait=SpecificWait(
        groups=(
            ConditionGroup(name="Cataract", match=CATARACT, duration=months(18)),
            ConditionGroup(
                name="Hernia",
                match=Match(
                    icd10_prefixes=("K40", "K41", "K42", "K43", "K44", "K45", "K46"),
                    procedure_codes=("PX-HERNIA-REPAIR",),
                ),
                duration=months(18),
            ),
            ConditionGroup(
                name="Joint replacement",
                match=Match(procedure_codes=("PX-THR", "PX-TKR")),
                duration=months(18),
            ),
        ),
        accident_exempt=True,
    ),
    ped_wait=months(30),
    exclusions=(
        Exclusion(clause_id=C.COSMETIC, match=Match(procedure_codes=("PX-COSMETIC-RHINOPLASTY",))),
        Exclusion(
            clause_id=C.REFRACTIVE_ERROR,
            match=Match(icd10_prefixes=("H52",), procedure_codes=("PX-LASIK",)),
        ),
    ),
    ayush=Ayush(covered=True, requires_ayush_hospital=True, cap=Cap(rupees=25_000)),
    min_stay_hours=24,
    day_care_procedures=("PX-PHACO",),
    required_documents=ALL_DOCUMENTS,
    pre_hospitalisation_days=45,
    post_hospitalisation_days=90,
    line_exclusions=(
        LineExclusion(
            clause_id=C.NON_PAYABLE,
            item_codes=("NP-GLOVES", "NP-ADMISSION-KIT", "NP-REGISTRATION"),
        ),
        LineExclusion(clause_id=C.DIETARY_SUPPLEMENTS, item_codes=("EX-PROTEIN-SUPPLEMENT",)),
    ),
    room_cap=Cap(rupees=5_000),
    room_rate_includes=(),
    room_associated=(
        BillCategory.NURSING,
        BillCategory.SURGEON,
        BillCategory.ANAESTHETIST,
        BillCategory.CONSULTANT,
        BillCategory.OT,
    ),
    icu_cap=Cap(rupees=8_000),
    icu_associated=(),
    sublimits=(Sublimit(name="Cataract, per eye", match=CATARACT, cap_per_unit=Cap(rupees=45_000)),),
)

NEW_POLICY_START = dt.date(2025, 4, 1)
"""First inception for cases about the initial wait: the policy is brand new."""


@dataclass(frozen=True)
class Expected:
    verdict: Verdict
    payable: int
    clauses: tuple[str, ...]


@dataclass(frozen=True)
class GoldenCase:
    name: str
    policy: Policy
    claim: Claim
    expected: Expected


GOLDEN: list[Callable[[], GoldenCase]] = []


def golden(build: Callable[[], tuple[Policy, Claim, Expected]]) -> Callable[[], GoldenCase]:
    def case() -> GoldenCase:
        policy, claim, expected = build()
        return GoldenCase(build.__name__, policy, claim, expected)

    case.__name__ = build.__name__
    case.__doc__ = build.__doc__
    GOLDEN.append(case)
    return case


def expect(verdict: Verdict, payable: int, *clauses: str) -> Expected:
    return Expected(verdict, payable, tuple(sorted(clauses)))


# ---------------------------------------------------------------- amounts


@golden
def g01_only_non_payables_removed():
    """G01. Only non-payable items are removed -> APPROVE

    Acute appendicitis, laparoscopic appendicectomy.
    Admitted 4 Aug 2025 10:00, discharged 7 Aug 10:00 (72 h).

      Room            3 days x ₹4,000      12,000
      Nursing         3 days x ₹500         1,500
      Surgeon                              25,000
      Anaesthetist                          6,000
      OT                                   10,000
      Pharmacy                              6,000
      Investigations                        4,000
      Surgical gloves   (non-payable)         500
      Admission kit     (non-payable)       1,000
      Registration      (non-payable)         200
      Bill total                           66,200

    Working
      Non-payables    500 + 1,000 + 200 = 1,700 off          64,500
      Room rent       ₹4,000/day is within the ₹5,000 cap    64,500
      Sum insured     64,500 is within 5,00,000              64,500

    Expected: APPROVE, ₹64,500, clauses [A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=[
            room(4_000, days=3),
            nursing(500, days=3),
            surgeon(25_000),
            anaesthetist(6_000),
            ot(10_000),
            pharmacy(6_000),
            investigations(4_000),
            gloves(500),
            admission_kit(1_000),
            registration(200),
        ],
    )
    return policy, claim, expect(Verdict.APPROVE, 64_500, C.NON_PAYABLE)


@golden
def g02_room_above_cap():
    """G02. Room above the cap: proportionate deduction -> PARTIAL

    Acute appendicitis, laparoscopic appendicectomy.
    Admitted 4 Aug 2025 10:00, discharged 8 Aug 10:00 (96 h).

      Room            4 days x ₹8,000      32,000
      Nursing         4 days x ₹1,000       4,000
      Surgeon                              40,000
      Anaesthetist                          8,000
      OT                                   16,000
      Pharmacy                             20,000
      Investigations                       10,000
      Surgical gloves   (non-payable)         500
      Bill total                         1,30,500

    Working
      Non-payables    500 off                                           1,30,000
      Room rent       ₹8,000/day is above the ₹5,000 cap, so the room
                      line and associated charges are paid at 5,000/8,000 = 5/8.
                      Room + nursing + surgeon + anaesthetist + OT
                      = 32,000 + 4,000 + 40,000 + 8,000 + 16,000 = 1,00,000
                      paid at 5/8 = 62,500, so 37,500 off                 92,500
                      (pharmacy and investigations are not scaled)
      Sum insured     92,500 is within 5,00,000                            92,500

    Expected: PARTIAL, ₹92,500, clauses [3.1_room_rent_limit, A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-08 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=[
            room(8_000, days=4),
            nursing(1_000, days=4),
            surgeon(40_000),
            anaesthetist(8_000),
            ot(16_000),
            pharmacy(20_000),
            investigations(10_000),
            gloves(500),
        ],
    )
    return policy, claim, expect(Verdict.PARTIAL, 92_500, C.ROOM_RENT, C.NON_PAYABLE)


@golden
def g03_copay_only():
    """G03. Co-pay is the only reduction -> APPROVE (co-pay is cost sharing)

    Policy has a 20% co-pay.
    Pneumonia. Admitted 1 Sep 2025 09:00, discharged 4 Sep 09:00 (72 h).

      Room            3 days x ₹3,000       9,000
      Nursing         3 days x ₹500         1,500
      Consultant                            4,500
      Pharmacy                             12,000
      Investigations                        8,000
      Registration      (non-payable)         200
      Bill total                           35,200

    Working
      Non-payables    200 off                                35,000
      Room rent       ₹3,000/day is within the ₹5,000 cap    35,000
      Co-pay          20% of 35,000 = 7,000 off              28,000
      Sum insured     28,000 is within 5,00,000              28,000

    Expected: APPROVE, ₹28,000, clauses [5.2_copay, A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT, copay_bp=2_000)
    claim = build_claim(
        admitted="2025-09-01 09:00",
        discharged="2025-09-04 09:00",
        diagnosis=PNEUMONIA,
        items=[
            room(3_000, days=3),
            nursing(500, days=3),
            consultant(4_500),
            pharmacy(12_000),
            investigations(8_000),
            registration(200),
        ],
    )
    return policy, claim, expect(Verdict.APPROVE, 28_000, C.COPAY, C.NON_PAYABLE)


@golden
def g04_room_above_cap_then_copay():
    """G04. Room above the cap, then co-pay -> PARTIAL (locks room rent before co-pay)

    Policy has a 10% co-pay.
    Acute appendicitis, laparoscopic appendicectomy.
    Admitted 4 Aug 2025 10:00, discharged 7 Aug 10:00 (72 h).

      Room            3 days x ₹8,000      24,000
      Surgeon                              40,000
      OT                                   16,000
      Pharmacy                             20,000
      Surgical gloves   (non-payable)         500
      Bill total                         1,00,500

    Working
      Non-payables    500 off                                          1,00,000
      Room rent       above the cap, paid at 5/8:
                      room + surgeon + OT = 24,000 + 40,000 + 16,000 = 80,000
                      paid at 5/8 = 50,000, so 30,000 off                70,000
      Co-pay          10% of 70,000 = 7,000 off                           63,000
      Sum insured     within 5,00,000                                     63,000

    Expected: PARTIAL, ₹63,000, clauses [3.1_room_rent_limit, 5.2_copay, A1_non_payable_items]

    With co-pay before room rent it would be 1,00,000 - 10,000 - 30,000 = 60,000.
    """
    policy = build_policy(TEST_PRODUCT, copay_bp=1_000)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=[room(8_000, days=3), surgeon(40_000), ot(16_000), pharmacy(20_000), gloves(500)],
    )
    return policy, claim, expect(Verdict.PARTIAL, 63_000, C.ROOM_RENT, C.COPAY, C.NON_PAYABLE)


@golden
def g05_copay_then_sum_insured():
    """G05. Co-pay, then the sum insured cap -> PARTIAL (locks co-pay before the cap)

    Policy has a 10% co-pay; sum insured ₹5,00,000.
    Coronary artery disease, bypass surgery.
    Admitted 1 Oct 2025 08:00, discharged 11 Oct 08:00 (240 h).

      Room            10 days x ₹5,000     50,000
      Surgeon                            2,50,000
      OT                                 1,00,000
      Pharmacy                           1,00,000
      Investigations                     1,00,000
      Bill total                         6,00,000

    Working
      Non-payables    none                                      6,00,000
      Room rent       ₹5,000/day is exactly the cap: no cut      6,00,000
      Co-pay          10% of 6,00,000 = 60,000 off              5,40,000
      Sum insured     5,40,000 is above 5,00,000: capped        5,00,000

    Expected: PARTIAL, ₹5,00,000, clauses [5.2_copay, 5.3_sum_insured]

    With the cap before co-pay it would be 5,00,000 - 50,000 = 4,50,000.
    """
    policy = build_policy(TEST_PRODUCT, copay_bp=1_000)
    claim = build_claim(
        admitted="2025-10-01 08:00",
        discharged="2025-10-11 08:00",
        diagnosis=dx("I25.1", "Atherosclerotic heart disease"),
        procedures=[px("PX-CABG", "Coronary artery bypass grafting")],
        items=[
            room(5_000, days=10),
            surgeon(250_000),
            ot(100_000),
            pharmacy(100_000),
            investigations(100_000),
        ],
    )
    return policy, claim, expect(Verdict.PARTIAL, 500_000, C.COPAY, C.SUM_INSURED)


@golden
def g06_cumulative_bonus_raises_the_limit():
    """G06. The cumulative bonus raises the limit -> PARTIAL

    Sum insured ₹3,00,000 plus ₹60,000 cumulative bonus: limit ₹3,60,000.
    Coronary artery disease, bypass surgery.
    Admitted 1 Oct 2025 08:00, discharged 9 Oct 08:00 (192 h).

      Room            8 days x ₹4,000      32,000
      Surgeon                            1,80,000
      OT                                   60,000
      Pharmacy                             78,000
      Investigations                       50,000
      Bill total                         4,00,000

    Working
      Non-payables    none                                      4,00,000
      Room rent       ₹4,000/day is within the cap              4,00,000
      Sum insured     4,00,000 is above 3,00,000 + 60,000:
                      capped at 3,60,000                        3,60,000

    Expected: PARTIAL, ₹3,60,000, clauses [5.3_sum_insured]
    (Without the bonus it would be 3,00,000.)
    """
    policy = build_policy(TEST_PRODUCT, sum_insured=300_000, cumulative_bonus=60_000)
    claim = build_claim(
        admitted="2025-10-01 08:00",
        discharged="2025-10-09 08:00",
        diagnosis=dx("I25.1", "Atherosclerotic heart disease"),
        procedures=[px("PX-CABG", "Coronary artery bypass grafting")],
        items=[
            room(4_000, days=8),
            surgeon(180_000),
            ot(60_000),
            pharmacy(78_000),
            investigations(50_000),
        ],
    )
    return policy, claim, expect(Verdict.PARTIAL, 360_000, C.SUM_INSURED)


@golden
def g07_excluded_item_on_the_bill():
    """G07. An excluded item on an otherwise covered bill (partial exclusion) -> PARTIAL

    Pneumonia. Admitted 10 Nov 2025 09:00, discharged 15 Nov 09:00 (120 h).

      Room            5 days x ₹3,000      15,000
      Consultant                            7,500
      Pharmacy                             18,000
      Protein supplement  (excluded)        2,400
      Investigations                        9,000
      Surgical gloves     (non-payable)       600
      Bill total                           52,500

    Working
      Non-payables    600 off                                51,900
      Excluded items  protein supplement, 2,400 off          49,500
      Room rent       ₹3,000/day is within the cap           49,500
      Sum insured     within 5,00,000                        49,500

    Expected: PARTIAL, ₹49,500, clauses [4.14_dietary_supplements, A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-11-10 09:00",
        discharged="2025-11-15 09:00",
        diagnosis=PNEUMONIA,
        items=[
            room(3_000, days=5),
            consultant(7_500),
            pharmacy(18_000),
            protein_supplement(2_400),
            investigations(9_000),
            gloves(600),
        ],
    )
    return policy, claim, expect(Verdict.PARTIAL, 49_500, C.DIETARY_SUPPLEMENTS, C.NON_PAYABLE)


@golden
def g08_copay_rounding():
    """G08. Co-pay rounding: the deduction is rounded, halves up -> APPROVE

    Policy has a 10% co-pay.
    Gastroenteritis. Admitted 1 Dec 2025 10:00, discharged 3 Dec 10:00 (48 h).

      Room            2 days x ₹2,500       5,000
      Consultant                            3,000
      Pharmacy                              2,845
      Investigations                        1,500
      Bill total                           12,345

    Working
      Non-payables    none                                   12,345
      Room rent       ₹2,500/day is within the cap           12,345
      Co-pay          10% of 12,345 = 1,234.50, rounded
                      up to 1,235 off                        11,110
      Sum insured     within 5,00,000                        11,110

    Expected: APPROVE, ₹11,110, clauses [5.2_copay]
    (Rounding the remaining 11,110.50 instead of the deduction would give 11,111.)
    """
    policy = build_policy(TEST_PRODUCT, copay_bp=1_000)
    claim = build_claim(
        admitted="2025-12-01 10:00",
        discharged="2025-12-03 10:00",
        diagnosis=GASTROENTERITIS,
        items=[room(2_500, days=2), consultant(3_000), pharmacy(2_845), investigations(1_500)],
    )
    return policy, claim, expect(Verdict.APPROVE, 11_110, C.COPAY)


@golden
def g09_room_cap_as_percent_of_sum_insured():
    """G09. Room cap set as 1% of sum insured, with a half-rupee deduction -> PARTIAL

    Sum insured ₹3,50,000; room cap 1% of sum insured = ₹3,500 per day.
    Acute appendicitis, laparoscopic appendicectomy.
    Admitted 4 Aug 2025 10:00, discharged 7 Aug 10:00 (72 h).

      Room            3 days x ₹4,200      12,600
      Surgeon                              30,000
      OT                                    9,003
      Pharmacy                              5,000
      Bill total                           56,603

    (OT is ₹9,003 so that the deduction lands on exactly half a rupee.)

    Working
      Non-payables    none                                              56,603
      Room rent       ₹4,200/day is above ₹3,500, paid at 3,500/4,200 = 5/6.
                      Room + surgeon + OT = 12,600 + 30,000 + 9,003 = 51,603
                      1/6 of 51,603 = 8,600.50, rounded up to 8,601 off  48,002
      Sum insured     within 3,50,000                                   48,002

    Expected: PARTIAL, ₹48,002, clauses [3.1_room_rent_limit]
    """
    policy = build_policy(replace(TEST_PRODUCT, room_cap=Cap(bp_of_si=100)), sum_insured=350_000)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=[room(4_200, days=3), surgeon(30_000), ot(9_003), pharmacy(5_000)],
    )
    return policy, claim, expect(Verdict.PARTIAL, 48_002, C.ROOM_RENT)


# ---------------------------------------------------------------- gates


@golden
def g10_admitted_after_policy_ended():
    """G10. Admitted after the policy ended -> REJECT, and no other gate is checked

    Policy period 1 Apr 2025 - 31 Mar 2026.
    Gastroenteritis. Admitted 2 Apr 2026 09:00, discharged 2 Apr 19:00 (10 h).

      Room            1 day x ₹3,000        3,000
      Consultant                            2,000
      Pharmacy                              1,500
      Bill total                            6,500

    Working
      Policy period   2 Apr 2026 is after 31 Mar 2026: rejected. The 10-hour stay
                      would also fail the minimum stay, but once the policy is not
                      in force no other gate is checked.

    Expected: REJECT, ₹0, clauses [6.1_policy_period]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2026-04-02 09:00",
        discharged="2026-04-02 19:00",
        diagnosis=GASTROENTERITIS,
        items=[room(3_000, days=1), consultant(2_000), pharmacy(1_500)],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.POLICY_PERIOD)


@golden
def g11_illness_on_last_day_of_initial_wait():
    """G11. Illness on the last day of the initial wait -> REJECT

    New policy: first inception 1 Apr 2025.
    Pneumonia. Admitted 9 Jul 2025 09:00, discharged 12 Jul 09:00 (72 h).

      Room            3 days x ₹3,000       9,000
      Consultant                            4,500
      Pharmacy                             12,000
      Investigations                        8,000
      Bill total                           33,500

    Working
      Policy period   within
      Initial wait    100 days from 1 Apr 2025 are 1 Apr to 9 Jul (the wait is
                      over on 10 Jul). 9 Jul is day 100: inside. Illness: rejected.
      Minimum stay    72 h meets 24 h

    Expected: REJECT, ₹0, clauses [4.3_initial_waiting]
    """
    policy = build_policy(TEST_PRODUCT, first_inception=NEW_POLICY_START)
    claim = build_claim(
        admitted="2025-07-09 09:00",
        discharged="2025-07-12 09:00",
        diagnosis=PNEUMONIA,
        items=[room(3_000, days=3), consultant(4_500), pharmacy(12_000), investigations(8_000)],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.INITIAL_WAITING)


@golden
def g12_accident_inside_initial_wait():
    """G12. Accident inside the initial wait: the exception applies -> APPROVE

    New policy: first inception 1 Apr 2025.
    Road accident: fracture of the shaft of the tibia, open reduction and internal fixation.
    Admitted 15 May 2025 14:00, discharged 18 May 14:00 (72 h).

      Room            3 days x ₹4,000      12,000
      Surgeon                              35,000
      Anaesthetist                          7,000
      OT                                   12,000
      Implant (plate and screws)           25,000
      Pharmacy                              8,000
      Investigations                        6,000
      Surgical gloves   (non-payable)         500
      Bill total                         1,05,500

    Working
      Policy period   within
      Initial wait    15 May is inside the wait (over on 10 Jul), but the cause
                      is an accident, which the wait does not apply to
      Minimum stay    72 h meets 24 h
      Non-payables    500 off                                1,05,000
      Room rent       ₹4,000/day is within the cap           1,05,000
      Sum insured     within 5,00,000                        1,05,000

    Expected: APPROVE, ₹1,05,000, clauses [4.3_accident_exception, A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT, first_inception=NEW_POLICY_START)
    claim = build_claim(
        admitted="2025-05-15 14:00",
        discharged="2025-05-18 14:00",
        cause=Cause.ACCIDENT,
        diagnosis=dx("S82.2", "Fracture of shaft of tibia"),
        procedures=[px("PX-ORIF-TIBIA", "Open reduction and internal fixation of tibia")],
        items=[
            room(4_000, days=3),
            surgeon(35_000),
            anaesthetist(7_000),
            ot(12_000),
            implant(25_000, "Implant: plate and screws"),
            pharmacy(8_000),
            investigations(6_000),
            gloves(500),
        ],
    )
    return policy, claim, expect(Verdict.APPROVE, 105_000, C.INITIAL_WAITING_ACCIDENT, C.NON_PAYABLE)


@golden
def g13_day_care_cataract():
    """G13. Day-care trap: 6-hour cataract surgery -> APPROVE

    Senile nuclear cataract, phacoemulsification with lens implant (PX-PHACO).
    Admitted 12 Sep 2025 08:30, discharged 12 Sep 14:30 (6 h). No room charged.

      Surgeon                              18,000
      OT                                    7,000
      Implant (intraocular lens)           12,000
      Pharmacy                              2,500
      Investigations                        1,500
      Admission kit     (non-payable)       1,000
      Bill total                           42,000

    Working
      Policy period   within
      Initial wait    long over
      Specified wait  cataract is listed, but 18 months from 1 Apr 2022
                      were over on 1 Oct 2023
      Minimum stay    6 h is under 24 h, but PX-PHACO is on the day-care list
      Non-payables    1,000 off                              41,000
      Room rent       no room line: not checked              41,000
      Sub-limit       cataract, ₹45,000 for one eye;
                      41,000 is within it                    41,000
      Sum insured     within 5,00,000                        41,000

    Expected: APPROVE, ₹41,000, clauses [2.2_day_care, A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-09-12 08:30",
        discharged="2025-09-12 14:30",
        diagnosis=dx("H25.1", "Senile nuclear cataract"),
        procedures=[px("PX-PHACO", "Phacoemulsification with intraocular lens implant")],
        room_category=None,
        items=[
            surgeon(18_000),
            ot(7_000),
            implant(12_000, "Implant: intraocular lens"),
            pharmacy(2_500),
            investigations(1_500),
            admission_kit(1_000),
        ],
    )
    return policy, claim, expect(Verdict.APPROVE, 41_000, C.DAY_CARE, C.NON_PAYABLE)


@golden
def g14_short_stay_not_day_care():
    """G14. Stay under 24 hours, not a day-care procedure -> REJECT

    Gastroenteritis, no procedure.
    Admitted 3 Oct 2025 20:00, discharged 4 Oct 14:00 (18 h).

      Room            1 day x ₹3,000        3,000
      Consultant                            2,000
      Pharmacy                              1,500
      Investigations                        2,500
      Bill total                            9,000

    Working
      Policy period   within
      Initial wait    long over
      Minimum stay    18 h is under 24 h and there is no day-care procedure: rejected

    Expected: REJECT, ₹0, clauses [2.1_min_hospitalisation]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-10-03 20:00",
        discharged="2025-10-04 14:00",
        diagnosis=GASTROENTERITIS,
        items=[room(3_000, days=1), consultant(2_000), pharmacy(1_500), investigations(2_500)],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.MIN_HOSPITALISATION)


@golden
def g15_two_gates_fail():
    """G15. Two gates fail: both are in the answer key -> REJECT

    New policy: first inception 1 Apr 2025.
    Gastroenteritis, no procedure.
    Admitted 20 Jun 2025 22:00, discharged 21 Jun 12:00 (14 h).

      Room            1 day x ₹3,000        3,000
      Consultant                            2,000
      Pharmacy                              1,500
      Bill total                            6,500

    Working
      Policy period   within
      Initial wait    20 Jun is inside the wait (over on 10 Jul), illness: fires
      Minimum stay    14 h is under 24 h, no day-care procedure: fires

    Expected: REJECT, ₹0, clauses [2.1_min_hospitalisation, 4.3_initial_waiting]
    """
    policy = build_policy(TEST_PRODUCT, first_inception=NEW_POLICY_START)
    claim = build_claim(
        admitted="2025-06-20 22:00",
        discharged="2025-06-21 12:00",
        diagnosis=GASTROENTERITIS,
        items=[room(3_000, days=1), consultant(2_000), pharmacy(1_500)],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.MIN_HOSPITALISATION, C.INITIAL_WAITING)


@golden
def g16_accident_exception_but_short_stay():
    """G16. Accident exception applies, but the stay is too short -> REJECT

    New policy: first inception 1 Apr 2025.
    Fall: fracture of the lower end of the radius, closed reduction (not on the day-care list).
    Admitted 2 May 2025 18:00, discharged 3 May 08:00 (14 h).

      Room            1 day x ₹4,000        4,000
      Surgeon                               8,000
      OT                                    3,000
      Pharmacy                              1,200
      Bill total                           16,200

    Working
      Policy period   within
      Initial wait    inside the wait, but an accident: the exception fires
      Minimum stay    14 h is under 24 h, no day-care procedure: fires

    Expected: REJECT, ₹0, clauses [2.1_min_hospitalisation]
    The accident exception stays in the trace but not in the answer key: a
    rejection lists only the gates that rejected.
    """
    policy = build_policy(TEST_PRODUCT, first_inception=NEW_POLICY_START)
    claim = build_claim(
        admitted="2025-05-02 18:00",
        discharged="2025-05-03 08:00",
        cause=Cause.ACCIDENT,
        diagnosis=dx("S52.5", "Fracture of lower end of radius"),
        procedures=[px("PX-CLOSED-REDUCTION", "Closed reduction of fracture")],
        items=[room(4_000, days=1), surgeon(8_000), ot(3_000), pharmacy(1_200)],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.MIN_HOSPITALISATION)


# ---------------------------------------------------------------- specified diseases and PEDs


SENILE_CATARACT = dx("H25.1", "Senile nuclear cataract")
PHACO = px("PX-PHACO", "Phacoemulsification with intraocular lens implant")


@golden
def g17_cataract_inside_specified_disease_wait():
    """G17. Cataract surgery inside the specified-disease wait -> REJECT

    New policy: first inception 1 Apr 2025.
    Senile nuclear cataract, phacoemulsification with lens implant (PX-PHACO).
    Admitted 20 Nov 2025 08:00, discharged 20 Nov 14:00 (6 h). No room charged.

      Surgeon                              18,000
      OT                                    7,000
      Implant (intraocular lens)           12,000
      Pharmacy                              2,500
      Investigations                        1,500
      Admission kit     (non-payable)       1,000
      Bill total                           42,000

    Working
      Policy period   within
      Initial wait    over on 10 Jul 2025
      Specified wait  cataract is listed: the diagnosis H25.1 starts with H25.
                      18 months from 1 Apr 2025 are over on 1 Oct 2026, so
                      20 Nov 2025 is inside. An illness: fires.
      Minimum stay    6 h is under 24 h, but PX-PHACO is on the day-care list,
                      so the day-care exception fires (the claim is rejected anyway)

    Expected: REJECT, ₹0, clauses [4.2_specific_disease_waiting]
    The rule is named for cataract; the claim says "senile nuclear cataract".
    The engine matches the ICD-10 code, never the words.
    """
    policy = build_policy(TEST_PRODUCT, first_inception=NEW_POLICY_START)
    claim = build_claim(
        admitted="2025-11-20 08:00",
        discharged="2025-11-20 14:00",
        diagnosis=SENILE_CATARACT,
        procedures=[PHACO],
        room_category=None,
        items=[
            surgeon(18_000),
            ot(7_000),
            implant(12_000, "Implant: intraocular lens"),
            pharmacy(2_500),
            investigations(1_500),
            admission_kit(1_000),
        ],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.SPECIFIC_WAITING)


@golden
def g18_hip_replacement_after_a_fall():
    """G18. Hip replacement after a fall, inside the specified-disease wait -> APPROVE

    New policy: first inception 1 Apr 2025.
    Fall at home: fracture of the neck of the femur, total hip replacement (PX-THR).
    Admitted 10 Sep 2025 11:00, discharged 15 Sep 11:00 (120 h).

      Room            5 days x ₹4,000      20,000
      Surgeon                              80,000
      Anaesthetist                         15,000
      OT                                   25,000
      Implant (hip prosthesis)           1,20,000
      Pharmacy                             20,000
      Investigations                       10,000
      Surgical gloves   (non-payable)         500
      Bill total                         2,90,500

    Working
      Policy period   within
      Initial wait    over on 10 Jul 2025
      Specified wait  joint replacement is listed (PX-THR). 18 months from
                      1 Apr 2025 are over on 1 Oct 2026, so 10 Sep 2025 is inside,
                      but the cause is an accident: the exception fires
      Minimum stay    120 h meets 24 h
      Non-payables    500 off                                2,90,000
      Room rent       ₹4,000/day is within the cap           2,90,000
      Sum insured     within 5,00,000                        2,90,000

    Expected: APPROVE, ₹2,90,000, clauses [4.2_accident_exception, A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT, first_inception=NEW_POLICY_START)
    claim = build_claim(
        admitted="2025-09-10 11:00",
        discharged="2025-09-15 11:00",
        cause=Cause.ACCIDENT,
        diagnosis=dx("S72.0", "Fracture of neck of femur"),
        procedures=[px("PX-THR", "Total hip replacement")],
        items=[
            room(4_000, days=5),
            surgeon(80_000),
            anaesthetist(15_000),
            ot(25_000),
            implant(120_000, "Implant: hip prosthesis"),
            pharmacy(20_000),
            investigations(10_000),
            gloves(500),
        ],
    )
    return policy, claim, expect(Verdict.APPROVE, 290_000, C.SPECIFIC_WAITING_ACCIDENT, C.NON_PAYABLE)


DIABETES = ped("Type 2 diabetes mellitus", "E11")


@golden
def g19_declared_diabetes_complication_inside_ped_wait():
    """G19. Declared diabetes; admitted for a diabetic complication inside the PED wait -> REJECT

    The member declared type 2 diabetes (E11); first inception 1 Apr 2024.
    Type 2 diabetes with peripheral circulatory complications (diabetic foot), E11.5.
    Admitted 12 Aug 2025 10:00, discharged 17 Aug 10:00 (120 h).

      Room            5 days x ₹3,000      15,000
      Consultant                            7,500
      Pharmacy                             22,000
      Investigations                        9,000
      Bill total                           53,500

    Working
      Policy period   within
      Initial wait    100 days from 1 Apr 2024: over on 10 Jul 2024
      PED wait        E11.5 starts with E11, so this admission is for the declared
                      diabetes. 30 months from 1 Apr 2024 are over on 1 Oct 2026,
                      so 12 Aug 2025 is inside: fires.
      Minimum stay    120 h meets 24 h

    Expected: REJECT, ₹0, clauses [4.1_ped_waiting]
    """
    policy = build_policy(TEST_PRODUCT, first_inception=dt.date(2024, 4, 1), declared_peds=[DIABETES])
    claim = build_claim(
        admitted="2025-08-12 10:00",
        discharged="2025-08-17 10:00",
        diagnosis=dx("E11.5", "Type 2 diabetes mellitus with peripheral circulatory complications"),
        items=[room(3_000, days=5), consultant(7_500), pharmacy(22_000), investigations(9_000)],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.PED_WAITING)


@golden
def g20_declared_diabetes_but_admitted_for_appendicitis():
    """G20. Declared diabetes, but admitted for appendicitis -> APPROVE

    Same member as G19: declared type 2 diabetes (E11), first inception 1 Apr 2024.
    Acute appendicitis (K35.8), laparoscopic appendicectomy. The discharge
    summary also records the diabetes, as a secondary diagnosis (E11.9).
    Admitted 4 Aug 2025 10:00, discharged 7 Aug 10:00 (72 h).

      Room            3 days x ₹4,000      12,000
      Surgeon                              25,000
      Anaesthetist                          6,000
      OT                                   10,000
      Pharmacy                              7,000
      Investigations                        5,000
      Surgical gloves   (non-payable)         500
      Bill total                           65,500

    Working
      PED wait        the primary diagnosis, K35.8, is not related to diabetes.
                      E11.9 is only a secondary diagnosis: not the reason for this
                      admission, and no rule looks at secondary diagnoses.
      Non-payables    500 off                                65,000
      Room rent       ₹4,000/day is within the cap           65,000
      Sum insured     within 5,00,000                        65,000

    Expected: APPROVE, ₹65,000, clauses [A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT, first_inception=dt.date(2024, 4, 1), declared_peds=[DIABETES])
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        secondary_diagnoses=[dx("E11.9", "Type 2 diabetes mellitus without complications")],
        procedures=[APPENDICECTOMY],
        items=[
            room(4_000, days=3),
            surgeon(25_000),
            anaesthetist(6_000),
            ot(10_000),
            pharmacy(7_000),
            investigations(5_000),
            gloves(500),
        ],
    )
    return policy, claim, expect(Verdict.APPROVE, 65_000, C.NON_PAYABLE)


@golden
def g21_hernia_listed_and_declared():
    """G21. Hernia is both a listed condition and a declared PED: the longer wait decides -> REJECT

    The member declared an inguinal hernia (K40); first inception 1 Jan 2024.
    Unilateral inguinal hernia (K40.9), hernia repair with mesh (PX-HERNIA-REPAIR).
    Admitted 15 Sep 2025 09:00, discharged 17 Sep 09:00 (48 h).

      Room            2 days x ₹4,000       8,000
      Surgeon                              30,000
      Anaesthetist                          6,000
      OT                                   12,000
      Implant (mesh)                        8,000
      Pharmacy                              4,000
      Bill total                           68,000

    Working
      Policy period   within
      Initial wait    100 days from 1 Jan 2024: over on 10 Apr 2024
      Specified wait  hernia is listed; 18 months from 1 Jan 2024 were over on
                      1 Jul 2025, so 15 Sep 2025 is past it
      PED wait        K40.9 starts with the declared K40. 30 months from
                      1 Jan 2024 are over on 1 Jul 2026, so 15 Sep 2025 is
                      inside: fires.
      Minimum stay    48 h meets 24 h

    Expected: REJECT, ₹0, clauses [4.1_ped_waiting]
    """
    policy = build_policy(
        TEST_PRODUCT,
        first_inception=dt.date(2024, 1, 1),
        declared_peds=[ped("Inguinal hernia", "K40")],
    )
    claim = build_claim(
        admitted="2025-09-15 09:00",
        discharged="2025-09-17 09:00",
        diagnosis=dx("K40.9", "Unilateral inguinal hernia, without obstruction or gangrene"),
        procedures=[px("PX-HERNIA-REPAIR", "Inguinal hernia repair with mesh")],
        items=[
            room(4_000, days=2),
            surgeon(30_000),
            anaesthetist(6_000),
            ot(12_000),
            implant(8_000, "Implant: mesh"),
            pharmacy(4_000),
        ],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.PED_WAITING)


# ---------------------------------------------------------------- permanent exclusions


@golden
def g22_cosmetic_rhinoplasty():
    """G22. Cosmetic rhinoplasty: a permanent exclusion -> REJECT

    Acquired deformity of the nose (M95.0), cosmetic rhinoplasty (PX-COSMETIC-RHINOPLASTY).
    Admitted 6 Oct 2025 08:00, discharged 7 Oct 12:00 (28 h).

      Room            1 day x ₹5,000        5,000
      Surgeon                              60,000
      Anaesthetist                         10,000
      OT                                   15,000
      Pharmacy                              3,000
      Bill total                           93,000

    Working
      Policy period   within
      Initial wait    long over
      Exclusions      PX-COSMETIC-RHINOPLASTY is listed under cosmetic surgery: fires
      Minimum stay    28 h meets 24 h

    Expected: REJECT, ₹0, clauses [4.8_cosmetic_surgery]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-10-06 08:00",
        discharged="2025-10-07 12:00",
        diagnosis=dx("M95.0", "Acquired deformity of nose"),
        procedures=[px("PX-COSMETIC-RHINOPLASTY", "Cosmetic rhinoplasty")],
        items=[room(5_000, days=1), surgeon(60_000), anaesthetist(10_000), ot(15_000), pharmacy(3_000)],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.COSMETIC)


@golden
def g23_reconstructive_rhinoplasty_after_an_accident():
    """G23. Reconstructive rhinoplasty after an accident: close to the exclusion, but covered -> APPROVE

    Road accident: fracture of the nasal bones (S02.2), reconstructive rhinoplasty
    (PX-RHINOPLASTY-RECONSTRUCTIVE). The member has been insured since 2022.
    Admitted 6 Oct 2025 08:00, discharged 8 Oct 08:00 (48 h).

      Room            2 days x ₹4,000       8,000
      Surgeon                              40,000
      Anaesthetist                          8,000
      OT                                   12,000
      Pharmacy                              6,000
      Surgical gloves   (non-payable)         500
      Bill total                           74,500

    Working
      Exclusions      the cosmetic surgery exclusion lists only
                      PX-COSMETIC-RHINOPLASTY. Reconstruction after an injury is a
                      different procedure, and is not excluded.
      Non-payables    500 off                                74,000
      Room rent       ₹4,000/day is within the cap           74,000
      Sum insured     within 5,00,000                        74,000

    Expected: APPROVE, ₹74,000, clauses [A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-10-06 08:00",
        discharged="2025-10-08 08:00",
        cause=Cause.ACCIDENT,
        diagnosis=dx("S02.2", "Fracture of nasal bones"),
        procedures=[px("PX-RHINOPLASTY-RECONSTRUCTIVE", "Reconstructive rhinoplasty")],
        items=[
            room(4_000, days=2),
            surgeon(40_000),
            anaesthetist(8_000),
            ot(12_000),
            pharmacy(6_000),
            gloves(500),
        ],
    )
    return policy, claim, expect(Verdict.APPROVE, 74_000, C.NON_PAYABLE)


# ---------------------------------------------------------------- ICU, sub-limits, deductible


@golden
def g24_room_and_icu_both_above_their_caps():
    """G24. Room and ICU both above their caps; each scales only its own lines -> PARTIAL

    Pneumonia: 2 days in ICU, then 3 days on the ward.
    Admitted 1 Jul 2025 10:00, discharged 6 Jul 10:00 (120 h).

      ICU             2 days x ₹12,000     24,000
      Room            3 days x ₹6,000      18,000
      Consultant                            9,000
      Pharmacy                             25,000
      Investigations                       15,000
      Bill total                           91,000

    Working
      Non-payables    none                                              91,000
      Room rent       ₹6,000/day is above the ₹5,000 cap, paid at 5/6.
                      Room + consultant = 18,000 + 9,000 = 27,000;
                      1/6 of it = 4,500 off                             86,500
      ICU             ₹12,000/day is above the ₹8,000 cap, paid at 2/3.
                      Only the ICU line is scaled: 1/3 of 24,000
                      = 8,000 off                                       78,500
      Sum insured     within 5,00,000                                   78,500

    Expected: PARTIAL, ₹78,500, clauses [3.1_room_rent_limit, 3.2_icu_limit]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-07-01 10:00",
        discharged="2025-07-06 10:00",
        diagnosis=PNEUMONIA,
        items=[
            icu(12_000, days=2),
            room(6_000, days=3),
            consultant(9_000),
            pharmacy(25_000),
            investigations(15_000),
        ],
    )
    return policy, claim, expect(Verdict.PARTIAL, 78_500, C.ROOM_RENT, C.ICU_LIMIT)


@golden
def g25_both_eyes_one_sitting():
    """G25. Both eyes in one sitting: the cataract sub-limit counts per eye -> PARTIAL

    Senile nuclear cataract in both eyes, phacoemulsification of both (PX-PHACO x 2).
    Admitted 12 Sep 2025 08:00, discharged 12 Sep 16:00 (8 h). No room charged.

      Surgeon                              50,000
      OT                                   16,000
      Implant (intraocular lens) 2 x ₹20,000   40,000
      Pharmacy                              4,000
      Investigations                        2,000
      Admission kit     (non-payable)       1,000
      Bill total                         1,13,000

    Working
      Specified wait  cataract is listed, but the wait from 1 Apr 2022 was
                      over on 1 Oct 2023
      Minimum stay    8 h is under 24 h, but PX-PHACO is on the day-care list
      Non-payables    1,000 off                                         1,12,000
      Room rent       no room line: not checked                          1,12,000
      Sub-limit       ₹45,000 per eye x 2 eyes = ₹90,000;
                      1,12,000 is above it: capped                        90,000
      Sum insured     within 5,00,000                                     90,000

    Expected: PARTIAL, ₹90,000, clauses [2.2_day_care, 3.3_disease_sublimit, A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-09-12 08:00",
        discharged="2025-09-12 16:00",
        diagnosis=SENILE_CATARACT,
        procedures=[px("PX-PHACO", "Phacoemulsification with intraocular lens implant, both eyes", units=2)],
        room_category=None,
        items=[
            surgeon(50_000),
            ot(16_000),
            implant(20_000, "Implant: intraocular lens", qty=2),
            pharmacy(4_000),
            investigations(2_000),
            admission_kit(1_000),
        ],
    )
    return policy, claim, expect(Verdict.PARTIAL, 90_000, C.DAY_CARE, C.DISEASE_SUBLIMIT, C.NON_PAYABLE)


@golden
def g26_sublimit_then_deductible_then_copay():
    """G26. Sub-limit, then deductible, then co-pay -> PARTIAL (locks that order)

    Policy has a ₹10,000 deductible and a 10% co-pay.
    Senile nuclear cataract, one eye, with a premium lens (PX-PHACO).
    Admitted 3 Nov 2025 08:00, discharged 3 Nov 15:00 (7 h). No room charged.

      Surgeon                              30,000
      OT                                   10,000
      Implant (premium intraocular lens)   25,000
      Pharmacy                              3,000
      Investigations                        2,000
      Bill total                           70,000

    Working
      Minimum stay    7 h is under 24 h, but PX-PHACO is on the day-care list
      Non-payables    none                                   70,000
      Sub-limit       ₹45,000 for one eye: capped            45,000
      Deductible      10,000 off                             35,000
      Co-pay          10% of 35,000 = 3,500 off              31,500
      Sum insured     within 5,00,000                        31,500

    Expected: PARTIAL, ₹31,500,
              clauses [2.2_day_care, 3.3_disease_sublimit, 5.1_deductible, 5.2_copay]

    With the deductible before the sub-limit: 70,000 - 10,000 = 60,000, capped at
    45,000, less 4,500 co-pay = 40,500. With co-pay before the deductible:
    45,000 - 4,500 - 10,000 = 30,500.
    """
    policy = build_policy(TEST_PRODUCT, deductible=10_000, copay_bp=1_000)
    claim = build_claim(
        admitted="2025-11-03 08:00",
        discharged="2025-11-03 15:00",
        diagnosis=SENILE_CATARACT,
        procedures=[PHACO],
        room_category=None,
        items=[
            surgeon(30_000),
            ot(10_000),
            implant(25_000, "Implant: premium intraocular lens"),
            pharmacy(3_000),
            investigations(2_000),
        ],
    )
    return policy, claim, expect(
        Verdict.PARTIAL, 31_500, C.DAY_CARE, C.DISEASE_SUBLIMIT, C.DEDUCTIBLE, C.COPAY
    )


@golden
def g27_deductible_larger_than_the_claim():
    """G27. Deductible larger than the claim -> REJECT (nothing is left to pay)

    Policy has a ₹25,000 deductible.
    Pneumonia. Admitted 8 Dec 2025 09:00, discharged 10 Dec 09:00 (48 h).

      Room            2 days x ₹3,000       6,000
      Consultant                            4,000
      Pharmacy                              5,000
      Investigations                        3,000
      Bill total                           18,000

    Working
      Non-payables    none                                   18,000
      Room rent       ₹3,000/day is within the cap           18,000
      Deductible      the first ₹25,000 is the policyholder's, and the
                      whole 18,000 falls inside it                0
      Sum insured     within 5,00,000                             0

    Expected: REJECT, ₹0, clauses [5.1_deductible]
    """
    policy = build_policy(TEST_PRODUCT, deductible=25_000)
    claim = build_claim(
        admitted="2025-12-08 09:00",
        discharged="2025-12-10 09:00",
        diagnosis=PNEUMONIA,
        items=[room(3_000, days=2), consultant(4_000), pharmacy(5_000), investigations(3_000)],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.DEDUCTIBLE)


# ---------------------------------------------------------------- pre- and post-hospitalisation


@golden
def g28_pre_and_post_bills_inside_their_windows():
    """G28. Pre/post bills inside their windows are paid, and never scaled with room rent -> PARTIAL

    Acute appendicitis, laparoscopic appendicectomy.
    Admitted 4 Aug 2025 10:00, discharged 7 Aug 10:00 (72 h).

      Before the stay
        20 Jul  Consultation                   1,600
        25 Jul  Ultrasound                     2,400
      The stay
        Room            3 days x ₹8,000       24,000
        Surgeon                               40,000
        OT                                    16,000
        Pharmacy                               6,000
      After the stay
        20 Aug  Follow-up consultation         1,000
      Bill total                              91,000

    Working
      Pre window      45 days before 4 Aug: 20 Jun to 4 Aug. Both bills inside.
      Post window     90 days after 7 Aug: 7 Aug to 5 Nov. The bill is inside.  91,000
      Non-payables    none                                                        91,000
      Room rent       ₹8,000/day is above the ₹5,000 cap, paid at 5/8.
                      Room + surgeon + OT = 80,000; 3/8 of it = 30,000 off       61,000
                      The two consultations are consultant charges, but they
                      are not part of the stay, so they are not scaled.
      Sum insured     within 5,00,000                                            61,000

    Expected: PARTIAL, ₹61,000, clauses [3.1_room_rent_limit]
    (Scaling the consultations too would give 60,025.)
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=[
            pre(consultant(1_600, "Consultation"), on="2025-07-20"),
            pre(investigations(2_400, "Ultrasound"), on="2025-07-25"),
            room(8_000, days=3),
            surgeon(40_000),
            ot(16_000),
            pharmacy(6_000),
            post(consultant(1_000, "Follow-up consultation"), on="2025-08-20"),
        ],
    )
    return policy, claim, expect(Verdict.PARTIAL, 61_000, C.ROOM_RENT)


@golden
def g29_pre_and_post_bills_outside_their_windows():
    """G29. Bills dated outside the pre/post windows are dropped -> PARTIAL

    Pneumonia. Admitted 1 Sep 2025 09:00, discharged 4 Sep 09:00 (72 h).

      Before the stay
        10 Jul  Consultation                   1,200
        20 Aug  Chest X-ray                      800
      The stay
        Room            3 days x ₹3,000        9,000
        Consultant                             4,500
        Pharmacy                              12,000
        Investigations                         8,000
      After the stay
         1 Oct  Follow-up consultation         1,000
        10 Dec  Follow-up consultation         1,000
      Bill total                              37,500

    Working
      Pre window      45 days before 1 Sep: 18 Jul to 1 Sep.
                      10 Jul is outside: 1,200 off                            36,300
      Post window     90 days after 4 Sep: 4 Sep to 3 Dec.
                      10 Dec is outside: 1,000 off                            35,300
      Non-payables    none                                                    35,300
      Room rent       ₹3,000/day is within the cap                            35,300
      Sum insured     within 5,00,000                                         35,300

    Expected: PARTIAL, ₹35,300,
              clauses [3.5_pre_hospitalisation, 3.6_post_hospitalisation]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-09-01 09:00",
        discharged="2025-09-04 09:00",
        diagnosis=PNEUMONIA,
        items=[
            pre(consultant(1_200, "Consultation"), on="2025-07-10"),
            pre(investigations(800, "Chest X-ray"), on="2025-08-20"),
            room(3_000, days=3),
            consultant(4_500),
            pharmacy(12_000),
            investigations(8_000),
            post(consultant(1_000, "Follow-up consultation"), on="2025-10-01"),
            post(consultant(1_000, "Follow-up consultation"), on="2025-12-10"),
        ],
    )
    return policy, claim, expect(Verdict.PARTIAL, 35_300, C.PRE_HOSPITALISATION, C.POST_HOSPITALISATION)


# ---------------------------------------------------------------- AYUSH


@golden
def g30_ayurveda_in_an_ayush_hospital():
    """G30. Ayurvedic treatment in an AYUSH hospital, capped at the AYUSH limit -> PARTIAL

    Rheumatoid arthritis (M06.9), inpatient Ayurvedic treatment (Panchakarma),
    at a hospital that qualifies as an AYUSH hospital.
    Admitted 2 Feb 2026 10:00, discharged 9 Feb 10:00 (168 h).

      Room            7 days x ₹2,000       14,000
      Consultant (Ayurvedic physician)       7,000
      Panchakarma therapy                   10,500
      Pharmacy (Ayurvedic medicines)         4,500
      Bill total                            36,000

    Working
      AYUSH           Ayurveda in an AYUSH hospital: covered
      Minimum stay    168 h meets 24 h
      Non-payables    none                                   36,000
      Room rent       ₹2,000/day is within the cap           36,000
      AYUSH limit     ₹25,000 a claim; 36,000 is above it:
                      capped, 11,000 off                     25,000
      Sum insured     within 5,00,000                        25,000

    Expected: PARTIAL, ₹25,000, clauses [3.4_ayush]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2026-02-02 10:00",
        discharged="2026-02-09 10:00",
        diagnosis=dx("M06.9", "Rheumatoid arthritis, unspecified"),
        treatment_system=TreatmentSystem.AYURVEDA,
        hospital=Hospital(name="Test Ayurveda Hospital", city="Kochi", ayush_hospital=True),
        items=[
            room(2_000, days=7),
            consultant(7_000, "Ayurvedic physician visits"),
            therapy(10_500, "Panchakarma therapy"),
            pharmacy(4_500, "Ayurvedic medicines"),
        ],
    )
    return policy, claim, expect(Verdict.PARTIAL, 25_000, C.AYUSH)


@golden
def g31_homeopathy_outside_an_ayush_hospital():
    """G31. Homeopathic treatment at a hospital that is not an AYUSH hospital -> REJECT

    Low back pain (M54.5), inpatient homeopathic treatment at a general nursing
    home that does not qualify as an AYUSH hospital.
    Admitted 10 Jan 2026 10:00, discharged 13 Jan 10:00 (72 h).

      Room            3 days x ₹2,500        7,500
      Consultant                             3,000
      Pharmacy                               2,000
      Bill total                            12,500

    Working
      AYUSH           homeopathy is covered only in an AYUSH hospital, and this
                      nursing home is not one: fires
      Minimum stay    72 h meets 24 h

    Expected: REJECT, ₹0, clauses [3.4_ayush]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2026-01-10 10:00",
        discharged="2026-01-13 10:00",
        diagnosis=dx("M54.5", "Low back pain"),
        treatment_system=TreatmentSystem.HOMEOPATHY,
        hospital=Hospital(name="Test Nursing Home", city="Nashik", ayush_hospital=False),
        items=[room(2_500, days=3), consultant(3_000), pharmacy(2_000)],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.AYUSH)


# ---------------------------------------------------------------- escalation

G01_BILL = [
    room(4_000, days=3),
    nursing(500, days=3),
    surgeon(25_000),
    anaesthetist(6_000),
    ot(10_000),
    pharmacy(6_000),
    investigations(4_000),
    gloves(500),
    admission_kit(1_000),
    registration(200),
]
"""G01's bill: total ₹66,200, of which ₹64,500 is payable."""


@golden
def g32_discharge_summary_missing():
    """G32. The discharge summary is missing -> ESCALATE

    G01's claim (appendicitis, bill total ₹66,200), but only the claim form and
    the hospital bill were submitted.

    Working
      Documents       the discharge summary is missing. It is the source of the
                      diagnosis, dates and cause, so no gate can be checked.

    Expected: ESCALATE, ₹0, clauses [7.1_missing_documents]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=G01_BILL,
        documents=[DocType.CLAIM_FORM, DocType.HOSPITAL_BILL],
    )
    return policy, claim, expect(Verdict.ESCALATE, 0, C.MISSING_DOCUMENTS)


@golden
def g33_bill_missing_but_policy_not_in_force():
    """G33. The bill is missing, but the policy was not in force -> REJECT (the gap cannot matter)

    Gastroenteritis. Admitted 2 Apr 2026 09:00, discharged 3 Apr 19:00 (34 h).
    Only the claim form and the discharge summary were submitted.

    Working
      Policy period   2 Apr 2026 is after 31 Mar 2026: fires
      Documents       the hospital bill is missing, but the claim is rejected on
                      the policy period, which no bill could change

    Expected: REJECT, ₹0, clauses [6.1_policy_period]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2026-04-02 09:00",
        discharged="2026-04-03 19:00",
        diagnosis=GASTROENTERITIS,
        items=[room(3_000, days=2), consultant(2_000), pharmacy(1_500)],
        documents=[DocType.CLAIM_FORM, DocType.DISCHARGE_SUMMARY],
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.POLICY_PERIOD)


@golden
def g34_claimed_amount_differs_on_a_payable_claim():
    """G34. The claimed amount disagrees with the bill on a claim that would be paid -> ESCALATE

    G01's claim (appendicitis, bill total ₹66,200), but the claim form claims ₹72,000.

    Working
      Gates           none fires, so the claim would be paid
      Claim form      it claims 72,000 against a bill total of 66,200, and the
                      claim would otherwise be paid: fires

    Expected: ESCALATE, ₹0, clauses [7.2_document_mismatch]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=G01_BILL,
        claimed_amount=72_000,
    )
    return policy, claim, expect(Verdict.ESCALATE, 0, C.DOCUMENT_MISMATCH)


@golden
def g35_claim_form_dates_change_the_outcome():
    """G35. The claim form's dates would change the outcome -> ESCALATE

    New policy: first inception 1 Apr 2025, so the initial wait is over on 10 Jul 2025.
    Pneumonia. The discharge summary says admitted 2 Jul 2025 10:00, discharged
    5 Jul 10:00. The claim form says admitted 12 Jul, discharged 15 Jul.

      Room            3 days x ₹3,000        9,000
      Consultant                             4,500
      Pharmacy                              12,000
      Investigations                         8,000
      Bill total (and claimed amount)       33,500

    Working
      On the hospital's dates     2 Jul is inside the initial wait: REJECT ₹0
      On the claim form's dates   12 Jul is past it: APPROVE ₹33,500
      Claim form      the dates change the outcome: fires

    Expected: ESCALATE, ₹0, clauses [7.2_document_mismatch]
    """
    policy = build_policy(TEST_PRODUCT, first_inception=NEW_POLICY_START)
    claim = build_claim(
        admitted="2025-07-02 10:00",
        discharged="2025-07-05 10:00",
        diagnosis=PNEUMONIA,
        items=[room(3_000, days=3), consultant(4_500), pharmacy(12_000), investigations(8_000)],
        form_admitted="2025-07-12 10:00",
        form_discharged="2025-07-15 10:00",
    )
    return policy, claim, expect(Verdict.ESCALATE, 0, C.DOCUMENT_MISMATCH)


@golden
def g36_claim_form_dates_differ_but_cannot_matter():
    """G36. The claim form's dates differ, but cannot change the outcome -> APPROVE

    G01's claim, but the claim form says admitted 5 Aug 10:00 where the
    discharge summary says 4 Aug 10:00. Both say discharged 7 Aug 10:00.

    Working
      On the hospital's dates     APPROVE ₹64,500 (G01)
      On the claim form's dates   a 48 h stay still meets 24 h, and nothing else
                                  depends on the dates: APPROVE ₹64,500
      Claim form      the same result either way: decided on the hospital's records

    Expected: APPROVE, ₹64,500, clauses [A1_non_payable_items]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-08-04 10:00",
        discharged="2025-08-07 10:00",
        diagnosis=APPENDICITIS,
        procedures=[APPENDICECTOMY],
        items=G01_BILL,
        form_admitted="2025-08-05 10:00",
    )
    return policy, claim, expect(Verdict.APPROVE, 64_500, C.NON_PAYABLE)


@golden
def g37_claimed_amount_differs_but_a_gate_rejects():
    """G37. The claimed amount disagrees with the bill, but a gate rejects anyway -> REJECT

    G14's claim (gastroenteritis, 18-hour stay, bill total ₹9,000), but the
    claim form claims ₹10,000.

    Working
      Minimum stay    18 h is under 24 h and there is no day-care procedure: fires
      Claim form      the amounts disagree, but a rejection does not depend on them

    Expected: REJECT, ₹0, clauses [2.1_min_hospitalisation]
    """
    policy = build_policy(TEST_PRODUCT)
    claim = build_claim(
        admitted="2025-10-03 20:00",
        discharged="2025-10-04 14:00",
        diagnosis=GASTROENTERITIS,
        items=[room(3_000, days=1), consultant(2_000), pharmacy(1_500), investigations(2_500)],
        claimed_amount=10_000,
    )
    return policy, claim, expect(Verdict.REJECT, 0, C.MIN_HOSPITALISATION)
