"""A group mediclaim product of the older Indian kind, modelled on New India Mediclaim.

Source: New India Mediclaim Policy, The New India Assurance Co. Ltd., policy
clause document, UIN NIAHLIP23187V052223 (corpus/manifest.csv). The PDF is not
in the repo; corpus/fetch.py downloads it.

Where Arogya Sanjeevani is IRDAI's standard product, this is an insurer's own,
and it differs in ways that matter to an agent:

- limits are a share of the sum insured with no rupee ceiling (1% a day for the
  room, 2% for intensive care), so the same room rate passes at one sum insured
  and fails at another;
- the proportionate deduction bites only on "Associate Medical Expenses", a term
  the wording defines, and never on pharmacy, consumables, implants or diagnostics;
- there are four waiting periods, not two, and the shortest is ninety days for
  diabetes, hypertension and cardiac conditions;
- pre-existing diseases wait forty-eight months;
- day care is a closed list of 226 procedures, so a treatment that finishes
  inside a day is only covered if it is on the list. A hernia repair is not,
  where under Arogya Sanjeevani's open definition it is;
- there is no co-payment unless the policyholder buys one, and AYUSH treatment
  needs no AYUSH hospital.

Every value below is hand-extracted from that wording, with its section in a
comment; corpus/mapping.yaml adds pages and quotes, and
tests/test_new_india_mediclaim.py pins how every catalogue condition comes out.
"""

from __future__ import annotations

from engine import clauses as C
from engine.schema import (
    ALL_DOCUMENTS,
    Ayush,
    BillCategory,
    Cap,
    ConditionGroup,
    Duration,
    DurationUnit,
    Exclusion,
    LineExclusion,
    Match,
    ProductTerms,
    SpecificWait,
    Sublimit,
    Wait,
)
from sampler import ambiguity
from sampler.products.arogya_sanjeevani import DIETARY_SUPPLEMENTS, NON_PAYABLE_ITEMS
from sampler.profiles import ProductProfile

PRODUCT_ID = "NEW_INDIA_MEDICLAIM"
SOURCE = (
    "New India Mediclaim Policy, The New India Assurance Co. Ltd., policy clause document, "
    "UIN NIAHLIP23187V052223 (corpus/manifest.csv)"
)


def _months(n: int) -> Duration:
    return Duration(value=n, unit=DurationUnit.MONTHS)


def _days(n: int) -> Duration:
    return Duration(value=n, unit=DurationUnit.DAYS)


def _group(name: str, wait: Duration, icd10: tuple[str, ...] = (), procedures: tuple[str, ...] = ()) -> ConditionGroup:
    return ConditionGroup(
        name=name, match=Match(icd10_prefixes=icd10, procedure_codes=procedures), duration=wait
    )


NINETY_DAYS, TWO_YEARS, THREE_YEARS, FOUR_YEARS = _days(90), _months(24), _months(36), _months(48)

