"""Synthetic clinical and administrative vocabulary the sampler draws from.

Everything here is invented or generic. Person names are random pairings of
common Indian given names and surnames; hospital names are composed from word
lists; registration and policy numbers are random. Nothing comes from a real
registry, claim or person (CLAUDE.md invariant 5).

Diagnoses use WHO ICD-10 codes. Procedure codes (PX-...) and bill item codes are
this project's own vocabulary; product profiles list the same codes.

Prices are rough ranges for a private hospital in an Indian tier-2 city, in
whole rupees. They only need to be plausible: the engine, not these numbers,
decides every answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.schema import BillCategory, Cause, Gender, TreatmentSystem

Range = tuple[int, int]


@dataclass(frozen=True)
class ProcedureSpec:
    code: str
    plain: str
    clinical: str
    units: Range = (1, 1)
    """How many can be done in one admission (eyes, joints)."""


@dataclass(frozen=True)
class BillSpec:
    """Which charges a condition's bill carries, as price ranges."""

    surgeon: Range | None = None
    anaesthetist_pct: Range | None = None
    """Anaesthetist's fee as a percentage of the surgeon's fee."""
    ot: Range | None = None
    implant: tuple[str, int, int] | None = None
    """(description, price per unit low, high)."""
    consultant_per_day: Range = (600, 1_200)
    pharmacy_per_day: Range = (800, 2_500)
    investigations: Range = (2_000, 8_000)
    nursing_per_day: Range = (400, 1_000)
    therapy_per_day: tuple[str, int, int] | None = None
    """AYUSH therapy sessions: (description, per day low, high)."""


@dataclass(frozen=True)
class Condition:
    key: str
    icd10: str
    plain: str
    """How a claim form or a lay summary would name it."""
    clinical: tuple[str, ...]
    """How a discharge summary would put it; the hard tier uses these."""
    cause: Cause
    stay_days: Range
    ages: Range
    bill: BillSpec
    procedure: ProcedureSpec | None = None
    day_care: bool = False
    """Usually done in under 24 hours."""
    icu_days: Range = (0, 0)
    sex: Gender | None = None
    systems: tuple[TreatmentSystem, ...] = (TreatmentSystem.ALLOPATHY,)
    ped: str | None = None
    """Key in PEDS of the pre-existing disease this is a complication of."""
    mechanisms: tuple[str, ...] = ()
    """How an accident happened, as a discharge summary would say it. Accidents
    only: the renderer states one rather than inventing it."""


MEDICAL = BillSpec()
MEDICAL_HEAVY = BillSpec(consultant_per_day=(900, 1_800), pharmacy_per_day=(2_500, 6_000), investigations=(8_000, 20_000))


def surgical(surgeon: Range, ot: Range, implant: tuple[str, int, int] | None = None, **extra) -> BillSpec:
    return BillSpec(surgeon=surgeon, anaesthetist_pct=(20, 30), ot=ot, implant=implant, **extra)


def ayush(therapy: str) -> BillSpec:
    return BillSpec(
        consultant_per_day=(400, 900),
        pharmacy_per_day=(300, 900),
        investigations=(500, 2_500),
        nursing_per_day=(200, 500),
        therapy_per_day=(therapy, 900, 2_500),
    )


ILL, ACC = Cause.ILLNESS, Cause.ACCIDENT
AYURVEDA, HOMEOPATHY = TreatmentSystem.AYURVEDA, TreatmentSystem.HOMEOPATHY

