"""PLACEHOLDER product lists. UNVERIFIED: nothing here comes from a real policy wording.

These exist so the engine can be built and tested before a wording is chosen.
Step 3 replaces them with lists read from real IRDAI wordings, with each list's
source section recorded in corpus/mapping.yaml. Anything built from these lists
must carry source=PLACEHOLDER_SOURCE, and nothing carrying it may be released.

Codes are this project's own vocabulary: procedures are "PX-...", bill items
"NP-..." (non-payable) or "EX-..." (excluded). Diagnoses use WHO ICD-10.

engine/rules.py never imports this module. Rules read every list from
policy.terms (tests/test_guards.py enforces this).
"""

from engine import clauses as C
from engine.schema import BillCategory, Match

PLACEHOLDER_SOURCE = "UNVERIFIED_PLACEHOLDER"

PLACEHOLDER_SPECIFIC_CONDITIONS: dict[str, Match] = {  # each group gets its own wait (4.2)
    "Cataract": Match(icd10_prefixes=("H25", "H26"), procedure_codes=("PX-PHACO",)),
    "Hernia": Match(
        icd10_prefixes=("K40", "K41", "K42", "K43", "K44", "K45", "K46"),
        procedure_codes=("PX-HERNIA-REPAIR",),
    ),
    "Haemorrhoids, fissure and fistula": Match(icd10_prefixes=("K60", "K64")),
    "Kidney and gall bladder stones": Match(
        icd10_prefixes=("K80", "N20"), procedure_codes=("PX-LAP-CHOLECYSTECTOMY", "PX-LITHOTRIPSY")
    ),
    "Joint replacement": Match(procedure_codes=("PX-THR", "PX-TKR")),
}

PLACEHOLDER_EXCLUSIONS: dict[str, Match] = {  # whole claim rejected
    C.COSMETIC: Match(procedure_codes=("PX-COSMETIC-RHINOPLASTY", "PX-LIPOSUCTION")),
    C.REFRACTIVE_ERROR: Match(icd10_prefixes=("H52",), procedure_codes=("PX-LASIK",)),
    C.STERILITY_INFERTILITY: Match(icd10_prefixes=("N46", "N97"), procedure_codes=("PX-IVF",)),
}

PLACEHOLDER_SUBLIMIT_CONDITIONS: dict[str, Match] = {  # each gets a cap per unit (3.3)
    "Cataract, per eye": Match(icd10_prefixes=("H25", "H26"), procedure_codes=("PX-PHACO",)),
}

PLACEHOLDER_DAY_CARE_PROCEDURES: tuple[str, ...] = (
    "PX-PHACO",  # cataract: phacoemulsification with lens implant
    "PX-LITHOTRIPSY",  # kidney stone: shock-wave lithotripsy
    "PX-CHEMOTHERAPY",  # one chemotherapy session
    "PX-HAEMODIALYSIS",  # one dialysis session
    "PX-TONSILLECTOMY",
)

PLACEHOLDER_NON_PAYABLE_ITEMS: tuple[str, ...] = (
    "NP-GLOVES",
    "NP-MASK",
    "NP-ADMISSION-KIT",
    "NP-REGISTRATION",
    "NP-TOILETRIES",
    "NP-ATTENDANT-FOOD",
    "NP-TELEPHONE",
)

PLACEHOLDER_DIETARY_SUPPLEMENTS: tuple[str, ...] = (  # removed line by line under 4.14
    "EX-PROTEIN-SUPPLEMENT",
    "EX-MULTIVITAMIN-OTC",
)

PLACEHOLDER_ROOM_ASSOCIATED: tuple[BillCategory, ...] = (
    BillCategory.NURSING,
    BillCategory.SURGEON,
    BillCategory.ANAESTHETIST,
    BillCategory.CONSULTANT,
    BillCategory.OT,
)

PLACEHOLDER_ICU_ASSOCIATED: tuple[BillCategory, ...] = ()  # only the ICU line itself is scaled
