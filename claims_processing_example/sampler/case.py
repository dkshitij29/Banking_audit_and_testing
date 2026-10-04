"""case.json: one benchmark case. The scorer sees it; the agent never does.

The sampler writes everything except `documents` and the render fields of
`provenance`, which the renderer fills in at build step 4. Nothing the sampler
writes carries a timestamp, so a seed always gives the same bytes.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from engine.schema import Claim, Decision, Policy
from sampler.difficulty import Difficulty, Placement


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


class Provenance(_Model):
    generator_version: str
    engine_version: str
    ruleset_hash: str
    """Digest of the engine's rule code and this case's product terms."""
    terms_source: str
    """The wording the terms come from, or UNVERIFIED_PLACEHOLDER."""
    sampling_attempts: int
    """Draws it took to build a case the scenario was aimed at."""
    redraws: tuple[str, ...]
    """Why each earlier draw was discarded: the scenario missed, could not be built,
    or depended on a reading the wording leaves open (sampler/ambiguity.py)."""
    render_model: str | None = None
    rendered_at: str | None = None


class Case(_Model):
    case_id: str
    seed: int
    product_id: str
    difficulty: Difficulty
    scenario: str
    """What the sampler aimed for: the scheduled scenario, or the product's
    substitute for it. The gold answer is the engine's, never this."""
    scenario_tags: tuple[str, ...]
    policy: Policy
    claim: Claim
    gold: Decision
    placement: Placement
    """Which documents must state each fact the gold answer depends on."""
    documents: tuple[str, ...] = ()
    provenance: Provenance