CONDITIONS: dict[str, Condition] = {
    c.key: c
    for c in (
        # ------------------------------------------------ medical
        Condition("pneumonia", "J18.9", "Pneumonia",
                  ("Community-acquired pneumonia, right lower lobe", "Lobar pneumonia with consolidation"),
                  ILL, (3, 7), (2, 85), MEDICAL, icu_days=(0, 2)),
        Condition("dengue", "A90", "Dengue fever",
                  ("NS1-positive dengue fever with thrombocytopenia", "Dengue fever with warning signs"),
                  ILL, (3, 6), (5, 70), MEDICAL),
        Condition("typhoid", "A01.0", "Typhoid fever",
                  ("Enteric fever, blood culture positive for Salmonella Typhi",),
                  ILL, (4, 7), (5, 70), MEDICAL),
        Condition("gastroenteritis", "A09.0", "Acute gastroenteritis",
                  ("Acute infectious gastroenteritis with moderate dehydration",),
                  ILL, (1, 3), (2, 85), MEDICAL),
        Condition("uti", "N39.0", "Urinary tract infection",
                  ("Culture-positive urinary tract infection (E. coli)",),
                  ILL, (2, 5), (15, 85), MEDICAL),
        Condition("pancreatitis", "K85.9", "Acute pancreatitis",
                  ("Acute interstitial oedematous pancreatitis",),
                  ILL, (4, 8), (25, 75), MEDICAL_HEAVY, icu_days=(0, 2)),
        Condition("cellulitis", "L03.1", "Cellulitis of the leg",
                  ("Cellulitis of the left lower limb with lymphangitis",),
                  ILL, (3, 6), (15, 85), MEDICAL),
        Condition("asthma", "J45.9", "Asthma attack",
                  ("Acute severe exacerbation of bronchial asthma",),
                  ILL, (2, 4), (10, 75), MEDICAL, ped="asthma"),
        Condition("diabetic_foot", "E11.5", "Diabetic foot infection",
                  ("Type 2 diabetes mellitus with peripheral angiopathy and infected foot ulcer",),
                  ILL, (4, 9), (40, 85), MEDICAL_HEAVY, ped="diabetes"),
        Condition("hypertensive_hf", "I11.0", "Heart failure due to high blood pressure",
                  ("Hypertensive heart disease with congestive heart failure",),
                  ILL, (4, 8), (45, 85), MEDICAL_HEAVY, icu_days=(1, 2), ped="hypertension"),
        Condition("mi_ptca", "I21.9", "Heart attack",
                  ("Acute myocardial infarction, treated with angioplasty and stenting",),
                  ILL, (3, 6), (40, 80),
                  surgical((40_000, 80_000), (25_000, 50_000), ("Coronary stent", 25_000, 35_000)),
                  procedure=ProcedureSpec("PX-PTCA", "Angioplasty with stent",
                                          "Percutaneous transluminal coronary angioplasty with drug-eluting stent"),
                  icu_days=(1, 3)),
        Condition("cabg", "I25.1", "Coronary artery disease",
                  ("Triple vessel coronary artery disease",),
                  ILL, (6, 10), (45, 80),
                  surgical((1_20_000, 2_50_000), (60_000, 1_20_000), pharmacy_per_day=(4_000, 9_000),
                           investigations=(15_000, 35_000)),
                  procedure=ProcedureSpec("PX-CABG", "Bypass surgery", "Coronary artery bypass grafting"),
                  icu_days=(2, 4)),
        # ------------------------------------------------ surgical
        Condition("appendicitis", "K35.8", "Appendicitis",
                  ("Acute appendicitis with localised peritonitis",),
                  ILL, (2, 4), (10, 60), surgical((20_000, 40_000), (10_000, 25_000)),
                  procedure=ProcedureSpec("PX-LAP-APPENDICECTOMY", "Appendix removal",
                                          "Laparoscopic appendicectomy")),
        Condition("gallstones", "K80.2", "Gallstones",
                  ("Symptomatic cholelithiasis without cholecystitis",),
                  ILL, (2, 3), (25, 75), surgical((25_000, 45_000), (15_000, 30_000)),
                  procedure=ProcedureSpec("PX-LAP-CHOLECYSTECTOMY", "Gall bladder removal",
                                          "Laparoscopic cholecystectomy")),
        Condition("hernia", "K40.9", "Inguinal hernia",
                  ("Unilateral inguinal hernia without obstruction or gangrene",),
                  ILL, (1, 3), (20, 80), surgical((20_000, 40_000), (10_000, 20_000), ("Mesh", 5_000, 15_000)),
                  procedure=ProcedureSpec("PX-HERNIA-REPAIR", "Hernia repair", "Lichtenstein tension-free mesh hernioplasty")),
        Condition("haemorrhoids", "K64.9", "Piles",
                  ("Third-degree internal haemorrhoids",),
                  ILL, (1, 2), (25, 75), surgical((15_000, 30_000), (8_000, 15_000)),
                  procedure=ProcedureSpec("PX-HAEMORRHOIDECTOMY", "Piles surgery", "Stapled haemorrhoidopexy")),
        Condition("kidney_stone", "N20.0", "Kidney stone",
                  ("Left renal calculus, 11 mm, with hydronephrosis",),
                  ILL, (1, 2), (20, 70), surgical((20_000, 40_000), (10_000, 20_000)),
                  procedure=ProcedureSpec("PX-LITHOTRIPSY", "Stone breaking treatment",
                                          "Extracorporeal shock-wave lithotripsy"),
                  day_care=True),
        Condition("cataract", "H25.1", "Cataract",
                  ("Senile nuclear cataract", "Age-related nuclear sclerosis of the lens"),
                  ILL, (1, 1), (50, 85), surgical((12_000, 25_000), (5_000, 10_000), ("Intraocular lens", 8_000, 30_000),
                                                  pharmacy_per_day=(800, 2_000), investigations=(1_000, 3_000)),
                  procedure=ProcedureSpec("PX-PHACO", "Cataract surgery",
                                          "Phacoemulsification with foldable intraocular lens implant", units=(1, 2)),
                  day_care=True),
        Condition("knee_oa_tkr", "M17.1", "Knee arthritis",
                  ("Primary osteoarthritis of the right knee, Kellgren-Lawrence grade 4",),
                  ILL, (4, 7), (50, 85),
                  surgical((60_000, 1_20_000), (30_000, 60_000), ("Knee prosthesis", 80_000, 1_50_000)),
                  procedure=ProcedureSpec("PX-TKR", "Knee replacement", "Total knee arthroplasty")),
        Condition("tonsillitis", "J35.0", "Tonsillitis",
                  ("Chronic recurrent tonsillitis",),
                  ILL, (1, 1), (5, 30), surgical((15_000, 25_000), (8_000, 15_000)),
                  procedure=ProcedureSpec("PX-TONSILLECTOMY", "Tonsil removal", "Coblation tonsillectomy"),
                  day_care=True),
        Condition("fibroids", "D25.9", "Fibroids in the uterus",
                  ("Leiomyoma of uterus with menorrhagia",),
                  ILL, (3, 5), (35, 55), surgical((30_000, 60_000), (15_000, 30_000)),
                  procedure=ProcedureSpec("PX-HYSTERECTOMY", "Removal of the uterus",
                                          "Total laparoscopic hysterectomy"),
                  sex=Gender.FEMALE),
        # ------------------------------------------------ accidents
        Condition("tibia_fracture", "S82.2", "Broken shin bone",
                  ("Closed fracture of the shaft of the tibia",),
                  ACC, (3, 6), (10, 80),
                  surgical((35_000, 60_000), (15_000, 30_000), ("Intramedullary nail", 15_000, 40_000)),
                  procedure=ProcedureSpec("PX-ORIF-TIBIA", "Fracture fixation",
                                          "Open reduction and internal fixation of the tibia"),
                  mechanisms=("a road traffic accident", "a fall from a two-wheeler",
                              "a fall while crossing the road", "a fall at a construction site")),
        Condition("femur_neck_fracture", "S72.0", "Broken hip",
                  ("Displaced intracapsular fracture of the neck of the femur",),
                  ACC, (5, 8), (55, 85),
                  surgical((70_000, 1_20_000), (30_000, 60_000), ("Hip prosthesis", 80_000, 1_50_000)),
                  procedure=ProcedureSpec("PX-THR", "Hip replacement", "Total hip arthroplasty"),
                  mechanisms=("a fall at home", "a fall on a wet floor", "a fall from a two-wheeler",
                              "a fall down a flight of stairs", "a road traffic accident")),
        Condition("radius_fracture", "S52.5", "Broken wrist",
                  ("Distal radius fracture (Colles' type)",),
                  ACC, (1, 2), (8, 80), surgical((10_000, 20_000), (5_000, 10_000), ("K-wires", 1_500, 3_000)),
                  procedure=ProcedureSpec("PX-CRIF-RADIUS", "Wrist fracture fixation",
                                          "Closed reduction and percutaneous K-wire fixation of the distal radius"),
                  mechanisms=("a fall on an outstretched hand", "a fall at home", "a fall while playing",
                              "a fall from a two-wheeler")),
        Condition("head_injury", "S06.0", "Head injury",
                  ("Concussion with brief loss of consciousness",),
                  ACC, (1, 3), (5, 80), BillSpec(investigations=(6_000, 14_000)),
                  mechanisms=("a fall at home", "a road traffic accident", "a fall from a bicycle",
                              "a blow to the head during a fall")),
        Condition("nasal_fracture_reconstruction", "S02.2", "Broken nose, repaired",
                  ("Comminuted fracture of the nasal bones, post-traumatic deformity",),
                  ACC, (1, 2), (18, 60), surgical((40_000, 80_000), (15_000, 30_000)),
                  procedure=ProcedureSpec("PX-RHINOPLASTY-RECONSTRUCTIVE", "Nose reconstruction",
                                          "Post-traumatic reconstructive septorhinoplasty"),
                  mechanisms=("a road traffic accident", "a fall from a two-wheeler",
                              "a blow to the face during a fall", "an injury sustained while playing")),
        # ------------------------------------------------ usually excluded
        Condition("cosmetic_rhinoplasty", "M95.0", "Nose reshaping",
                  ("Acquired deformity of the nose, dorsal hump",),
                  ILL, (1, 2), (18, 45), surgical((40_000, 80_000), (15_000, 30_000)),
                  procedure=ProcedureSpec("PX-COSMETIC-RHINOPLASTY", "Nose job", "Aesthetic rhinoplasty")),
        Condition("myopia_lasik", "H52.1", "Short-sightedness (-4.5 dioptres)",
                  ("Bilateral myopia, -4.5 dioptres",),
                  ILL, (1, 1), (20, 40), surgical((25_000, 50_000), (5_000, 10_000)),
                  procedure=ProcedureSpec("PX-LASIK", "Laser eye surgery", "Laser-assisted in situ keratomileusis"),
                  day_care=True),
        Condition("infertility_ivf", "N97.9", "Infertility treatment",
                  ("Primary female infertility",),
                  ILL, (1, 2), (25, 40), surgical((80_000, 1_50_000), (10_000, 20_000)),
                  procedure=ProcedureSpec("PX-IVF", "IVF", "In vitro fertilisation with embryo transfer"),
                  sex=Gender.FEMALE),
        # ------------------------------------------------ AYUSH
        Condition("ra_ayurveda", "M06.9", "Rheumatoid arthritis",
                  ("Seropositive rheumatoid arthritis (Amavata)",),
                  ILL, (7, 14), (30, 75), ayush("Panchakarma therapy"), systems=(AYURVEDA,)),
        Condition("back_pain_ayush", "M54.5", "Low back pain",
                  ("Chronic mechanical low back pain (Kati shoola)",),
                  ILL, (5, 10), (25, 75), ayush("Kati basti therapy"), systems=(AYURVEDA, HOMEOPATHY)),
        Condition("psoriasis_ayurveda", "L40.0", "Psoriasis",
                  ("Chronic plaque psoriasis (Ekakushtha)",),
                  ILL, (7, 14), (18, 70), ayush("Virechana therapy"), systems=(AYURVEDA,)),
    )
}