# 4.2, lists (i) to (iv). Each listed item is a group of its own, so a claim that
# falls under two of them waits for the longer, as 4.2.c requires.
SPECIFIED_DISEASES: tuple[ConditionGroup, ...] = (
    # (i) 90 days
    _group("Diabetes Mellitus", NINETY_DAYS, ("E10", "E11", "E12", "E13", "E14")),
    _group("Hypertension", NINETY_DAYS, ("I10", "I11", "I12", "I13", "I15")),
    # "Cardiac Conditions": the ischaemic, rhythm and failure codes. Hypertensive
    # heart disease sits under Hypertension above and waits the same ninety days.
    _group("Cardiac Conditions", NINETY_DAYS,
           ("I20", "I21", "I22", "I23", "I24", "I25", "I34", "I35", "I42", "I44", "I45", "I46",
            "I47", "I48", "I49", "I50", "I51")),
    # (ii) 24 months
    _group("All internal and external benign tumours, cysts, polyps of any kind, including benign breast lumps",
           TWO_YEARS,
           ("D1", "D2", "D30", "D31", "D32", "D33", "D34", "D35", "D36",
            "J33", "J38.1", "K09", "K62.0", "K62.1", "L72", "M71.2", "N60", "N63", "N84")),
    _group("Benign ear, nose, throat disorders", TWO_YEARS,
           ("H65.2", "H65.3", "H65.4", "H66.1", "H66.2", "H66.3", "H70", "H71", "H72", "H74",
            "J31", "J33", "J34", "J35", "J37", "J38")),
    _group("Benign prostate hypertrophy", TWO_YEARS, ("N40",)),
    _group("Cataract and age related eye ailments", TWO_YEARS, ("H25", "H26", "H28", "Q12.0"),
           procedures=("PX-PHACO",)),
    _group("Gastric/ Duodenal Ulcer", TWO_YEARS, ("K25", "K26", "K27", "K28")),
    _group("Gout and Rheumatism", TWO_YEARS, ("M05", "M06", "M10", "M79.0")),
    _group("Hernia of all types", TWO_YEARS, ("K40", "K41", "K42", "K43", "K44", "K45", "K46")),
    _group("Hydrocele", TWO_YEARS, ("N43",)),
    _group("Non Infective Arthritis", TWO_YEARS, ("M05", "M06", "M07", "M08", "M1")),
    _group("Piles, Fissures and Fistula in anus", TWO_YEARS, ("K60", "K64")),
    _group("Pilonidal sinus, Sinusitis and related disorders", TWO_YEARS, ("J01", "J32", "L05")),
    _group("Prolapse inter Vertebral Disc and Spinal Diseases unless arising from accident", TWO_YEARS,
           ("M4", "M50", "M51", "M53", "M54")),
    # "Skin Disorders" read as the chronic ones, not infections of the skin: an
    # abscess or a cellulitis is an acute infection and is not what the list means
    # (corpus/mapping.yaml records the reading).
    _group("Skin Disorders, other than infections of the skin", TWO_YEARS, ("L2", "L3", "L4")),
    _group("Stone in Gall Bladder and Bile duct, excluding malignancy", TWO_YEARS, ("K80",)),
    _group("Stones in Urinary system", TWO_YEARS, ("N20", "N21", "N22", "N23")),
    _group("Treatment for Menorrhagia/Fibromyoma, Myoma and Prolapsed uterus", TWO_YEARS,
           ("D25", "N81", "N92")),
    _group("Varicose Veins and Varicose Ulcers", TWO_YEARS, ("I83",)),
    _group("Renal Failure", TWO_YEARS, ("N17", "N18", "N19")),
    _group("Puberty and Menopause related Disorders", TWO_YEARS, ("N95",)),
    _group("Internal Congenital Diseases", TWO_YEARS, ("Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9")),
    # (iii) 36 months
    _group("Congenital External Disease", THREE_YEARS, ("Q0", "Q1")),
    # (iv) 48 months
    _group("Joint Replacement due to Degenerative Condition", FOUR_YEARS, procedures=("PX-THR", "PX-TKR")),
    _group("Age-related Osteoarthritis & Osteoporosis", FOUR_YEARS,
           ("M15", "M16", "M17", "M18", "M19", "M80", "M81")),
    _group("Treatment of Mental Illness", FOUR_YEARS, ("F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7")),
    _group("Age Related Macular Degeneration (ARMD)", FOUR_YEARS, ("H35.3",)),
)

# 4.4.5 (Excl08), 4.4.12 (Excl15), 4.4.14 (Excl17). The other standard exclusions
# are in the wording but no catalogue condition reaches them.
EXCLUSIONS: tuple[Exclusion, ...] = (
    Exclusion(clause_id=C.COSMETIC, match=Match(procedure_codes=("PX-COSMETIC-RHINOPLASTY", "PX-LIPOSUCTION"))),
    Exclusion(clause_id=C.REFRACTIVE_ERROR, match=Match(icd10_prefixes=("H52",), procedure_codes=("PX-LASIK",))),
    Exclusion(clause_id=C.STERILITY_INFERTILITY,
              match=Match(icd10_prefixes=("N46", "N97"), procedure_codes=("PX-IVF",))),
)

# Annexure I, a closed list of 226 procedures. These are the ones the catalogue
# can reach, with the item that covers each. A procedure not on the list is not
# day care however short the stay, which is 2.18's "except for specified
# procedures / treatments as mentioned in Annexure I".
DAY_CARE_PROCEDURES: tuple[str, ...] = (
    "PX-CRIF-RADIUS",  # 178 ORIF with K wire fixation - small bones; 202 closed reduction with osteosynthesis
    "PX-HAEMORRHOIDECTOMY",  # 110 Surgical Treatment Of Haemorrhoids
    "PX-LITHOTRIPSY",  # 67 ESWL
    "PX-PHACO",  # 55 Surgery for cataract
    "PX-RHINOPLASTY-RECONSTRUCTIVE",  # 17 Septoplasty; 20 Reduction of fracture of Nasal Bone
    "PX-TONSILLECTOMY",  # 34 Tonsillectomy without adenoidectomy; 35 with adenoidectomy
)
"""Hernia repair is deliberately absent: it is nowhere in Annexure I."""

