"""Clause ID registry: every clause ID the engine can emit, and nothing else.

Clause IDs are graded, so they are frozen. Never rename, renumber or delete one;
add a new ID instead. tests/test_clauses.py pins the full list.

Format: <section>_<slug>. Sections are the engine's own canonical numbering, not
the numbering of any particular policy wording; corpus/mapping.yaml records where
each rule actually appears in each wording.

  2.x  definitions (minimum stay, day-care)
  3.x  benefits and limits
  4.n  waiting periods and exclusions, numbered in the order of IRDAI's standard
       exclusion codes: 4.1 = Excl01 (pre-existing disease), 4.2 = Excl02
       (specified disease), 4.3 = Excl03 (30-day wait), ... 4.18 = Excl18.
       Titles to be confirmed against the first real wording at step 3.
  5.x  cost sharing and sum insured
  6.x  general conditions
  7.x  claim procedure
  A1   list of non-payable items

Descriptions are short and neutral. They say what a clause is about, never how
it resolves, and carry no product numbers. They will seed the clause list in the
agent brief (docs/AGENT_BRIEF.md, build step 8).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CLAUSE_ID_PATTERN = re.compile(r"^(?:\d+\.\d+|A\d+)_[a-z0-9]+(?:_[a-z0-9]+)*$")


@dataclass(frozen=True)
class Clause:
    id: str
    description: str


REGISTRY: dict[str, Clause] = {}


def _register(clause_id: str, description: str) -> str:
    if not CLAUSE_ID_PATTERN.match(clause_id):
        raise ValueError(f"malformed clause ID {clause_id!r}")
    if clause_id in REGISTRY:
        raise ValueError(f"duplicate clause ID {clause_id!r}")
    REGISTRY[clause_id] = Clause(clause_id, description)
    return clause_id


# 2 - definitions
MIN_HOSPITALISATION = _register("2.1_min_hospitalisation", "Minimum duration of hospitalisation")
DAY_CARE = _register("2.2_day_care", "Day-care treatment")

# 3 - benefits and limits
ROOM_RENT = _register("3.1_room_rent_limit", "Room rent limit and proportionate deduction")
ICU_LIMIT = _register("3.2_icu_limit", "ICU charges limit")
DISEASE_SUBLIMIT = _register("3.3_disease_sublimit", "Disease- or procedure-wise sub-limit")
AYUSH = _register("3.4_ayush", "AYUSH treatment")
PRE_HOSPITALISATION = _register("3.5_pre_hospitalisation", "Pre-hospitalisation expenses")
POST_HOSPITALISATION = _register("3.6_post_hospitalisation", "Post-hospitalisation expenses")

# 4 - waiting periods and exclusions
PED_WAITING = _register("4.1_ped_waiting", "Pre-existing disease waiting period")
SPECIFIC_WAITING = _register(
    "4.2_specific_disease_waiting", "Specified disease or procedure waiting period"
)
SPECIFIC_WAITING_ACCIDENT = _register(
    "4.2_accident_exception", "Accident exception to the specified disease waiting period"
)
INITIAL_WAITING = _register("4.3_initial_waiting", "Initial waiting period")
INITIAL_WAITING_ACCIDENT = _register(
    "4.3_accident_exception", "Accident exception to the initial waiting period"
)
INVESTIGATION = _register("4.4_investigation_evaluation", "Investigation and evaluation")
REST_CURE = _register("4.5_rest_cure_rehabilitation", "Rest cure, rehabilitation and respite care")
OBESITY = _register("4.6_obesity_weight_control", "Obesity and weight control")
CHANGE_OF_GENDER = _register("4.7_change_of_gender", "Change-of-gender treatment")
COSMETIC = _register("4.8_cosmetic_surgery", "Cosmetic or plastic surgery")
HAZARDOUS_SPORTS = _register("4.9_hazardous_sports", "Hazardous or adventure sports")
BREACH_OF_LAW = _register("4.10_breach_of_law", "Breach of law")
EXCLUDED_PROVIDERS = _register("4.11_excluded_providers", "Excluded providers")
SUBSTANCE_ABUSE = _register("4.12_substance_abuse", "Alcoholism, drug or substance abuse")
HYDROS_SPAS = _register("4.13_hydros_spas", "Health hydros, nature cure clinics and spas")
DIETARY_SUPPLEMENTS = _register(
    "4.14_dietary_supplements", "Dietary supplements and non-prescription substances"
)
REFRACTIVE_ERROR = _register("4.15_refractive_error", "Refractive error")
UNPROVEN_TREATMENTS = _register("4.16_unproven_treatments", "Unproven treatments")
STERILITY_INFERTILITY = _register("4.17_sterility_infertility", "Sterility and infertility")
MATERNITY = _register("4.18_maternity", "Maternity")

# 5 - cost sharing and sum insured
DEDUCTIBLE = _register("5.1_deductible", "Deductible")
COPAY = _register("5.2_copay", "Co-payment")
SUM_INSURED = _register("5.3_sum_insured", "Sum insured and cumulative bonus")

# 6 - general conditions
POLICY_PERIOD = _register("6.1_policy_period", "Policy period")

# 7 - claim procedure
MISSING_DOCUMENTS = _register("7.1_missing_documents", "Required claim documents")
DOCUMENT_MISMATCH = _register("7.2_document_mismatch", "Consistency of claim documents")

# A - annexures
NON_PAYABLE = _register("A1_non_payable_items", "List of non-payable items")

STANDARD_EXCLUSIONS: tuple[str, ...] = (
    INVESTIGATION,
    REST_CURE,
    OBESITY,
    CHANGE_OF_GENDER,
    COSMETIC,
    HAZARDOUS_SPORTS,
    BREACH_OF_LAW,
    EXCLUDED_PROVIDERS,
    SUBSTANCE_ABUSE,
    HYDROS_SPAS,
    DIETARY_SUPPLEMENTS,
    REFRACTIVE_ERROR,
    UNPROVEN_TREATMENTS,
    STERILITY_INFERTILITY,
    MATERNITY,
)
"""4.4-4.18: exclusions that can reject a whole claim or remove single bill lines."""
