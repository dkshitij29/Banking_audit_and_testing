"""The sampler: reproducible cases, the agreed mix, gold from the engine, honest tiers.

Dataset-level checks run on the first release (seeds 0-499) of every product profile.
"""

import functools
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from engine import adjudicate, tables
from engine import clauses as C
from engine.schema import DocType, Verdict
from sampler import ambiguity
from sampler.case import Case
from sampler.catalogue import CONDITIONS, GIVEN_NAMES, HOSPITAL_KINDS, HOSPITAL_WORDS, SURNAMES
from sampler.difficulty import CLAIM_FACTS, RESTATABLE_RULES, DiagnosisStyle, Difficulty, Doc
from sampler.products import PROFILES
from sampler.profiles import PLACEHOLDER
from sampler.sample import sample_case, write_dataset
from sampler.scenarios import SCENARIO_BY_NAME, SCENARIOS, SCHEDULE

ROOT = Path(__file__).resolve().parent.parent
FIRST_RELEASE = range(500)


@functools.cache
def first_release(product_id: str) -> tuple[Case, ...]:
    return tuple(sample_case(seed, PROFILES[product_id]) for seed in FIRST_RELEASE)


@pytest.fixture(params=sorted(PROFILES), ids=str.lower)
def profile(request):
    return PROFILES[request.param]


@pytest.fixture
def cases(profile):
    return first_release(profile.product_id)


# ---------------------------------------------------------------- reproducibility


@pytest.mark.parametrize("seed", [0, 1, 17, 42, 99, 123, 499])
def test_same_seed_gives_the_same_bytes(seed, profile):
    assert sample_case(seed, profile).model_dump_json() == sample_case(seed, profile).model_dump_json()


def test_bytes_are_identical_across_processes_and_hash_seeds():
    script = (
        "import sys\n"
        "from sampler.products import PROFILES\n"
        "from sampler.sample import sample_case\n"
        "for profile in PROFILES.values():\n"
        "    for seed in range(40):\n"
        "        sys.stdout.write(sample_case(seed, profile).model_dump_json() + '\\n')\n"
    )

    def run(hash_seed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
        return subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, encoding="utf-8", check=True
        ).stdout

    outputs = {seed: run(seed) for seed in ("0", "1", "4242")}
    assert outputs["0"].count("\n") == 40 * len(PROFILES)
    assert len(set(outputs.values())) == 1


def test_a_case_id_is_derived_from_its_seed(cases):
    assert [case.case_id for case in cases[:3]] == ["case-000000", "case-000001", "case-000002"]


def test_growing_the_dataset_never_changes_existing_cases(tmp_path):
    small = write_dataset("grow", [(PLACEHOLDER, range(10))], tmp_path / "a")
    large = write_dataset("grow", [(PLACEHOLDER, range(25))], tmp_path / "b")
    for seed in range(10):
        name = f"cases/case-{seed:06d}/case.json"
        assert (small / name).read_bytes() == (large / name).read_bytes()


def test_case_json_round_trips(cases):
    for case in cases[:25]:
        assert Case.model_validate_json(case.model_dump_json()) == case


# ---------------------------------------------------------------- gold comes from the engine


def test_gold_is_exactly_what_the_engine_decides(cases):
    for case in cases:
        assert adjudicate(case.policy, case.claim) == case.gold, case.case_id


def test_every_case_is_what_its_scenario_aimed_for(cases, profile):
    for case in cases:
        assert SCENARIO_BY_NAME[case.scenario].realised_by(case.gold, profile), case.case_id


def test_no_case_depends_on_a_reading_the_wording_leaves_open(cases, profile):
    guards = ambiguity.GENERAL + profile.ambiguities
    for case in cases:
        assert ambiguity.first_reason(guards, case.policy, case.claim, case.gold) is None, case.case_id


# ---------------------------------------------------------------- the agreed mix


