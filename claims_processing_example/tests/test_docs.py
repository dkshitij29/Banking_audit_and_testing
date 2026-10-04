"""The three documents shipped to the agent team must stay true to the code.

The brief is the contract the gold answers are graded against, so its clause list
has to be the registry's, and it must carry no product's numbers: an agent told
what a waiting period is would not have to read the wording it was given.
"""

import re
from pathlib import Path

import pytest

from engine import clauses as C
from engine.rules import AMOUNT_ORDER, cap_amount
from engine.schema import Verdict
from render import layout
from render.layout import Issuer
from sampler.products import REAL

DOCS = Path(__file__).resolve().parent.parent / "docs"
BRIEF = (DOCS / "AGENT_BRIEF.md").read_text(encoding="utf-8")
METRICS = (DOCS / "METRICS.md").read_text(encoding="utf-8")
PROMPT = (DOCS / "reference_prompt.md").read_text(encoding="utf-8")


def flat(text: str) -> str:
    """Prose wraps, so a phrase is searched for without its line breaks."""
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------- the brief


def test_the_brief_lists_exactly_the_clauses_the_engine_can_cite():
    listed = set(re.findall(r"`([0-9A-Za-z][^`\n]*_[^`\n]*)`", BRIEF))
    assert listed == set(C.REGISTRY)


def test_every_clause_in_the_brief_carries_its_description():
    for clause_id, clause in C.REGISTRY.items():
        assert f"| `{clause_id}` | {clause.description} |" in BRIEF, clause_id


def test_the_brief_names_every_verdict():
    for verdict in Verdict:
        assert f"`{verdict.value}`" in BRIEF, verdict


def test_the_brief_states_the_order_the_engine_applies():
    """Nine steps, in the engine's order. Where the two disagree the dataset is
    graded on an order nobody was told about."""
    steps = re.findall(r"^\d+\. (.+)$", BRIEF, re.MULTILINE)
    assert len(steps) == len(AMOUNT_ORDER)
    for word, step in zip(("window", "not pay for", "room rate", "intensive care",
                           "condition or\n   procedure", "system of medicine", "deductible",
                           "co-payment", "sum insured"), steps, strict=True):
        assert word.split("\n")[0] in step, step


@pytest.mark.parametrize("profile", REAL, ids=lambda p: p.product_id.lower())
def test_the_brief_gives_away_no_product_s_numbers(profile):
    """"Anything that can differ between products belongs in that product's
    documents, never in the brief" (CLAUDE.md)."""
    terms = profile.terms(profile.sum_insured_options[0])
    style = layout.style_for(profile.product_id, issuer=Issuer.INSURER)
    forbidden = {
        terms.ped_wait.describe(),
        terms.initial_wait.duration.describe(),
        f"{terms.min_stay_hours} hours",
        f"{terms.pre_hospitalisation_days} days",
        f"{terms.post_hospitalisation_days} days",
    }
    forbidden |= {group.duration.describe() for group in terms.specific_wait.groups}
    for cap in (terms.room_cap, terms.icu_cap, *(s.cap_per_unit for s in terms.sublimits)):
        if cap is not None:
            forbidden |= {layout.format_money(int(cap_amount(cap, profile.sum_insured_options[0])), style)}
            if cap.bp_of_si:
                forbidden |= {f"{cap.bp_of_si // 100}%"}
    for bp in (profile.mandatory_copay_bp, *profile.copay_options_bp):
        if bp:
            forbidden |= {f"{bp // 100}%"}
    assert [value for value in forbidden if value and value in BRIEF] == []


def test_the_brief_does_not_give_the_hard_tier_away():
    """No hint that a rule might be hiding in the wording, or that a tier exists."""
    for hint in ("difficulty", "tier", "easy", "hard case", "day-care list", "check the wording"):
        assert hint not in BRIEF.lower(), hint


def test_the_brief_says_which_documents_are_the_claimant_s():
    assert "may be missing one of them" in BRIEF
    for name in ("claim form", "hospital bill", "discharge summary", "policy wording",
                 "certificate of insurance"):
        assert name in BRIEF.lower(), name
    assert "were checked when the" in BRIEF  # intake verified the rest


# ---------------------------------------------------------------- the metrics


def test_the_metrics_require_what_claude_md_requires():
    metrics = flat(METRICS)
    for requirement in ("k = 4", "confusion matrix", "pass^k", "pass^1",
                        "Escalation recall", "False escalation rate", "check adherence",
                        "Schema error rate", "Semantic error rate", "Recovery rate",
                        "Tool calls on success", "prompt_id"):
        assert requirement.lower() in metrics.lower(), requirement


def test_the_metrics_keep_the_judge_away_from_the_numbers():
    assert "Never let a model judge them" in flat(METRICS)
    assert "only the explanation" in flat(METRICS)


def test_the_metrics_forbid_a_single_accuracy_number():
    assert "Never report a single accuracy number" in flat(METRICS)


# ---------------------------------------------------------------- the reference prompt


def test_the_prompt_has_an_id_and_the_tools_it_promises():
    assert "claims-ref-1" in PROMPT
    for tool in ("list_documents", "read_document", "submit"):
        assert f"`{tool}" in PROMPT, tool


def test_the_prompt_ships_the_brief_alongside_it():
    assert "AGENT_BRIEF.md" in PROMPT
    assert "k = 4" in PROMPT
