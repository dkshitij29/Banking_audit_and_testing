"""sample_case(seed) -> Case: one benchmark case, byte-identical for a given seed.

    uv run python -m sampler.sample --name practice --count 500
    uv run python -m sampler.sample --name as --product AROGYA_SANJEEVANI_GCI

writes, under datasets/<name>/:
    cases/<case_id>/case.json   one per case
    index.jsonl                 one row per case: id, product, tier, tags, verdict, payable
    manifest.json               versions, ruleset hashes, seed range, counts and mixes

The gold answer in every case is engine.adjudicate's output, computed from the
structured policy and claim. The sampler never writes a label itself.

A draw is discarded, and the next one tried, when the engine's answer is not
what the scenario aimed for, or when it would change under a reading the wording
leaves open (sampler/ambiguity.py). provenance.redraws records why, and the
manifest counts the reasons.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

import engine
from engine import adjudicate
from engine import clauses as C
from engine.schema import BillCategory, Claim, Decision, ProductTerms, UnsupportedCase
from sampler import GENERATOR_VERSION, ambiguity, difficulty
from sampler.case import Case, Provenance
from sampler.difficulty import Difficulty, NotPlaceable
from sampler.products import PROFILES, REAL
from sampler.profiles import PLACEHOLDER, ProductProfile
from sampler.rng import Rng
from sampler.scenarios import SCENARIO_BY_NAME, SCHEDULE, Builder, NotRealisable, Scenario

MAX_ATTEMPTS = 80
ENGINE_FILES = ("rules.py", "schema.py", "clauses.py")

CLAUSE_TAGS = {
    C.ROOM_RENT: "room_rent_breach",
    C.ICU_LIMIT: "icu_breach",
    C.DISEASE_SUBLIMIT: "sublimit",
    C.AYUSH: "ayush",
    C.PRE_HOSPITALISATION: "outside_pre_window",
    C.POST_HOSPITALISATION: "outside_post_window",
    C.PED_WAITING: "within_ped_wait",
    C.SPECIFIC_WAITING: "within_specified_wait",
    C.INITIAL_WAITING: "within_initial_wait",
    C.INITIAL_WAITING_ACCIDENT: "accident_exception",
    C.SPECIFIC_WAITING_ACCIDENT: "accident_exception",
    C.DAY_CARE: "day_care",
    C.MIN_HOSPITALISATION: "short_stay",
    C.DEDUCTIBLE: "deductible",
    C.COPAY: "copay",
    C.SUM_INSURED: "sum_insured_exhausted",
    C.POLICY_PERIOD: "policy_not_in_force",
    C.MISSING_DOCUMENTS: "missing_document",
    C.DOCUMENT_MISMATCH: "document_mismatch",
    C.NON_PAYABLE: "non_payables",
}


class NotSampled(RuntimeError):
    """No draw realised the seed's scenario: a bug in the scenario, not bad luck."""


@functools.cache
def _engine_digest() -> bytes:
    root = Path(engine.__file__).parent
    digest = hashlib.sha256()
    for name in ENGINE_FILES:
        digest.update((root / name).read_bytes())
    return digest.digest()


def ruleset_hash(terms: ProductTerms) -> str:
    """Digest of the engine's rule code and the product terms: changes whenever
    either could change a gold answer."""
    return hashlib.sha256(_engine_digest() + terms.model_dump_json().encode()).hexdigest()[:16]


def _nursing_tipped_the_room(decision: Decision, claim: Claim) -> bool:
    """The room line alone was within the cap; the charges counted with it were not."""
    for step in decision.reasoning_trace:
        if step.fired_clause == C.ROOM_RENT and step.facts.get("rate_includes"):
            room = next(line for line in claim.bill if line.category is BillCategory.ROOM)
            return room.unit_price <= Fraction(str(step.facts["cap_per_day"]))
    return False


def tags_for(
    decision: Decision, terms: ProductTerms, scenario: Scenario, tier: Difficulty, claim: Claim
) -> tuple[str, ...]:
    line_level = {rule.clause_id for rule in terms.line_exclusions if rule.clause_id != C.NON_PAYABLE}
    fired = {step.fired_clause for step in decision.reasoning_trace if step.fired_clause}
    tags = set(scenario.tags)
    if _nursing_tipped_the_room(decision, claim):
        tags.add("charges_in_room_rate")
    for clause in fired:
        if clause in line_level:
            tags.add("excluded_items")
        elif clause in C.STANDARD_EXCLUSIONS:
            tags.add("permanent_exclusion")
        else:
            tags.add(CLAUSE_TAGS[clause])
    if tier is Difficulty.HARD:
        tags.add("clinical_diagnosis")
    if len(fired - {C.NON_PAYABLE}) >= 2:
        tags.add("multi_rule")
    return tuple(sorted(tags))


