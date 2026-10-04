"""Arogya Sanjeevani Policy, as worded by Generali Central Insurance Company Limited.

UIN GCIHLIP20160V011920. Arogya Sanjeevani is IRDAI's standard individual health
product: every insurer sells it with the same cover, so this one wording stands
for the product. The PDF is not in the repo; corpus/manifest.csv records where
to fetch it and corpus/fetch.py downloads it.

Every value here is hand-extracted from that wording. Comments cite its own
section numbers ("4.1.i", "Excl02"); corpus/mapping.yaml adds page numbers and
records each interpretation. The wording names conditions and items in words:
the ICD-10 prefixes, procedure codes and bill item codes below are this
project's coding of those words (sampler/catalogue.py), and
tests/test_arogya_sanjeevani.py pins how every catalogue condition comes out.

Two numbering quirks of the wording: the standard and specific exclusions are
numbered 7.1-7.21 although they sit under chapter 6, so they are cited by their
IRDAI codes (Excl04-Excl18); and the claim procedure is chapter 7, part III.
"""

from __future__ import annotations

import datetime as dt

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
from sampler.profiles import ProductProfile

PRODUCT_ID = "AROGYA_SANJEEVANI_GCI"
SOURCE = (
    "Arogya Sanjeevani Policy, Generali Central Insurance Company Limited, policy wording, "
    "UIN GCIHLIP20160V011920 (corpus/manifest.csv)"
)


def _months(n: int) -> Duration:
    return Duration(value=n, unit=DurationUnit.MONTHS)


def _group(name: str, months: int, icd10: tuple[str, ...] = (), procedures: tuple[str, ...] = ()) -> ConditionGroup:
    return ConditionGroup(
        name=name, match=Match(icd10_prefixes=icd10, procedure_codes=procedures), duration=_months(months)
    )


# 6.3 (Excl02): each listed item, in the wording's order and words. Where an item
# names a procedure (tonsillectomy, hysterectomy), any claim with that procedure
# matches, whatever the diagnosis. A claim matching several items waits for the
# longest, as 6.3.c says for PED against a listed condition.
SPECIFIED_DISEASES: tuple[ConditionGroup, ...] = (
    # i. 24 months
    _group("Benign ENT disorders", 24,
           ("H65.2", "H65.3", "H65.4", "H66.1", "H66.2", "H66.3", "H70", "H71", "H72", "H74", "H80",
            "J31", "J32", "J33", "J34", "J35", "J37", "J38")),
    _group("Tonsillectomy", 24, procedures=("PX-TONSILLECTOMY",)),
    _group("Adenoidectomy", 24, procedures=("PX-ADENOIDECTOMY",)),
    _group("Mastoidectomy", 24, procedures=("PX-MASTOIDECTOMY",)),
    _group("Tympanoplasty", 24, procedures=("PX-TYMPANOPLASTY",)),
    _group("Hysterectomy", 24, procedures=("PX-HYSTERECTOMY",)),
    _group("All internal or external benign tumors, cysts, polyps of any kind, including benign breast lumps", 24,
           ("D1", "D2", "D30", "D31", "D32", "D33", "D34", "D35", "D36",  # benign neoplasms D10-D36
            "J33", "J38.1", "K09", "K31.7", "K62.0", "K62.1", "K63.5", "L72", "M71.2", "N28.1",
            "N60", "N63", "N83.0", "N83.1", "N83.2", "N84")),
    _group("Benign Prostate Hypertrophy", 24, ("N40",)),
    _group("Cataract and age related eye ailments", 24, ("H25", "H26", "H28", "H35.3", "Q12.0"),
           procedures=("PX-PHACO",)),
    _group("Gastric/ Duodenal Ulcer", 24, ("K25", "K26", "K27", "K28")),
    _group("Gout and Rheumatism", 24, ("M05", "M06", "M10", "M79.0")),
    _group("Hernia of all types", 24, ("K40", "K41", "K42", "K43", "K44", "K45", "K46")),
    _group("Hydrocele", 24, ("N43",)),
    # Arthritis that is not infective: M05-M19 without M00-M03 (infective arthropathies).
    _group("Non Infective Arthritis", 24, ("M05", "M06", "M07", "M08", "M1")),
    _group("Piles, Fissures and Fistula in anus", 24, ("K60", "K64")),
    _group("Pilonidal sinus, Sinusitis and related disorders", 24, ("J01", "J32", "L05")),
    # Dorsopathies, M40-M54, low back pain (M54.5) included.
    _group("Prolapse inter Vertebral Disc and Spinal Diseases unless arising from accident", 24,
           ("M4", "M50", "M51", "M53", "M54")),
    # By diagnosis only: a cholecystectomy for a malignancy is not "calculi".
    _group("Calculi in urinary system, Gall Bladder and bile duct, excluding malignancy", 24,
           ("K80", "N20", "N21", "N22")),
    _group("Varicose Veins and Varicose Ulcers", 24, ("I83",)),
    # ii. 36 months
    _group("Treatment for joint replacement unless arising from accident", 36, procedures=("PX-THR", "PX-TKR")),
    _group("Age-related Osteoarthritis & Osteoporosis", 36, ("M15", "M16", "M17", "M18", "M19", "M80", "M81")),
)

