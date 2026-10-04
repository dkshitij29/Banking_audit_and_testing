"""What must hold for every real product: its wording, its mapping, its profile.

Each product is modelled from a policy wording nobody here may redistribute, so
the wording is fetched from corpus/manifest.csv and the tests that read it skip
when it is not on this machine. The rest hold either way.
"""

import csv
import hashlib
import re
from pathlib import Path

import pytest
import yaml

from engine import clauses as C
from sampler import ambiguity
from sampler.catalogue import ITEMS
from sampler.products import REAL
from sampler.sample import sample_case

ROOT = Path(__file__).resolve().parent.parent
MAPPING = yaml.safe_load((ROOT / "corpus" / "mapping.yaml").read_text(encoding="utf-8"))
with (ROOT / "corpus" / "manifest.csv").open(newline="", encoding="utf-8") as handle:
    MANIFEST = {row["document_id"]: row for row in csv.DictReader(handle)}

products = pytest.mark.parametrize("profile", REAL, ids=lambda profile: profile.product_id.lower())


def mapping_of(profile):
    return MAPPING[profile.product_id]


def entries_of(profile):
    block = mapping_of(profile)
    return [*block["general"].values(), *block["clauses"].values(), *block["not_modelled"]]


def document_of(profile):
    return MANIFEST[mapping_of(profile)["document"]]


def pdf_of(profile):
    return ROOT / "corpus" / "pdfs" / f"{mapping_of(profile)['document']}.pdf"


# ---------------------------------------------------------------- the mapping


@products
def test_every_product_is_mapped_to_a_document_in_the_manifest(profile):
    block = mapping_of(profile)
    assert block["document"] in MANIFEST
    assert document_of(profile)["product_id"] == profile.product_id
    assert block["profile"] == f"sampler/products/{Path(block['profile']).name}"
    assert (ROOT / block["profile"]).exists()


@products
def test_the_mapping_covers_every_clause_in_the_registry(profile):
    assert set(mapping_of(profile)["clauses"]) == set(C.REGISTRY)


@products
def test_every_modelled_clause_points_at_the_wording(profile):
    for clause_id, entry in mapping_of(profile)["clauses"].items():
        if entry.get("modelled") is not False or "pages" in entry:
            assert entry.get("pages") and entry.get("section"), clause_id


@products
def test_every_mapped_page_is_in_the_document(profile):
    pages = int(document_of(profile)["pages"])
    for entry in entries_of(profile):
        assert all(1 <= page <= pages for page in entry.get("pages", [])), entry


@products
def test_the_mapping_and_the_terms_agree_on_which_exclusions_are_modelled(profile):
    terms = profile.terms(profile.sum_insured_options[0])
    in_terms = {e.clause_id for e in terms.exclusions} | {r.clause_id for r in terms.line_exclusions}
    for clause_id in C.STANDARD_EXCLUSIONS:
        modelled = mapping_of(profile)["clauses"][clause_id].get("modelled") is not False
        assert modelled == (clause_id in in_terms), (profile.product_id, clause_id)


@products
def test_the_mapping_names_exactly_the_guards_in_use(profile):
    named = {guard for entry in entries_of(profile) for guard in entry.get("guards", [])}
    in_use = {guard.__name__ for guard in ambiguity.GENERAL + profile.ambiguities}
    assert named == in_use, profile.product_id


# ---------------------------------------------------------------- the profile


@products
def test_every_listed_bill_item_is_in_the_catalogue(profile):
    terms = profile.terms(profile.sum_insured_options[0])
    for rule in terms.line_exclusions:
        assert set(rule.item_codes) <= set(ITEMS), (profile.product_id, rule.clause_id)


@products
def test_a_product_is_releasable_and_says_where_its_rules_came_from(profile):
    assert profile.releasable
    assert document_of(profile)["uin"] in profile.source
    assert "corpus/manifest.csv" in profile.source


@products
def test_no_document_is_issued_in_the_real_insurer_s_name(profile):
    """The rules are a real product's; the branding never is (CLAUDE.md invariant 5)."""
    insurer = document_of(profile)["insurer"].lower()
    assert profile.insurer.lower() != insurer
    assert profile.uin != document_of(profile)["uin"]
    for word in insurer.replace(",", " ").split():
        if len(word) > 4 and word not in {"insurance", "company", "limited", "general", "assurance"}:
            assert word not in profile.insurer.lower(), word


@products
def test_every_policy_carries_cost_sharing_the_product_offers(profile):
    for seed in range(40):
        policy = sample_case(seed, profile).policy
        assert policy.copay_bp in {profile.mandatory_copay_bp, *profile.copay_options_bp}
        assert policy.deductible in {0, *profile.deductible_options}
        assert policy.sum_insured in profile.sum_insured_options
        step = profile.bonus_step_bp * policy.sum_insured // 10_000
        assert policy.cumulative_bonus % step == 0
        assert policy.cumulative_bonus <= profile.bonus_max_bp * policy.sum_insured // 10_000


@products
def test_a_substitute_aims_at_the_same_verdict(profile):
    from sampler.scenarios import SCENARIO_BY_NAME

    for scheduled, substitute in profile.substitutes.items():
        assert SCENARIO_BY_NAME[substitute].verdict is SCENARIO_BY_NAME[scheduled].verdict, scheduled


# ---------------------------------------------------------------- the wording itself


@products
def test_the_fetched_wording_is_the_one_in_the_manifest(profile):
    if not pdf_of(profile).exists():
        pytest.skip("corpus not fetched: uv run python -m corpus.fetch")
    from pypdf import PdfReader

    document = document_of(profile)
    assert hashlib.sha256(pdf_of(profile).read_bytes()).hexdigest() == document["sha256"]
    assert len(PdfReader(pdf_of(profile)).pages) == int(document["pages"])


@products
def test_every_quote_in_the_mapping_is_in_the_wording(profile):
    """Quotes must be the wording's own words. Text extraction splits some words
    ("m edical"), so the comparison ignores whitespace."""
    if not pdf_of(profile).exists():
        pytest.skip("corpus not fetched: uv run python -m corpus.fetch")
    from pypdf import PdfReader

    def squash(text: str) -> str:
        return re.sub(r"\s+", "", text)

    wording = squash(" ".join(page.extract_text() for page in PdfReader(pdf_of(profile)).pages))
    quotes = [entry["text"] for entry in entries_of(profile) if "text" in entry]
    assert len(quotes) >= 25, profile.product_id
    assert [quote for quote in quotes if squash(quote) not in wording] == []