def sample_case(seed: int, profile: ProductProfile = PLACEHOLDER) -> Case:
    scheduled, tier = SCHEDULE[seed % len(SCHEDULE)]
    scenario = SCENARIO_BY_NAME[profile.substitutes.get(scheduled, scheduled)]
    guards = ambiguity.GENERAL + profile.ambiguities
    redraws: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        builder = Builder(Rng(seed, "case", str(attempt)), profile, tier)
        try:
            scenario.build(builder)
            policy, claim = builder.realise()
            decision = adjudicate(policy, claim)
            if not scenario.realised_by(decision, profile):
                redraws.append(f"missed: {decision.verdict.value} {' '.join(decision.clauses)}".rstrip())
                continue
            reason = ambiguity.first_reason(guards, policy, claim, decision)
            if reason is not None:
                redraws.append(f"ambiguous: {reason}")
                continue
            placement = difficulty.plan(decision, policy.terms, tier, claim.documents_submitted)
        except NotRealisable as error:
            redraws.append(f"unrealisable: {error}")
            continue
        except NotPlaceable as error:
            redraws.append(f"unplaceable: {error}")
            continue
        except UnsupportedCase as error:
            redraws.append(f"unsupported: {error}")
            continue
        return Case(
            case_id=f"case-{seed:06d}",
            seed=seed,
            product_id=profile.product_id,
            difficulty=tier,
            scenario=scenario.name,
            scenario_tags=tags_for(decision, policy.terms, scenario, tier, claim),
            policy=policy,
            claim=claim,
            gold=decision,
            placement=placement,
            provenance=Provenance(
                generator_version=GENERATOR_VERSION,
                engine_version=engine.ENGINE_VERSION,
                ruleset_hash=ruleset_hash(policy.terms),
                terms_source=policy.terms.source,
                sampling_attempts=attempt,
                redraws=tuple(redraws),
            ),
        )
    raise NotSampled(f"seed {seed}: scenario {scenario.name} ({tier}) not realised in {MAX_ATTEMPTS} draws")


def write_dataset(name: str, parts: Sequence[tuple[ProductProfile, range]], root: Path) -> Path:
    """Write cases, index and manifest under root/name.

    `parts` gives each product the block of seeds it is built from. A case ID comes
    from its seed, so the blocks must not overlap: one dataset then holds several
    products, as CLAUDE.md's output layout expects, and every case still regenerates
    to the same bytes on its own.
    """
    out = root / name
    seen: set[int] = set()
    for _, seeds in parts:
        if overlap := seen & set(seeds):
            raise ValueError(f"seeds {sorted(overlap)[:3]}... are used by two products")
        seen |= set(seeds)
    cases = [sample_case(seed, profile) for profile, seeds in parts for seed in seeds]
    for case in cases:
        path = out / "cases" / case.case_id / "case.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(case.model_dump_json(indent=2) + "\n", encoding="utf-8")

    rows = [
        {
            "case_id": case.case_id,
            "product_id": case.product_id,
            "difficulty": case.difficulty.value,
            "scenario_tags": list(case.scenario_tags),
            "verdict": case.gold.verdict.value,
            "payable": case.gold.payable,
            "clause_count": len(case.gold.clauses),
            "documents": list(case.documents),
        }
        for case in cases
    ]
    (out / "index.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    attempts = [case.provenance.sampling_attempts for case in cases]
    reasons = Counter(
        reason if reason.startswith("ambiguous") else reason.split(":")[0]
        for case in cases
        for reason in case.provenance.redraws
    )
    manifest = {
        "name": name,
        "generator_version": GENERATOR_VERSION,
        "engine_version": engine.ENGINE_VERSION,
        "ruleset_hashes": sorted({case.provenance.ruleset_hash for case in cases}),
        "terms_sources": sorted({case.provenance.terms_source for case in cases}),
        "releasable": all(profile.releasable for profile, _ in parts),
        "products": {
            profile.product_id: {
                "seeds": [seeds.start, seeds.stop],
                "cases": len(seeds),
                "source": profile.source,
                "insurer_on_the_documents": profile.insurer,
            }
            for profile, seeds in parts
        },
        "counts": {"cases": len(cases)},
        "tiers": dict(sorted(Counter(case.difficulty.value for case in cases).items())),
        "verdicts": dict(sorted(Counter(case.gold.verdict.value for case in cases).items())),
        "scenarios": dict(sorted(Counter(case.scenario for case in cases).items())),
        "substitutes": {profile.product_id: dict(sorted(profile.substitutes.items()))
                        for profile, _ in parts if profile.substitutes},
        "sampling": {
            "draws": sum(attempts),
            "redraws": sum(attempts) - len(cases),
            "redraw_reasons": dict(sorted(reasons.items())),
        },
        "render_discard_rate": None,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="dataset name (a folder under --out)")
    parser.add_argument("--count", type=int, default=500, help="cases per product")
    parser.add_argument("--start", type=int, default=0, help="first seed")
    parser.add_argument("--product", action="append", default=[], choices=sorted(PROFILES),
                        help="repeat for several products; each gets its own block of seeds")
    parser.add_argument("--release", action="store_true", help="every real product, in order")
    parser.add_argument("--out", type=Path, default=Path("datasets"))
    args = parser.parse_args(argv)

    chosen = list(REAL) if args.release else [PROFILES[name] for name in args.product or [PLACEHOLDER.product_id]]
    parts = [
        (profile, range(args.start + n * args.count, args.start + (n + 1) * args.count))
        for n, profile in enumerate(chosen)
    ]
    out = write_dataset(args.name, parts, args.out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    print(f"wrote {manifest['counts']['cases']} cases to {out}")
    for product_id, part in manifest["products"].items():
        print(f"  {product_id}: {part['cases']} cases, seeds {part['seeds'][0]}-{part['seeds'][1] - 1}")
    print(f"  verdicts {manifest['verdicts']}  tiers {manifest['tiers']}")
    if not manifest["releasable"]:
        print("  built from UNVERIFIED placeholder terms: practice data, never to be released")


if __name__ == "__main__":
    main()