# Standard exclusions (6.B) that some catalogue condition falls under. The others
# (Excl04-07, 09-13, 16, 18) have no catalogue condition and are not modelled.
EXCLUSIONS: tuple[Exclusion, ...] = (
    # Excl08: "unless for reconstruction following an Accident, Burn(s) or Cancer";
    # so by procedure: aesthetic surgery only, never a reconstruction.
    Exclusion(clause_id=C.COSMETIC, match=Match(procedure_codes=("PX-COSMETIC-RHINOPLASTY", "PX-LIPOSUCTION"))),
    # Excl15: "refractive error less than 7.5 diopters". Every catalogue refractive
    # error states its power, and all are under 7.5 (pinned by a test).
    Exclusion(clause_id=C.REFRACTIVE_ERROR, match=Match(icd10_prefixes=("H52",), procedure_codes=("PX-LASIK",))),
    # Excl17: sterility and infertility, assisted reproduction included.
    Exclusion(clause_id=C.STERILITY_INFERTILITY, match=Match(icd10_prefixes=("N46", "N97"), procedure_codes=("PX-IVF",))),
)

# Annexure A. List I is not covered at all; Lists II-IV are subsumed into room,
# procedure or treatment charges, so none is paid as a line of its own. Each
# catalogue item, with where the annexure lists it:
NON_PAYABLE_ITEMS: tuple[str, ...] = (
    "NP-GLOVES",  # List I 56 "GLOVES"
    "NP-MASK",  # List I 60 "MASK"; List II 15 "FACE MASK"
    "NP-ADMISSION-KIT",  # List II 27 "ADMISSION KIT"
    "NP-REGISTRATION",  # List IV 1 "ADMISSION/REGISTRATION CHARGES"
    "NP-TOILETRIES",  # List I 54 "(Toiletries are not payable ...)"
    "NP-ATTENDANT-FOOD",  # List I 9 "FOOD CHARGES (OTHER THAN PATIENT's DIET ...)"; 24 "ATTENDANT CHARGES"
    "NP-TELEPHONE",  # List I 14 "TELEPHONE CHARGES"
    "NP-DIAPER",  # List I 17 "DIAPER OF ANY TYPE"
    "NP-THERMOMETER",  # List I 41 "THERMOMETER"
    "NP-CREPE-BANDAGE",  # List I 16 "CREPE BANDAGE"
    "NP-SHOE-COVER",  # List II 3 "SHOE COVER"
    "NP-ALCOHOL-SWABS",  # List IV 15 "ALCOHOL SWABES"
    "NP-URINE-BAG",  # List IV 18 "URINE BAG"
    "NP-LAUNDRY",  # List I 11 "LAUNDRY CHARGES"
    "NP-MINERAL-WATER",  # List I 12 "MINERAL WATER"
    "NP-TELEVISION",  # List I 22 "TELEVISION CHARGES"
    "NP-HOUSEKEEPING",  # List II 22 "HOUSE KEEPING CHARGES"
    "NP-AC-CHARGES",  # List II 23 "AIR CONDITIONER CHARGES"
    "NP-PULSE-OXIMETER",  # List II 37 "PULSEOXYMETER CHARGES"
    "NP-FILE-OPENING",  # List II 34 "FILE OPENING CHARGES"
    "NP-DOCUMENTATION",  # List II 29 "DOCUMENTATION CHARGES / ADMINISTRATIVE EXPENSES"
    "NP-DISCHARGE-PROCEDURE",  # List II 30 "DISCHARGE PROCEDURE CHARGES"
    "NP-VISITOR-PASS",  # List II 32 "ENTRANCE PASS / VISITORS PASS CHARGES"
)

