"""Product profiles: everything the sampler needs to know about a product.

A profile turns a sampled sum insured into the ProductTerms embedded in each
policy, and says which policy-level options the product offers (sums insured,
co-pay, deductible, cumulative bonus). Real profiles live in sampler/products/,
one module per policy wording, hand-extracted at build step 3 with each value's
source in corpus/mapping.yaml. sampler.products.PROFILES lists them all.

PLACEHOLDER below is UNVERIFIED: its lists come from engine/tables.py and its
numbers are deliberately unrealistic. Any dataset built from it is practice
data and must never be released.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from engine import clauses as C
from engine import tables
from engine.schema import (
    ALL_DOCUMENTS,
    Ayush,
    Cap,
    ConditionGroup,
    Duration,
    DurationUnit,
    Exclusion,
    LineExclusion,
    ProductTerms,
    SpecificWait,
    Sublimit,
    Wait,
)
from sampler.ambiguity import Guard


@dataclass(frozen=True)
class ProductProfile:
    product_id: str
    source: str
    """A wording reference, or tables.PLACEHOLDER_SOURCE."""
    product_name: str
    """The product as its documents name it."""
    insurer: str
    """An invented insurer. The rules come from a real wording (see source), but no
    document in this dataset is issued in a real company's name."""
    insurer_address: str
    uin: str
    """An invented UIN, in the shape IRDAI uses. Never a real filing's number."""
    sum_insured_options: tuple[int, ...]
    copay_options_bp: tuple[int, ...]
    """Co-pay a policy may carry when a scenario calls for one. Empty: the product has none."""
    mandatory_copay_bp: int
    """Co-pay on every claim (e.g. a standard product's flat co-pay); 0 if none."""
    deductible_options: tuple[int, ...]
    """Empty: the product offers no deductible."""
    bonus_step_bp: int
    """Cumulative bonus per claim-free year, as a share of sum insured."""
    bonus_max_bp: int
    policy_prefix: str
    """For synthetic policy numbers."""
    launched: dt.date | None
    """When the product went on sale: a policy renewed every year since it began
    starts no earlier. Older continuous cover can only be ported in."""
    build_terms: Callable[[int], ProductTerms]
    """Terms for a given sum insured (some products set limits by sum-insured band)."""
    substitutes: Mapping[str, str]
    """Scenario to build in place of a scheduled one the product cannot give (no
    deductible, say). A substitute aims at the same verdict, so the mix holds."""
    ambiguities: tuple[Guard, ...]
    """Guards for readings this wording leaves open (sampler/ambiguity.py), on top
    of the ones every product gets."""

    @property
    def releasable(self) -> bool:
        return self.source != tables.PLACEHOLDER_SOURCE

    def terms(self, sum_insured: int) -> ProductTerms:
        return self.build_terms(sum_insured)


def _days(n: int) -> Duration:
    return Duration(value=n, unit=DurationUnit.DAYS)


def _placeholder_terms(sum_insured: int) -> ProductTerms:
    """UNVERIFIED PLACEHOLDER. Every number here is made up."""
    return ProductTerms(
        product_id="PLACEHOLDER",
        source=tables.PLACEHOLDER_SOURCE,
        initial_wait=Wait(duration=_days(100), accident_exempt=True),
        specific_wait=SpecificWait(
            groups=tuple(
                ConditionGroup(name=name, match=match, duration=_days(500))
                for name, match in tables.PLACEHOLDER_SPECIFIC_CONDITIONS.items()
            ),
            accident_exempt=True,
        ),
        ped_wait=_days(1_000),
        exclusions=tuple(
            Exclusion(clause_id=clause_id, match=match)
            for clause_id, match in tables.PLACEHOLDER_EXCLUSIONS.items()
        ),
        ayush=Ayush(covered=True, requires_ayush_hospital=True, cap=Cap(rupees=20_000)),
        min_stay_hours=24,
        day_care_procedures=tables.PLACEHOLDER_DAY_CARE_PROCEDURES,
        required_documents=ALL_DOCUMENTS,
        pre_hospitalisation_days=50,
        post_hospitalisation_days=100,
        line_exclusions=(
            LineExclusion(clause_id=C.NON_PAYABLE, item_codes=tables.PLACEHOLDER_NON_PAYABLE_ITEMS),
            LineExclusion(clause_id=C.DIETARY_SUPPLEMENTS, item_codes=tables.PLACEHOLDER_DIETARY_SUPPLEMENTS),
        ),
        room_cap=Cap(rupees=5_000),
        room_rate_includes=(),
        room_associated=tables.PLACEHOLDER_ROOM_ASSOCIATED,
        icu_cap=Cap(rupees=10_000),
        icu_associated=tables.PLACEHOLDER_ICU_ASSOCIATED,
        sublimits=tuple(
            Sublimit(name=name, match=match, cap_per_unit=Cap(rupees=25_000))
            for name, match in tables.PLACEHOLDER_SUBLIMIT_CONDITIONS.items()
        ),
    )


PLACEHOLDER = ProductProfile(
    product_id="PLACEHOLDER",
    source=tables.PLACEHOLDER_SOURCE,
    product_name="Placeholder Health Policy",
    insurer="Placeholder General Insurance Company Limited",
    insurer_address="Nowhere",
    uin="PLACEHOLDERV000000",
    sum_insured_options=(2_00_000, 3_00_000, 5_00_000, 10_00_000),
    copay_options_bp=(1_000, 2_000),
    mandatory_copay_bp=0,
    deductible_options=(10_000, 25_000),
    bonus_step_bp=1_000,
    bonus_max_bp=5_000,
    policy_prefix="PH",
    launched=None,
    build_terms=_placeholder_terms,
    substitutes={},
    ambiguities=(),
)
