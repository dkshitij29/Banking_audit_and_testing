"""Splitting a dataset into what the agent team gets and what the scorer keeps.

    uv run python -m release.split --dataset datasets/release-1

A generated dataset holds both halves of every case side by side: the documents an
agent must read, and the case.json that says what the answer is. Handing that over
whole would give the agent team the answer key, so a release is split in two:

    <dataset>/public/   the documents, the wording, the brief. Ship this.
    <dataset>/gold/     case.json and the answers. Keep this.

The public half carries no verdict, no amount, no clause list, no difficulty tier
and no scenario name, and its manifest reports no distribution of any of them: the
mix of verdicts is itself worth withholding, since an agent that knows the base
rates can play them. The scorer joins the two halves on case_id, which is the only
thing they share.

tests/test_split.py reads every byte of the public half back and fails if an answer
is anywhere in it.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
SHIPPED_DOCS = ("AGENT_BRIEF.md", "METRICS.md", "reference_prompt.md")

PUBLIC_README = """# Claims adjudication benchmark — {cases} cases

Each case is a folder of PDFs under `cases/`, plus the policy wording for its
product under `wordings/`. Settle each claim from those documents.

## Start here

1. `AGENT_BRIEF.md` — the conventions your decision is judged against. Give it to
   the agent, unchanged, on every case.
2. `reference_prompt.md` — the baseline system prompt and the tool interface to
   implement. Hold it fixed across models.
3. `METRICS.md` — what to report, and in what format.

## What is here

| Path | |
|---|---|
| `cases/<case_id>/documents/` | the documents that case's claimant submitted, and the insurer's certificate |
| `wordings/<product_id>.pdf` | the policy wording, shared by every case written against that product |
| `index.jsonl` | one row per case: its ID, its product, and the documents it has |

`index.jsonl` tells you which wording goes with which case. It tells you nothing
else, on purpose.

## Things worth knowing before you start

- **A case may be missing one of the claimant's documents.** That is a fact about
  the case, not a packaging error, and the brief says what to do about it.
- **The policies differ.** {products} products are represented, and their limits,
  waiting periods and day care rules are genuinely different. Read the wording for
  the case in front of you.
- **Nothing here states an answer.** No document says whether a claim is payable,
  and none names a clause identifier. Every document was machine-checked for that
  before release.
- **Cases vary in how hard the retrieval is.** Which case is which is withheld; the
  scorer knows, and will break your results down by it.

Answers are held by the scorer and are not in this package.
"""


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def public_row(case: dict, documents: list[str]) -> dict:
    """What the agent team may know about a case before running it."""
    return {
        "case_id": case["case_id"],
        "product_id": case["product_id"],
        "wording": f"wordings/{case['product_id']}.pdf",
        "documents": sorted(documents),
    }


def gold_row(case: dict) -> dict:
    """What the scorer needs to mark a case and break the results down."""
    gold = case["gold"]
    return {
        "case_id": case["case_id"],
        "product_id": case["product_id"],
        "difficulty": case["difficulty"],
        "scenario": case["scenario"],
        "scenario_tags": list(case["scenario_tags"]),
        "verdict": gold["verdict"],
        "payable": gold["payable"],
        "clauses": list(gold["clauses"]),
        "checks": list(gold["checks"]),
    }


def split(dataset: Path, force: bool = False) -> tuple[Path, Path]:
    """Write <dataset>/public and <dataset>/gold. Returns both paths."""
    public, gold = dataset / "public", dataset / "gold"
    for half in (public, gold):
        if half.exists():
            if not force:
                raise FileExistsError(f"{half} exists; pass --force to rebuild it")
            shutil.rmtree(half)

    index = read_rows(dataset / "index.jsonl")
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))

    public_rows, gold_rows = [], []
    for row in index:
        case_id = row["case_id"]
        folder = dataset / "cases" / case_id
        case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        documents = sorted(p.name for p in (folder / "documents").glob("*.pdf"))
        if not documents:
            raise FileNotFoundError(f"{case_id} has no rendered documents; render before splitting")

        into = public / "cases" / case_id / "documents"
        into.mkdir(parents=True, exist_ok=True)
        for name in documents:
            shutil.copy2(folder / "documents" / name, into / name)

        (gold / "cases" / case_id).mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / "case.json", gold / "cases" / case_id / "case.json")

        public_rows.append(public_row(case, [f"cases/{case_id}/documents/{name}" for name in documents]))
        gold_rows.append(gold_row(case))

    shutil.copytree(dataset / "wordings", public / "wordings")
    for name in SHIPPED_DOCS:
        shutil.copy2(DOCS / name, public / name)

    write_rows(public / "index.jsonl", public_rows)
    write_rows(gold / "gold.jsonl", gold_rows)

    products = sorted({row["product_id"] for row in public_rows})
    (public / "README.md").write_text(
        PUBLIC_README.format(cases=len(public_rows), products=len(products)), encoding="utf-8"
    )
    (public / "manifest.json").write_text(json.dumps({
        "name": manifest["name"],
        "generator_version": manifest["generator_version"],
        "engine_version": manifest["engine_version"],
        "counts": {"cases": len(public_rows)},
        "products": {
            product_id: {"cases": sum(1 for row in public_rows if row["product_id"] == product_id),
                         "wording": f"wordings/{product_id}.pdf"}
            for product_id in products
        },
        "documents_per_case": "four, or three where the claimant did not submit one",
    }, indent=2) + "\n", encoding="utf-8")

    (gold / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for name in ("validation.json", "render_discards.json"):
        if (dataset / name).exists():
            shutil.copy2(dataset / name, gold / name)
    return public, gold


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="rebuild the splits if they already exist")
    args = parser.parse_args(argv)

    public, gold = split(args.dataset, args.force)
    cases = len(read_rows(public / "index.jsonl"))
    print(f"public split: {public}  ({cases} cases) — this is the one to share")
    print(f"gold split:   {gold}  — keep this; it holds the answers")


if __name__ == "__main__":
    main()