# Excl14: supplements bought without a prescription, "unless prescribed by a
# medical practitioner as part of hospitalization". The bill lines say they were not.
DIETARY_SUPPLEMENTS: tuple[str, ...] = ("EX-MULTIVITAMIN-OTC", "EX-PROTEIN-SUPPLEMENT")

# 4.1.1.iv covers "All the day care treatments", with no list. Definition 3.12:
# treatment under general or local anaesthesia, completed in under 24 hours
# because of technological advancement, that would otherwise need more than 24
# hours in hospital; not treatment normally taken as an out-patient. These are
# the catalogue procedures that meet it. Short stays are only ever sampled for
# these (payable) or for medical admissions with no procedure (not payable), so no
# case turns on a procedure whose day-care status is arguable.
DAY_CARE_PROCEDURES: tuple[str, ...] = (
    "PX-CRIF-RADIUS",  # closed reduction and K-wire fixation, under anaesthesia
    "PX-HAEMORRHOIDECTOMY",
    "PX-HERNIA-REPAIR",
    "PX-LITHOTRIPSY",
    "PX-PHACO",
    "PX-RHINOPLASTY-RECONSTRUCTIVE",
    "PX-TONSILLECTOMY",
)

TERMS = ProductTerms(
    product_id=PRODUCT_ID,
    source=SOURCE,
    # 6.2 (Excl03): 30 days from first commencement, "except claims arising due to an accident".
    initial_wait=Wait(duration=Duration(value=30, unit=DurationUnit.DAYS), accident_exempt=True),
    # 6.3.a (Excl02): "This exclusion shall not be applicable for claims arising due to an accident."
    specific_wait=SpecificWait(groups=SPECIFIED_DISEASES, accident_exempt=True),
    # 6.1.a (Excl01): 36 months of continuous coverage after inception of the first policy.
    ped_wait=_months(36),
    exclusions=EXCLUSIONS,
    # 4.2: inpatient AYUSH treatment "up to the limit of sum insured ... in any AYUSH Hospital".
    ayush=Ayush(covered=True, requires_ayush_hospital=True, cap=None),
    # 4.1.1 note 1 and definition 3.19: at least 24 consecutive hours, except day care.
    min_stay_hours=24,
    day_care_procedures=DAY_CARE_PROCEDURES,
    # 7.III.4 lists 14 documents. Three are rendered: claim form (i), itemised bills
    # (iv) and discharge summary (vi). The agent brief says intake checked the rest.
    required_documents=ALL_DOCUMENTS,
    pre_hospitalisation_days=30,  # 4.4
    post_hospitalisation_days=60,  # 4.5
    line_exclusions=(
        LineExclusion(clause_id=C.NON_PAYABLE, item_codes=NON_PAYABLE_ITEMS),  # 4.7, Annexure A
        LineExclusion(clause_id=C.DIETARY_SUPPLEMENTS, item_codes=DIETARY_SUPPLEMENTS),  # Excl14
    ),
    # 4.1.i: "Room Rent, Boarding, Nursing Expenses ... up to 2% of the sum insured
    # subject to maximum of Rs. 5000/-, per day"; "all inclusive" in the table of
    # benefits. Nursing is therefore counted in the daily room rate.
    room_cap=Cap(rupees=5_000, bp_of_si=200),
    room_rate_includes=(BillCategory.NURSING,),
    # 4.1.1 note 2: above the limit, "all other expenses incurred at the Hospital,
    # with the exception of cost of pharmacy, consumables, implants, medical devices
    # and diagnostics" are paid in the same proportion.
    room_associated=(
        BillCategory.ADMIN,
        BillCategory.ANAESTHETIST,
        BillCategory.CONSULTANT,
        BillCategory.OT,
        BillCategory.OTHER,
        BillCategory.SURGEON,
    ),
    # 4.1.ii: ICU / ICCU "up to 5% of sum insured subject to maximum of Rs 10,000/- per day".
    icu_cap=Cap(rupees=10_000, bp_of_si=500),
    # 4.1.1 note 3: "Proportionate deductions is not applicable" above the ICU limit.
    icu_associated=(),
    sublimits=(
        # 4.3: "25% of Sum Insured or Rs. 40,000/-, whichever is lower, per each eye in one policy year".
        Sublimit(
            name="Cataract, per eye",
            match=Match(icd10_prefixes=("H25", "H26", "H28", "Q12.0"), procedure_codes=("PX-PHACO",)),
            cap_per_unit=Cap(rupees=40_000, bp_of_si=2_500),
        ),
    ),
)