# Declared pre-existing diseases, with the ICD-10 prefixes that count as the
# condition and its direct complications.
PEDS: dict[str, tuple[str, tuple[str, ...], str]] = {
    # key: (name as declared, prefixes, code of the condition itself, for comorbidity lists)
    "diabetes": ("Type 2 diabetes mellitus", ("E11",), "E11.9"),
    "hypertension": ("Hypertension", ("I10", "I11", "I12", "I13"), "I10"),
    "hypothyroidism": ("Hypothyroidism", ("E03",), "E03.9"),
    "asthma": ("Bronchial asthma", ("J45",), "J45.9"),
    "dyslipidaemia": ("Dyslipidaemia", ("E78",), "E78.5"),
}

ROOM_CATEGORIES: tuple[tuple[str, int, int], ...] = (
    ("General ward", 1_200, 2_500),
    ("Twin sharing", 2_500, 4_500),
    ("Single private AC", 4_500, 8_000),
    ("Deluxe room", 8_000, 14_000),
)

ICU_RATES: Range = (5_000, 25_000)

# Descriptions and categories for the bill items product lists name. Any
# admission can carry these, so none is specific to surgery or to one condition.
ITEMS: dict[str, tuple[str, BillCategory]] = {
    "NP-GLOVES": ("Surgical gloves", BillCategory.CONSUMABLE),
    "NP-MASK": ("Face masks", BillCategory.CONSUMABLE),
    "NP-ADMISSION-KIT": ("Admission kit", BillCategory.CONSUMABLE),
    "NP-REGISTRATION": ("Registration charges", BillCategory.ADMIN),
    "NP-TOILETRIES": ("Toiletries", BillCategory.CONSUMABLE),
    "NP-ATTENDANT-FOOD": ("Attendant food charges", BillCategory.OTHER),
    "NP-TELEPHONE": ("Telephone charges", BillCategory.ADMIN),
    "NP-DIAPER": ("Adult diapers", BillCategory.CONSUMABLE),
    "NP-THERMOMETER": ("Digital thermometer", BillCategory.CONSUMABLE),
    "NP-CREPE-BANDAGE": ("Crepe bandage", BillCategory.CONSUMABLE),
    "NP-SHOE-COVER": ("Shoe covers", BillCategory.CONSUMABLE),
    "NP-ALCOHOL-SWABS": ("Alcohol swabs", BillCategory.CONSUMABLE),
    "NP-URINE-BAG": ("Urine bag", BillCategory.CONSUMABLE),
    "NP-LAUNDRY": ("Laundry charges", BillCategory.OTHER),
    "NP-MINERAL-WATER": ("Mineral water", BillCategory.OTHER),
    "NP-TELEVISION": ("Television charges", BillCategory.OTHER),
    "NP-HOUSEKEEPING": ("Housekeeping charges", BillCategory.OTHER),
    "NP-AC-CHARGES": ("Air conditioner charges", BillCategory.OTHER),
    "NP-PULSE-OXIMETER": ("Pulse oximeter charges", BillCategory.OTHER),
    "NP-FILE-OPENING": ("File opening charges", BillCategory.ADMIN),
    "NP-DOCUMENTATION": ("Documentation charges", BillCategory.ADMIN),
    "NP-DISCHARGE-PROCEDURE": ("Discharge procedure charges", BillCategory.ADMIN),
    "NP-VISITOR-PASS": ("Visitor pass charges", BillCategory.ADMIN),
    "EX-PROTEIN-SUPPLEMENT": ("Protein supplement powder (over the counter, not prescribed)", BillCategory.PHARMACY),
    "EX-MULTIVITAMIN-OTC": ("Multivitamin tablets (over the counter, not prescribed)", BillCategory.PHARMACY),
}

