"""The public split must be shippable: documents, and no answers anywhere in it.

This is the last gate before a dataset leaves the building, so it reads the split
back off disk rather than trusting the code that wrote it.
"""

import json

import pytest

from engine import clauses as C
from engine.schema import Verdict
from release.split import read_rows, split
from render.documents import render_case
from render.llm import Budget, stub_client
from render.wording import render_policy_wording
from sampler.case import Case
from sampler.products import PROFILES, REAL
from sampler.sample import write_dataset


@pytest.fixture(scope="module")
def released(tmp_path_factory):
    """A small dataset of both products, rendered offline, then split."""
    root = tmp_path_factory.mktemp("release")
    parts = [(profile, range(n * 6, (n + 1) * 6)) for n, profile in enumerate(REAL)]
    dataset = write_dataset("small", parts, root)
    client = stub_client(cache_dir=root / "cache", budget=Budget(root / "spend.jsonl"))
    for profile, _ in parts:
        render_policy_wording(profile, dataset / "wordings")
    for row in read_rows(dataset / "index.jsonl"):
        folder = dataset / "cases" / row["case_id"]
        case = Case.model_validate_json((folder / "case.json").read_text(encoding="utf-8"))
        render_case(case, PROFILES[case.product_id], client, folder / "documents")
    public, gold = split(dataset)
    return dataset, public, gold


# ---------------------------------------------------------------- nothing leaks


def test_the_public_split_holds_no_case_file(released):
    _, public, _ = released
    assert list(public.rglob("case.json")) == []
    assert list(public.rglob("gold*")) == []


def test_no_answer_appears_anywhere_in_the_public_split(released):
    """Read every text file in the split and look for the answers themselves."""
    dataset, public, _ = released
    answers = {}
    for row in read_rows(dataset / "index.jsonl"):
        case = json.loads((dataset / "cases" / row["case_id"] / "case.json").read_text(encoding="utf-8"))
        answers[row["case_id"]] = case["gold"]

    for path in public.rglob("*"):
        if path.suffix.lower() in {".pdf"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for case_id, gold in answers.items():
            assert f'"{case_id}"' not in text or gold["verdict"] not in text, path
        for verdict in Verdict:
            # The brief and the metrics explain the verdicts on purpose; the index
            # and the manifest are the files that must not carry them.
            if path.name in {"index.jsonl", "manifest.json"}:
                assert verdict.value not in text, (path, verdict)


def test_the_index_tells_the_agent_team_only_what_it_needs(released):
    _, public, _ = released
    rows = read_rows(public / "index.jsonl")
    assert rows
    for row in rows:
        assert set(row) == {"case_id", "product_id", "wording", "documents"}
        assert (public / row["wording"]).exists()
        for document in row["documents"]:
            assert (public / document).exists()


def test_the_public_manifest_reports_no_distribution(released):
    """Knowing the mix of verdicts would let an agent play the base rates."""
    _, public, _ = released
    manifest = json.loads((public / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"name", "generator_version", "engine_version", "counts", "products",
                             "documents_per_case"}
    assert "verdicts" not in manifest and "tiers" not in manifest and "scenarios" not in manifest


def test_the_public_split_never_names_a_clause_outside_the_brief(released):
    _, public, _ = released
    for path in (public / "index.jsonl", public / "manifest.json", public / "README.md"):
        text = path.read_text(encoding="utf-8")
        assert not [clause for clause in C.REGISTRY if clause in text], path


def test_the_difficulty_tier_is_withheld(released):
    _, public, _ = released
    for path in (public / "index.jsonl", public / "manifest.json"):
        text = path.read_text(encoding="utf-8").lower()
        for tier in ("easy", "medium", "hard"):
            assert tier not in text, (path, tier)


# ---------------------------------------------------------------- everything needed is there


def test_every_case_ships_its_documents_and_its_wording(released):
    dataset, public, _ = released
    for row in read_rows(dataset / "index.jsonl"):
        shipped = sorted(p.name for p in (public / "cases" / row["case_id"] / "documents").glob("*.pdf"))
        made = sorted(p.name for p in (dataset / "cases" / row["case_id"] / "documents").glob("*.pdf"))
        assert shipped == made, row["case_id"]
    for profile in REAL:
        assert (public / "wordings" / f"{profile.product_id}.pdf").exists()


def test_the_brief_the_metrics_and_the_prompt_ship_with_it(released):
    _, public, _ = released
    for name in ("AGENT_BRIEF.md", "METRICS.md", "reference_prompt.md", "README.md"):
        assert (public / name).read_text(encoding="utf-8").strip(), name


def test_a_case_missing_a_document_ships_that_way(released):
    """The gap is the case, not a packaging fault."""
    dataset, public, _ = released
    short = [row for row in read_rows(public / "index.jsonl") if len(row["documents"]) < 4]
    for row in short:
        case = json.loads((dataset / "cases" / row["case_id"] / "case.json").read_text(encoding="utf-8"))
        assert len(case["claim"]["documents_submitted"]) < 3


# ---------------------------------------------------------------- the gold half


def test_the_gold_split_can_mark_every_case(released):
    """Every answer, exactly as the engine gave it: the flat file is what a scorer
    joins on, so it has to agree with the case files beside it."""
    dataset, public, gold = released
    public_ids = [row["case_id"] for row in read_rows(public / "index.jsonl")]
    gold_rows = {row["case_id"]: row for row in read_rows(gold / "gold.jsonl")}
    assert sorted(gold_rows) == sorted(public_ids)
    for case_id, row in gold_rows.items():
        case = json.loads((dataset / "cases" / case_id / "case.json").read_text(encoding="utf-8"))
        assert row["verdict"] == case["gold"]["verdict"]
        assert row["payable"] == case["gold"]["payable"]
        assert row["clauses"] == list(case["gold"]["clauses"])
        assert row["checks"] == list(case["gold"]["checks"])
        assert row["difficulty"] == case["difficulty"]
        assert row["scenario_tags"] == list(case["scenario_tags"])
        assert row["verdict"] in {verdict.value for verdict in Verdict}
        assert set(row["clauses"]) <= set(C.REGISTRY)
        assert (row["payable"] == 0) == (row["verdict"] in {"REJECT", "ESCALATE"})


def test_the_gold_split_keeps_the_case_files(released):
    dataset, _, gold = released
    for row in read_rows(dataset / "index.jsonl"):
        kept = gold / "cases" / row["case_id"] / "case.json"
        assert kept.read_bytes() == (dataset / "cases" / row["case_id"] / "case.json").read_bytes()


def test_splitting_twice_needs_saying_so(released):
    dataset, _, _ = released
    with pytest.raises(FileExistsError):
        split(dataset)
    split(dataset, force=True)