TERMS = ProductTerms(
    product_id=PRODUCT_ID,
    source=SOURCE,
    initial_wait=Wait(duration=_days(30), accident_exempt=True),  # 4.3 (Excl03)
    specific_wait=SpecificWait(groups=SPECIFIED_DISEASES, accident_exempt=True),  # 4.2.a
    ped_wait=FOUR_YEARS,  # 4.1 (Excl01) and definition 2.35: 48 months
    exclusions=EXCLUSIONS,
    # 3.4: up to 100% of the sum insured, with no requirement that the hospital be
    # an AYUSH hospital.
    ayush=Ayush(covered=True, requires_ayush_hospital=False, cap=None),
    min_stay_hours=24,  # 2.18
    day_care_procedures=DAY_CARE_PROCEDURES,  # 2.18, Annexure I
    required_documents=ALL_DOCUMENTS,  # 5.20.c.i, iii
    pre_hospitalisation_days=30,  # 3.1(e), 2.36
    post_hospitalisation_days=60,  # 3.1(f), 2.37
    line_exclusions=(
        # Annexure II Lists I-IV, and 4.4.18 for the hospital's own service and
        # registration charges. The lists are IRDAI's standard ones, the same as
        # Arogya Sanjeevani's Annexure A, so the item codes are shared.
        LineExclusion(clause_id=C.NON_PAYABLE, item_codes=NON_PAYABLE_ITEMS),
        LineExclusion(clause_id=C.DIETARY_SUPPLEMENTS, item_codes=DIETARY_SUPPLEMENTS),  # 4.4.11 (Excl14)
    ),
    # 3.1(a): room, boarding, DMO/RMO/CMO/RMP charges and nursing, not exceeding
    # 1% of the sum insured a day. Nursing is inside that limit, so it counts
    # towards the daily rate.
    room_cap=Cap(bp_of_si=100),
    room_rate_includes=(BillCategory.NURSING,),
    # 3.2 with 2.46: the proportionate deduction falls on Associate Medical
    # Expenses, being the professional fees, anaesthesia, theatre and procedure
    # charges, and never on pharmacy, consumables, implants or diagnostics.
    room_associated=(
        BillCategory.ANAESTHETIST,
        BillCategory.CONSULTANT,
        BillCategory.OT,
        BillCategory.SURGEON,
    ),
    icu_cap=Cap(bp_of_si=200),  # 3.1(b): 2% of the sum insured a day
    icu_associated=(),
    sublimits=(
        # 3.3: 20% of the sum insured, at most Rs 50,000, for each eye.
        Sublimit(
            name="Cataract, per eye",
            match=Match(icd10_prefixes=("H25", "H26", "H28", "Q12.0"), procedure_codes=("PX-PHACO",)),
            cap_per_unit=Cap(rupees=50_000, bp_of_si=2_000),
        ),
    ),
)

NEW_INDIA_MEDICLAIM = ProductProfile(
    product_id=PRODUCT_ID,
    source=SOURCE,
    # The insurer, its address and the UIN are invented, and so is the product's
    # name: unlike Arogya Sanjeevani, this is a company's own product, not a
    # standard one, so its name belongs to that company and is not used here.
    product_name="Sarvodaya Mediclaim Policy",
    insurer="Pragati Sarvodaya General Insurance Company Limited",
    insurer_address="Sarvodaya Towers, 2nd Floor, 14 Cathedral Road, Chennai 600 086",
    uin="PSGIHLIP26002V012627",
    # The wording leaves the amounts to the schedule. A sum insured under two lakh
    # would put the 1% room limit below any ward rate in the catalogue, and the
    # cumulative bonus starts at two lakh (3.18 Note 2.i).
    sum_insured_options=(2_00_000, 3_00_000, 5_00_000, 8_00_000),
    # 3.16 Optional Cover IV: a voluntary co-payment of 20%, bought for a discount
    # on the premium. There is no co-payment otherwise.
    copay_options_bp=(2_000,),
    mandatory_copay_bp=0,
    deductible_options=(),
    bonus_step_bp=2_500,  # 3.18: 25% for each claim-free year
    bonus_max_bp=5_000,  # up to 50%
    policy_prefix="NIM",
    # The product line is far older than this revision of its wording, so a member
    # may have been covered continuously for longer than the wording has existed.
    launched=None,
    build_terms=lambda sum_insured: TERMS,
    substitutes={
        # No co-payment unless bought, so the AYUSH reject cannot be built: this
        # product covers AYUSH anywhere, and its AYUSH cover has no limit of its own.
        "ayush_not_qualified": "specific_wait",
        "ayush_capped": "pre_post_window",
        "deductible_only": "ayush_covered",  # no deductible
        "sublimit_deductible_copay": "room_rent_exclusion_copay",  # no deductible
    },
    ambiguities=(
        ambiguity.copay_after_sum_insured,  # 3.16 does not say where the co-payment falls in the order
        ambiguity.room_limit_with_pre_post_bills,  # 2.46 could be read to cover a pre-admission consultant's fee
        ambiguity.pre_post_with_day_care,  # 2.36 and 2.37 want an admissible inpatient hospitalisation
        ambiguity.sublimit_with_pre_post,  # 3.3 "any claim relating to Cataract"
        ambiguity.room_limit_on_ayush,  # 3.4 sets its own limit and does not mention 3.1
        # Not bonus_in_percentage_limits: 2.50 and 3.18 Note 1 say in terms that the
        # cumulative bonus is not part of the sum insured for reckoning any limit.
        # Not room_limit_with_icu_stay: intensive care has its own limit under
        # 3.1(b) and is not an Associate Medical Expense, so it is never scaled.
    ),
)
