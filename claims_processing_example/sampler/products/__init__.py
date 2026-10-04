"""Product profiles by product_id: the placeholder, and one module per real wording."""

from sampler.products.arogya_sanjeevani import AROGYA_SANJEEVANI
from sampler.products.new_india_mediclaim import NEW_INDIA_MEDICLAIM
from sampler.profiles import PLACEHOLDER, ProductProfile

REAL: tuple[ProductProfile, ...] = (AROGYA_SANJEEVANI, NEW_INDIA_MEDICLAIM)
"""The products a release is built from, in the order they were modelled."""

PROFILES: dict[str, ProductProfile] = {profile.product_id: profile for profile in (PLACEHOLDER, *REAL)}