GIVEN_NAMES = {
    Gender.FEMALE: ("Aarti", "Ananya", "Bhavna", "Deepa", "Divya", "Farah", "Gauri", "Ishita", "Jyoti", "Kavita",
                    "Lakshmi", "Meera", "Nandini", "Pooja", "Priya", "Rekha", "Sana", "Shalini", "Sunita", "Tanvi",
                    "Usha", "Vandana", "Yamini", "Zoya"),
    Gender.MALE: ("Aakash", "Amit", "Arjun", "Deepak", "Farhan", "Gaurav", "Harish", "Imran", "Karan", "Manoj",
                  "Nikhil", "Pranav", "Rahul", "Rajesh", "Rohan", "Sanjay", "Suresh", "Tarun", "Varun", "Vikram",
                  "Yash", "Zubin"),
}
SURNAMES = ("Agarwal", "Bhat", "Chatterjee", "Das", "Desai", "Fernandes", "Gupta", "Iyer", "Joshi", "Kapoor", "Khan",
            "Kulkarni", "Menon", "Mishra", "Nair", "Pandey", "Patel", "Pillai", "Rao", "Reddy", "Saxena", "Sharma",
            "Shetty", "Singh", "Sinha", "Verma")

# (city, state medical council prefix for doctors' registration numbers)
CITIES = (("Pune", "MMC"), ("Nagpur", "MMC"), ("Nashik", "MMC"), ("Indore", "MPMC"), ("Bhopal", "MPMC"),
          ("Jaipur", "RMC"), ("Lucknow", "UPMC"), ("Kanpur", "UPMC"), ("Kochi", "TCMC"), ("Coimbatore", "TNMC"),
          ("Madurai", "TNMC"), ("Mysuru", "KMC"), ("Visakhapatnam", "APMC"), ("Vadodara", "GMC"), ("Surat", "GMC"),
          ("Bhubaneswar", "OCMR"), ("Guwahati", "AMC"), ("Chandigarh", "PMC"), ("Dehradun", "UKMC"))

HOSPITAL_WORDS = ("Amaltas", "Arogyam", "Chandrika", "Devika", "Harshal", "Kalpataru", "Nirmiti", "Pranjal", "Saanvi",
                  "Shravasti", "Suryoday", "Tejaswini", "Vasundhara", "Yashodhan")
HOSPITAL_KINDS = ("Multispeciality Hospital", "Hospital", "Nursing Home", "Medical Centre", "Superspeciality Hospital")