def test_the_schedule_holds_the_agreed_mix_in_every_100_seeds():
    verdict_of = {scenario.name: scenario.verdict for scenario in SCENARIOS}
    assert len(SCHEDULE) == 100
    assert Counter(verdict_of[name] for name, _ in SCHEDULE) == {
        Verdict.APPROVE: 35, Verdict.PARTIAL: 40, Verdict.REJECT: 13, Verdict.ESCALATE: 12,
    }
    assert Counter(tier for _, tier in SCHEDULE) == {Difficulty.EASY: 34, Difficulty.MEDIUM: 33, Difficulty.HARD: 33}


def test_a_substitute_aims_at_the_same_verdict(profile):
    for scheduled, substitute in profile.substitutes.items():
        assert SCENARIO_BY_NAME[substitute].verdict is SCENARIO_BY_NAME[scheduled].verdict, scheduled


def test_the_first_release_has_the_agreed_mix(cases):
    assert Counter(case.gold.verdict for case in cases) == {
        Verdict.APPROVE: 175, Verdict.PARTIAL: 200, Verdict.REJECT: 65, Verdict.ESCALATE: 60,
    }
    assert Counter(case.difficulty for case in cases) == {
        Difficulty.EASY: 170, Difficulty.MEDIUM: 165, Difficulty.HARD: 165,
    }


def test_every_deliberate_hard_case_type_is_present(cases):
    tags = Counter(tag for case in cases for tag in case.scenario_tags)
    for tag in ("day_care_trap", "accident_exception", "exclusion_near_miss", "clinical_diagnosis",
                "partial_exclusion", "immaterial_conflict", "multi_rule", "missing_document", "document_mismatch"):
        assert tags[tag] >= 10, tag


def test_the_escalation_share_is_twelve_percent(cases):
    escalated = [case for case in cases if case.gold.verdict is Verdict.ESCALATE]
    assert len(escalated) / len(cases) == pytest.approx(0.12)
    assert all(set(case.gold.clauses) <= {C.MISSING_DOCUMENTS, C.DOCUMENT_MISMATCH} for case in escalated)


# ---------------------------------------------------------------- realism and honesty


def test_every_bill_carries_non_payable_items(cases):
    for case in cases:
        non_payable = next(r for r in case.policy.terms.line_exclusions if r.clause_id == C.NON_PAYABLE).item_codes
        assert any(line.item_code in non_payable for line in case.claim.bill), case.case_id


def test_hard_cases_keep_a_deciding_rule_in_the_wording_only(cases):
    clinical = {term for condition in CONDITIONS.values() for term in condition.clinical}
    for case in cases:
        if case.difficulty is not Difficulty.HARD:
            assert case.placement.wording_only == ()
            continue
        assert case.placement.wording_only, case.case_id
        for fact in case.placement.wording_only:
            assert case.placement.facts[fact] == (Doc.POLICY_WORDING,), (case.case_id, fact)
        assert case.placement.diagnosis_style is DiagnosisStyle.CLINICAL
        assert case.claim.primary_dx.term in clinical, case.case_id


def test_easy_cases_put_every_claim_fact_on_the_claim_form(cases):
    for case in cases:
        if case.difficulty is not Difficulty.EASY or DocType.CLAIM_FORM not in case.claim.documents_submitted:
            continue
        for fact, docs in case.placement.facts.items():
            if fact in CLAIM_FACTS:
                assert Doc.CLAIM_FORM in docs, (case.case_id, fact)


def test_easy_and_medium_cases_restate_their_rules_on_the_certificate(cases):
    for case in cases:
        if case.difficulty is Difficulty.HARD:
            continue
        for fact, docs in case.placement.facts.items():
            if fact in RESTATABLE_RULES:
                assert Doc.POLICY_CERTIFICATE in docs, (case.case_id, fact)


def test_no_fact_is_placed_in_a_document_that_was_not_submitted(cases):
    missing_to_doc = {DocType.CLAIM_FORM: Doc.CLAIM_FORM, DocType.DISCHARGE_SUMMARY: Doc.DISCHARGE_SUMMARY,
                      DocType.HOSPITAL_BILL: Doc.HOSPITAL_BILL}
    for case in cases:
        missing = {doc for kind, doc in missing_to_doc.items() if kind not in case.claim.documents_submitted}
        for docs in case.placement.facts.values():
            assert not missing & set(docs), case.case_id