AROGYA_SANJEEVANI = ProductProfile(
    product_id=PRODUCT_ID,
    source=SOURCE,
    # Arogya Sanjeevani is IRDAI's standard product and every insurer sells it under
    # that name, so the name is the product's, not a company's. The company, its
    # address and the UIN below are invented: the rules are modelled from a real
    # wording, but no document in this dataset is issued in a real insurer's name.
    product_name="Arogya Sanjeevani Policy",
    insurer="Sanchit Bharat General Insurance Company Limited",
    insurer_address="Sanchit House, 4th Floor, Plot 22, Bandra Kurla Complex, Mumbai 400 051",
    uin="SBGIHLIP26001V012627",
    # The wording leaves the amount to the policy schedule. Common Arogya Sanjeevani
    # sums insured; each case's certificate states its own.
    sum_insured_options=(1_00_000, 2_00_000, 3_00_000, 5_00_000),
    copay_options_bp=(),
    # 7.III.5: "Each and every claim ... shall be subject to a Copayment of 5%".
    mandatory_copay_bp=500,
    deductible_options=(),
    # 5: 5% of sum insured per claim-free year, up to 50%.
    bonus_step_bp=500,
    bonus_max_bp=5_000,
    policy_prefix="ASP",
    launched=dt.date(2020, 4, 1),  # IRDAI required every insurer to offer it from 1 April 2020
    build_terms=lambda sum_insured: TERMS,
    substitutes={
        "deductible_only": "ayush_covered",  # no deductible; AYUSH is covered up to the sum insured
        "sublimit_deductible_copay": "room_rent_exclusion_copay",  # no deductible
        "si_exhausted": "icu_breach",  # every claim has co-pay, and co-pay vs the SI limit is open
        "ayush_capped": "room_rent_breach",  # AYUSH has no limit of its own
    },
    ambiguities=(
        ambiguity.bonus_in_percentage_limits,  # definition 3.52 puts cumulative bonus in Sum Insured
        ambiguity.copay_after_sum_insured,  # 7.III.5 "claim amount admissible and payable"
        ambiguity.room_limit_with_icu_stay,  # 4.1.1 note 2 "all other expenses"
        ambiguity.room_limit_with_pre_post_bills,  # 4.1.1 note 2 "incurred at the Hospital"
        ambiguity.pre_post_with_day_care,  # 4.4 / 4.5 "hospitalization requiring inpatient care"
        ambiguity.sublimit_with_pre_post,  # 4.3 "expenses incurred for treatment of Cataract"
        ambiguity.room_limit_on_ayush,  # 4.2 "up to the limit of sum insured"
    ),
)