def test_complications_of_a_known_disease_are_declared(cases):
    for case in cases:
        claimant = next(m for m in case.policy.members if m.member_id == case.claim.member_id)
        condition = next(c for c in CONDITIONS.values() if c.icd10 == case.claim.primary_dx.icd10)
        if condition.ped:
            assert claimant.declared_peds, case.case_id


def test_renewal_histories_start_no_earlier_than_the_product(cases, profile):
    if profile.launched is None:
        pytest.skip("the product has no launch date")
    for case in cases:
        claimant = next(m for m in case.policy.members if m.member_id == case.claim.member_id)
        anniversary = (claimant.first_inception.month, claimant.first_inception.day) == (
            case.policy.period_start.month, case.policy.period_start.day)
        if anniversary:
            assert claimant.first_inception >= profile.launched, case.case_id


def test_people_and_hospitals_come_only_from_the_synthetic_lists(cases):
    given_names = {name for names in GIVEN_NAMES.values() for name in names}
    for case in cases:
        for member in case.policy.members:
            first, last = member.name.split(" ")
            assert first in given_names and last in SURNAMES, member.name
        word, *kind = case.claim.hospital.name.split(" ")
        assert word in HOSPITAL_WORDS, case.claim.hospital.name
        if not case.claim.hospital.ayush_hospital:
            assert " ".join(kind) in HOSPITAL_KINDS, case.claim.hospital.name


def test_nursing_counted_in_the_room_rate_takes_rooms_over_the_limit():
    """The trap in a wording that caps room, boarding and nursing together: the
    room alone is within the limit, the rate with nursing is not."""
    product = next(p for p in PROFILES.values() if p.terms(p.sum_insured_options[0]).room_rate_includes)
    tagged = [case for case in first_release(product.product_id) if "charges_in_room_rate" in case.scenario_tags]
    assert len(tagged) >= 10
    for case in tagged:
        assert C.ROOM_RENT in case.gold.clauses, case.case_id


# ---------------------------------------------------------------- the dataset on disk


def test_placeholder_data_is_marked_and_never_releasable(tmp_path):
    out = write_dataset("practice", [(PLACEHOLDER, range(12))], tmp_path)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["releasable"] is False
    assert manifest["terms_sources"] == [tables.PLACEHOLDER_SOURCE]
    rows = [json.loads(line) for line in (out / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["case_id"] for row in rows] == [f"case-{seed:06d}" for seed in range(12)]
    assert manifest["counts"]["cases"] == 12 == len(list((out / "cases").iterdir()))


def test_a_real_product_is_releasable_and_records_its_substitutes(tmp_path):
    product = PROFILES["AROGYA_SANJEEVANI_GCI"]
    manifest = json.loads((write_dataset("as", [(product, range(12))], tmp_path) / "manifest.json").read_text())
    assert manifest["releasable"] is True
    assert manifest["substitutes"] == {product.product_id: dict(sorted(product.substitutes.items()))}
    assert manifest["products"][product.product_id]["source"] == product.source
    assert sum(manifest["sampling"]["redraw_reasons"].values()) == manifest["sampling"]["redraws"]


def test_one_dataset_can_hold_several_products(tmp_path):
    """A release is one dataset with a block of seeds per product, so case IDs stay
    unique and each case still regenerates to the same bytes on its own."""
    from sampler.products import REAL

    parts = [(profile, range(n * 20, (n + 1) * 20)) for n, profile in enumerate(REAL)]
    out = write_dataset("release", parts, tmp_path)
    rows = [json.loads(line) for line in (out / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 20 * len(REAL)
    assert len({row["case_id"] for row in rows}) == len(rows)
    assert {row["product_id"] for row in rows} == {profile.product_id for profile in REAL}
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["products"]) == {profile.product_id for profile in REAL}
    assert len(manifest["ruleset_hashes"]) == len(REAL)


def test_two_products_may_not_share_a_seed(tmp_path):
    from sampler.products import REAL

    with pytest.raises(ValueError, match="two products"):
        write_dataset("clash", [(profile, range(5)) for profile in REAL], tmp_path)
